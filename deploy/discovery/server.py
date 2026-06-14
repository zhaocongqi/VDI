#!/usr/bin/env python3
"""VDI Master 发现服务

为后续 control-plane / worker 节点提供集群协调信息：
  GET /healthz                 集群就绪状态
  GET /cluster-info            全局参数（VIP/CIDR/版本/网卡）
  GET /join-token              worker join token（kubeadm token create）
  GET /cp-join?key=<install-key>   control-plane token + certificate-key
  GET /ca?key=<install-key>        CA 证书（兜底）

token 动态签发，不缓存。/cp-join 和 /ca 需 install-key 鉴权。
"""
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _parse_env_config(config_dir):
    """从 env-config.sh 解析全局参数，返回 dict"""
    env = {}
    path = os.path.join(config_dir, "env-config.sh")
    if not os.path.exists(path):
        return env
    pattern = re.compile(r'^([A-Z][A-Z0-9_]*)="([^"]*)"')
    with open(path) as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                env[m.group(1)] = m.group(2)
    return env


def _run_kubeadm(args, timeout=30):
    """执行 kubeadm 命令，返回 (returncode, stdout)。KUBECONFIG 指向 admin.conf"""
    env = dict(os.environ)
    env["KUBECONFIG"] = "/etc/kubernetes/admin.conf"
    try:
        r = subprocess.run(
            ["kubeadm"] + args,
            capture_output=True, text=True, timeout=timeout, env=env
        )
        return r.returncode, r.stdout + r.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, str(e)


def _parse_join_command(output, config_dir):
    """从 kubeadm token create --print-join-command 输出解析 token / ca_hash / join_cmd"""
    token = ""
    ca_hash = ""
    join_cmd = ""
    for line in output.splitlines():
        line = line.strip()
        if "kubeadm join" in line:
            join_cmd = line
            m = re.search(r"--token\s+(\S+)", line)
            if m:
                token = m.group(1)
            m = re.search(r"--discovery-token-ca-cert-hash\s+(\S+)", line)
            if m:
                ca_hash = m.group(1)
    # 若 join_cmd 带具体地址，替换为 VIP（HA 场景需通过 VIP 访问）
    env = _parse_env_config(config_dir)
    vip = env.get("VIP", "")
    if vip and join_cmd:
        join_cmd = re.sub(r"kubeadm join [^:]+:\d+", f"kubeadm join {vip}:6443", join_cmd)
    return token, ca_hash, join_cmd


def _parse_certificate_key(output):
    """从 kubeadm init phase upload-certs 输出解析 certificate-key（最后一个 hex 串）"""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if re.fullmatch(r"[0-9a-f]{16,40}", line):
            return line
    return ""


def _invoke_runner(runner, args):
    """统一调用 kubeadm_runner，返回 (rc, out)。

    防御性处理：当 runner 返回非二元组（例如测试默认 MagicMock 或运行时异常）
    时，归一化为失败结果 (1, '')，避免解包崩溃导致连接中断。
    """
    try:
        result = runner(args)
    except Exception as e:
        return 1, f"runner exception: {e}"
    if isinstance(result, tuple) and len(result) == 2:
        return result
    return 1, f"runner returned unexpected value: {result!r}"


class DiscoveryHandler(BaseHTTPRequestHandler):
    """发现服务请求处理器"""

    def log_message(self, fmt, *args):
        pass  # 静默默认日志（生产由 systemd journal 收集）

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_key(self):
        """校验 install-key，合法返回 True，否则发 403 并返回 False"""
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        key = (q.get("key") or [""])[0]
        if key != self.server.install_key:
            self._send_json(403, {"error": "invalid or missing install-key"})
            return False
        return True

    def do_GET(self):
        from urllib.parse import urlparse
        path = urlparse(self.path).path
        if path == "/healthz":
            return self._handle_healthz()
        if path == "/cluster-info":
            return self._handle_cluster_info()
        if path == "/join-token":
            return self._handle_join_token()
        if path == "/cp-join":
            if not self._check_key():
                return
            return self._handle_cp_join()
        if path == "/ca":
            if not self._check_key():
                return
            return self._handle_ca()
        self._send_json(404, {"error": f"unknown path: {path}"})

    def _handle_healthz(self):
        env = _parse_env_config(self.server.config_dir)
        self._send_json(200, {
            "status": "ok",
            "vip": env.get("VIP", ""),
            "k8s_version": env.get("K8S_VERSION", ""),
        })

    def _handle_cluster_info(self):
        env = _parse_env_config(self.server.config_dir)
        self._send_json(200, {
            "vip": env.get("VIP", ""),
            "pod_cidr": env.get("POD_CIDR", ""),
            "svc_cidr": env.get("SVC_CIDR", ""),
            "k8s_version": env.get("K8S_VERSION", ""),
            "vip_interface": env.get("VIP_INTERFACE", ""),
        })

    def _handle_join_token(self):
        """worker join token: kubeadm token create --print-join-command --ttl 15m"""
        rc, out = _invoke_runner(self.server.kubeadm_runner,
            ["token", "create", "--print-join-command", "--ttl", "15m"])
        if rc != 0:
            return self._send_json(500, {"error": f"kubeadm token create failed: {out.strip()}"})
        token, ca_hash, join_cmd = _parse_join_command(out, self.server.config_dir)
        if not token:
            return self._send_json(500, {"error": f"failed to parse join command: {out.strip()}"})
        self._send_json(200, {
            "token": token,
            "ca_cert_hash": ca_hash,
            "join_command": join_cmd,
        })

    def _handle_cp_join(self):
        """control-plane join: upload-certs 拿 certificate-key + 另签 token"""
        rc_certs, out_certs = _invoke_runner(self.server.kubeadm_runner,
            ["init", "phase", "upload-certs", "--upload-certs"])
        if rc_certs != 0:
            return self._send_json(500, {"error": f"upload-certs failed: {out_certs.strip()}"})
        cert_key = _parse_certificate_key(out_certs)
        if not cert_key:
            return self._send_json(500, {"error": f"failed to parse certificate-key: {out_certs.strip()}"})
        rc_tok, out_tok = _invoke_runner(self.server.kubeadm_runner,
            ["token", "create", "--print-join-command", "--ttl", "2h"])
        if rc_tok != 0:
            return self._send_json(500, {"error": f"token create failed: {out_tok.strip()}"})
        token, ca_hash, join_cmd = _parse_join_command(out_tok, self.server.config_dir)
        cp_cmd = f"{join_cmd} --control-plane --certificate-key {cert_key}"
        self._send_json(200, {
            "token": token,
            "certificate_key": cert_key,
            "ca_cert_hash": ca_hash,
            "join_command": cp_cmd,
        })

    def _handle_ca(self):
        """CA 证书文件流（兜底，certificate-key 通常已覆盖）"""
        ca_path = "/etc/kubernetes/pki/ca.crt"
        if not os.path.exists(ca_path):
            return self._send_json(404, {"error": f"CA not found: {ca_path}"})
        with open(ca_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class DiscoveryServer:
    """发现服务封装"""

    def __init__(self, config_dir="/etc/vdi", install_key="",
                 kubeadm_runner=None, port=8090, host="0.0.0.0"):
        self.config_dir = config_dir
        self.install_key = install_key
        self.kubeadm_runner = kubeadm_runner or _run_kubeadm
        self.httpd = ThreadingHTTPServer((host, port), DiscoveryHandler)
        self.httpd.config_dir = config_dir
        self.httpd.install_key = install_key
        self.httpd.kubeadm_runner = self.kubeadm_runner

    def serve_forever(self):
        self.httpd.serve_forever()

    def shutdown(self):
        self.httpd.shutdown()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VDI Master Discovery Service")
    parser.add_argument("--config-dir", default="/etc/vdi")
    parser.add_argument("--install-key-file", default="/etc/vdi/install.key")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    install_key = ""
    if os.path.exists(args.install_key_file):
        with open(args.install_key_file) as f:
            install_key = f.read().strip()

    srv = DiscoveryServer(
        config_dir=args.config_dir,
        install_key=install_key,
        port=args.port,
    )
    print(f"[vdi-discovery] listening on 0.0.0.0:{args.port}, config={args.config_dir}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
