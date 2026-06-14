# HA 集群引导 · 阶段一：发现服务 + Bootstrap Master 增强 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Master 发现服务（HTTP API）+ Bootstrap Master 装机后自动启动它并显示 install-key，为后续 control-plane/worker join 提供协调信息源。

**Architecture:** Python `http.server` 实现的发现服务（systemd unit `vdi-discovery.service`，绑 0.0.0.0:8090），暴露 `/healthz` `/cluster-info` `/join-token` `/cp-join?key=` `/ca?key=` 端点。token 动态签发（subprocess 调 kubeadm），`/cp-join` 和 `/ca` 用 install-key（24 字符随机，存 `/etc/vdi/install.key`）鉴权。Bootstrap Master 装机流程末尾新增 `enable-discovery` 步骤，Complete 屏幕显示 VIP + install-key。

**Tech Stack:** Python 3 标准库（http.server / subprocess / secrets / json）、systemd、kubeadm、jq、curl

**Scope:** 这是 spec（`docs/superpowers/specs/2026-06-14-ha-cluster-bootstrap-design.md`）3 阶段中的**阶段一**。阶段二（TUI 模式重构 + control-plane join）、阶段三（worker join + 磁盘统一）依赖本阶段产出的 discovery API，待阶段一在单 VM 验证后续写计划。

**前置约定**：
- ISO 打包无需改 `scripts/package-iso/entry`——它已 rsync 整个 `/deploy` 到 ISO 的 `/scripts/deploy/`，新增的 `deploy/discovery/` 会自动打入
- 所有 Python 代码在 `iso-builder/tui/` 或 `deploy/` 下，遵循现有 `set -euo pipefail` + `LOG_TAG` 脚本约定、curses TUI 约定
- 测试用 Python 标准库 `unittest`（代码库无 pytest），kubeadm/subprocess 用 `unittest.mock.patch`

---

## File Structure

| 文件 | 职责 |
|------|------|
| `deploy/discovery/server.py` | 发现服务 HTTP server，5 个端点 |
| `deploy/discovery/vdi-discovery.service` | systemd unit |
| `deploy/discovery/install.sh` | 安装 unit + 拷贝 server.py 到 /usr/local/bin + 启动 |
| `tui/backend/config_generator.py` | 新增 install-key 生成（修改） |
| `tui/backend/deploy.py` | 新增 `enable-discovery` step（修改） |
| `tui/screens/progress.py` | bootstrap DEPLOY_STEPS 加 enable-discovery（修改） |
| `tui/screens/complete.py` | 显示 VIP + install-key（修改） |
| `deploy/skills/os-init/scripts/init.sh` | 确保 jq 安装（修改） |
| `iso-builder/tests/test_discovery_server.py` | 发现服务单元测试（新建） |
| `iso-builder/tests/test_config_generator.py` | install-key 生成测试（新建） |

---

## Task 1: 发现服务骨架 — `/healthz` 与 `/cluster-info`

**Files:**
- Create: `deploy/discovery/server.py`
- Create: `iso-builder/tests/test_discovery_server.py`

- [ ] **Step 1: 写失败测试 — 启动 server，curl `/healthz` 和 `/cluster-info`**

Create `iso-builder/tests/test_discovery_server.py`:

```python
"""发现服务单元测试（Python 标准库 unittest，无外部依赖）"""
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.request import urlopen
from urllib.error import HTTPError

# 让测试能 import deploy/discovery/server.py
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, os.path.join(_REPO, "deploy", "discovery"))

import server


def _start_server(config_dir, install_key=""):
    """在后台线程起一个测试用 discovery server，返回 (server, port)"""
    srv = server.DiscoveryServer(
        config_dir=config_dir,
        install_key=install_key,
        kubeadm_runner=mock.MagicMock(),
        port=0,  # 随机可用端口
    )
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    port = srv.httpd.server_address[1]
    return srv, port


def _get(port, path):
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.read().decode()


class TestHealthAndClusterInfo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # 写 env-config.sh 提供全局参数
        with open(os.path.join(self.tmp, "env-config.sh"), "w") as f:
            f.write('VIP="192.168.220.100"\n')
            f.write('POD_CIDR="10.16.0.0/16"\n')
            f.write('SVC_CIDR="10.96.0.0/12"\n')
            f.write('K8S_VERSION="v1.34.3"\n')
            f.write('VIP_INTERFACE="ens160"\n')

    def test_healthz(self):
        srv, port = _start_server(self.tmp)
        try:
            status, body = _get(port, "/healthz")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertIn("status", data)
        finally:
            srv.shutdown()

    def test_cluster_info_returns_global_params(self):
        srv, port = _start_server(self.tmp)
        try:
            status, body = _get(port, "/cluster-info")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["vip"], "192.168.220.100")
            self.assertEqual(data["pod_cidr"], "10.16.0.0/16")
            self.assertEqual(data["svc_cidr"], "10.96.0.0/12")
            self.assertEqual(data["k8s_version"], "v1.34.3")
            self.assertEqual(data["vip_interface"], "ens160")
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败（server 模块不存在）**

Run: `cd /home/zcq/Github/VDI/iso-builder && python3 -m pytest tests/test_discovery_server.py -v`（若无 pytest，用 `python3 tests/test_discovery_server.py`）

Expected: FAIL，`ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: 实现 server.py 骨架（/healthz + /cluster-info）**

Create `deploy/discovery/server.py`:

```python
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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _parse_env_config(config_dir):
    """从 env-config.sh 解析全局参数，返回 dict"""
    env = {}
    path = os.path.join(config_dir, "env-config.sh")
    if not os.path.exists(path):
        return env
    pattern = re.compile(r'^([A-Z_]+)="([^"]*)"')
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


class DiscoveryHandler(BaseHTTPRequestHandler):
    """发现服务请求处理器"""

    def log_message(self, fmt, *args):
        # 静默默认日志（生产由 systemd journal 收集）
        pass

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
        # Task 2 实现
        self._send_json(501, {"error": "not implemented yet"})

    def _handle_cp_join(self):
        # Task 3 实现
        self._send_json(501, {"error": "not implemented yet"})

    def _handle_ca(self):
        # Task 3 实现
        self._send_json(501, {"error": "not implemented yet"})


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
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd /home/zcq/Github/VDI/iso-builder && python3 tests/test_discovery_server.py`

Expected: 两个测试 PASS（`test_healthz`、`test_cluster_info_returns_global_params`）

- [ ] **Step 5: 提交**

```bash
cd /home/zcq/Github/VDI
git add deploy/discovery/server.py iso-builder/tests/test_discovery_server.py
git commit -m "feat(iso-builder): 发现服务骨架 healthz 与 cluster-info 端点"
```

---

## Task 2: install-key 鉴权 — `/cp-join` 与 `/ca` 的 403 逻辑

**Files:**
- Modify: `iso-builder/tests/test_discovery_server.py`（加鉴权测试）
- Verify: `deploy/discovery/server.py`（鉴权逻辑已在 Task 1 实现，本任务补测试覆盖）

- [ ] **Step 1: 写失败测试 — 无 key 时 /cp-join 返回 403，有 key 时不返回 403**

Append to `iso-builder/tests/test_discovery_server.py`（在现有类后新增）:

```python
class TestInstallKeyAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "env-config.sh"), "w") as f:
            f.write('VIP="192.168.220.100"\n')

    def test_cp_join_without_key_returns_403(self):
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/cp-join", timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()

    def test_cp_join_with_wrong_key_returns_403(self):
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/cp-join?key=wrong", timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()

    def test_cp_join_with_correct_key_not_403(self):
        # 正确 key 时不应是 403（501 not implemented 也算通过，证明放行了鉴权）
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/cp-join?key=secret123", timeout=5)
            self.assertNotEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()

    def test_ca_without_key_returns_403(self):
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/ca", timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()
```

- [ ] **Step 2: 运行测试，确认通过（鉴权逻辑已在 Task 1 的 `_check_key` 实现）**

Run: `cd /home/zcq/Github/VDI/iso-builder && python3 tests/test_discovery_server.py`

Expected: 6 个测试全 PASS（含新增 4 个鉴权测试）

- [ ] **Step 3: 提交**

```bash
cd /home/zcq/Github/VDI
git add iso-builder/tests/test_discovery_server.py
git commit -m "test(iso-builder): 发现服务 install-key 鉴权覆盖测试"
```

---

## Task 3: token 动态签发 — `/join-token`、`/cp-join`、`/ca` 完整实现

**Files:**
- Modify: `deploy/discovery/server.py`（实现 3 个端点的 kubeadm 集成）
- Modify: `iso-builder/tests/test_discovery_server.py`（mock kubeadm 测试）

- [ ] **Step 1: 写失败测试 — mock kubeadm 验证 token 签发与解析**

Append to `iso-builder/tests/test_discovery_server.py`:

```python
class TestTokenIssuance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "env-config.sh"), "w") as f:
            f.write('VIP="192.168.220.100"\n')

    def test_join_token_parses_kubeadm_output(self):
        """kubeadm token create --print-join-command 输出解析"""
        # kubeadm 输出形如: kubeadm join 192.168.220.100:6443 --token abc.def --discovery-token-ca-cert-hash sha256:xxx
        fake_output = ("kubeadm join 192.168.220.100:6443 "
                       "--token abc123.abcdef0123456789 "
                       "--discovery-token-ca-cert-hash sha256:deadbeef\n")
        runner = mock.MagicMock(return_value=(0, fake_output))
        srv = server.DiscoveryServer(
            config_dir=self.tmp, install_key="", kubeadm_runner=runner, port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        port = srv.httpd.server_address[1]
        try:
            status, body = _get(port, "/join-token")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["token"], "abc123.abcdef0123456789")
            self.assertEqual(data["ca_cert_hash"], "sha256:deadbeef")
            self.assertIn("192.168.220.100:6443", data["join_command"])
            # 验证调用了 kubeadm token create
            runner.assert_called_once()
            called_args = runner.call_args[0][0]
            self.assertEqual(called_args[0], "token")
            self.assertEqual(called_args[1], "create")
        finally:
            srv.shutdown()

    def test_cp_join_uses_upload_certs(self):
        """cp-join 调 kubeadm init phase upload-certs 拿 certificate-key"""
        # upload-certs 输出最后一行是 certificate-key
        fake_output = ("[upload-certs] Storing the certificates...\n"
                       "W0514 ... \n"
                       "[upload-certs] Using certificate key:\n"
                       "aabbcc112233\n")
        runner = mock.MagicMock(return_value=(0, fake_output))
        srv = server.DiscoveryServer(
            config_dir=self.tmp, install_key="key123",
            kubeadm_runner=runner, port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        port = srv.httpd.server_address[1]
        try:
            status, body = _get(port, "/cp-join?key=key123")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["certificate_key"], "aabbcc112233")
            self.assertIn("--control-plane", data["join_command"])
            self.assertIn("--certificate-key aabbcc112233", data["join_command"])
        finally:
            srv.shutdown()

    def test_join_token_failure_returns_500(self):
        """kubeadm 失败时返回 500 + error"""
        runner = mock.MagicMock(return_value=(1, "kubeadm error: not initialized"))
        srv = server.DiscoveryServer(
            config_dir=self.tmp, install_key="", kubeadm_runner=runner, port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        time.sleep(0.3)
        port = srv.httpd.server_address[1]
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/join-token", timeout=5)
            self.assertEqual(ctx.exception.code, 500)
        finally:
            srv.shutdown()
```

- [ ] **Step 2: 运行测试，确认失败（端点返回 501）**

Run: `cd /home/zcq/Github/VDI/iso-builder && python3 tests/test_discovery_server.py`

Expected: 新增 3 个测试 FAIL（`_handle_join_token` 等返回 501）

- [ ] **Step 3: 实现 3 个端点的 kubeadm 集成**

Replace the three `# Task X 实现` stub handlers in `deploy/discovery/server.py`:

```python
    def _handle_join_token(self):
        """worker join token: kubeadm token create --print-join-command --ttl 15m"""
        rc, out = self.server.kubeadm_runner(
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
        """control-plane join: kubeadm init phase upload-certs 拿 certificate-key + 另签 token"""
        rc_certs, out_certs = self.server.kubeadm_runner(
            ["init", "phase", "upload-certs", "--upload-certs"])
        if rc_certs != 0:
            return self._send_json(500, {"error": f"upload-certs failed: {out_certs.strip()}"})
        cert_key = _parse_certificate_key(out_certs)
        if not cert_key:
            return self._send_json(500, {"error": f"failed to parse certificate-key: {out_certs.strip()}"})
        rc_tok, out_tok = self.server.kubeadm_runner(
            ["token", "create", "--print-join-command", "--ttl", "2h"])
        if rc_tok != 0:
            return self._send_json(500, {"error": f"token create failed: {out_tok.strip()}"})
        token, ca_hash, join_cmd = _parse_join_command(out_tok, self.server.config_dir)
        # 注入 --control-plane --certificate-key
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
```

Add the two parser helpers near the top of `deploy/discovery/server.py`（在 `_run_kubeadm` 之后）:

```python
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
    # 若 join_cmd 没带具体地址，补 VIP（kubeadm 默认输出本机地址，HA 场景需替换为 VIP）
    env = _parse_env_config(config_dir)
    vip = env.get("VIP", "")
    if vip and join_cmd:
        join_cmd = re.sub(r"kubeadm join [^:]+:\d+", f"kubeadm join {vip}:6443", join_cmd)
    return token, ca_hash, join_cmd


def _parse_certificate_key(output):
    """从 kubeadm init phase upload-certs 输出解析 certificate-key（最后一行非空）"""
    for line in reversed(output.splitlines()):
        line = line.strip()
        # certificate-key 是 6 段字母数字，形如 aabbcc112233
        if re.fullmatch(r"[0-9a-f]{16,40}", line):
            return line
    return ""
```

- [ ] **Step 4: 运行测试，确认全通过**

Run: `cd /home/zcq/Github/VDI/iso-builder && python3 tests/test_discovery_server.py`

Expected: 全部 9 个测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/zcq/Github/VDI
git add deploy/discovery/server.py iso-builder/tests/test_discovery_server.py
git commit -m "feat(iso-builder): 发现服务 token 动态签发 join-token/cp-join/ca"
```

---

## Task 4: install-key 生成（config_generator）

**Files:**
- Modify: `tui/backend/config_generator.py`
- Create: `iso-builder/tests/test_config_generator.py`

- [ ] **Step 1: 写失败测试 — install-key 生成 24 字符随机串并落盘**

Create `iso-builder/tests/test_config_generator.py`:

```python
"""config_generator 单元测试"""
import os
import re
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tui"))

from backend.config_generator import ConfigGenerator


class TestInstallKeyGeneration(unittest.TestCase):
    def test_generate_install_key_creates_24_char_file(self):
        tmp = tempfile.mkdtemp()
        gen = ConfigGenerator(output_dir=tmp)
        gen.generate_install_key()
        key_path = os.path.join(tmp, "install.key")
        self.assertTrue(os.path.exists(key_path))
        with open(key_path) as f:
            key = f.read().strip()
        # 24 字符，仅字母数字（URL 安全）
        self.assertEqual(len(key), 24)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9]{24}", key))

    def test_generate_install_key_is_random(self):
        tmp1 = tempfile.mkdtemp()
        tmp2 = tempfile.mkdtemp()
        k1 = ConfigGenerator(output_dir=tmp1)
        k2 = ConfigGenerator(output_dir=tmp2)
        k1.generate_install_key()
        k2.generate_install_key()
        with open(os.path.join(tmp1, "install.key")) as f:
            v1 = f.read()
        with open(os.path.join(tmp2, "install.key")) as f:
            v2 = f.read()
        self.assertNotEqual(v1, v2)

    def test_generate_bootstrap_includes_install_key(self):
        """bootstrap 模式 generate() 应同时生成 install.key"""
        tmp = tempfile.mkdtemp()
        gen = ConfigGenerator(output_dir=tmp)
        gen.generate(2, {
            "mode": 2,
            "node_ip": "192.168.220.128",
            "hostname": "vdi-node-01",
            "role": "master",
            "vip": "192.168.220.100",
            "vip_interface": "ens160",
            "pod_cidr": "10.16.0.0/16",
            "svc_cidr": "10.96.0.0/12",
            "k8s_version": "v1.34.3",
            "longhorn_disk": "/dev/sdb",
            "longhorn_data_dir": "/var/lib/longhorn",
        })
        self.assertTrue(os.path.exists(os.path.join(tmp, "install.key")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试，确认失败（generate_install_key 不存在）**

Run: `cd /home/zcq/Github/VDI/iso-builder && python3 tests/test_config_generator.py`

Expected: FAIL，`AttributeError: 'ConfigGenerator' object has no attribute 'generate_install_key'`

- [ ] **Step 3: 实现 generate_install_key + 在 generate() bootstrap 分支调用**

Modify `tui/backend/config_generator.py`。先在文件顶部 import 段加 `secrets`：

```python
import os
import logging
import secrets
```

然后在 `ConfigGenerator` 类的 `generate` 方法末尾（现有 `if mode == 4:` PXE 分支之后）加 bootstrap 模式 install-key 生成。找到 `generate` 方法末尾：

```python
        # 生成 PXE 配置（模式 4）
        if mode == 4:
            self._generate_pxe_config(config)
            logger.info("PXE 配置已生成")
```

在其后追加：

```python
        # Bootstrap Master 模式（1/2）生成 install-key（供后续 control-plane join 鉴权）
        if mode in (1, 2):
            self.generate_install_key()
            logger.info("install-key 已生成")
```

然后在类中新增 `generate_install_key` 方法（放在 `generate` 之后）:

```python
    def generate_install_key(self):
        """生成一次性 install-key（24 字符随机），写入 output_dir/install.key"""
        import string
        alphabet = string.ascii_letters + string.digits
        key = "".join(secrets.choice(alphabet) for _ in range(24))
        path = os.path.join(self.output_dir, "install.key")
        with open(path, "w") as f:
            f.write(key)
        os.chmod(path, 0o600)
        return key
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd /home/zcq/Github/VDI/iso-builder && python3 tests/test_config_generator.py`

Expected: 3 个测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/zcq/Github/VDI
git add iso-builder/tui/backend/config_generator.py iso-builder/tests/test_config_generator.py
git commit -m "feat(iso-builder): bootstrap 模式生成 install-key 供 discovery 鉴权"
```

---

## Task 5: systemd unit + 安装脚本

**Files:**
- Create: `deploy/discovery/vdi-discovery.service`
- Create: `deploy/discovery/install.sh`

- [ ] **Step 1: 创建 systemd unit**

Create `deploy/discovery/vdi-discovery.service`:

```ini
[Unit]
Description=VDI Master Discovery Service
After=network-online.target kubelet.service
Wants=network-online.target
ConditionPathExists=/etc/vdi/env-config.sh

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/vdi/discovery/server.py --config-dir /etc/vdi --install-key-file /etc/vdi/install.key --port 8090
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: 创建安装脚本 install.sh**

Create `deploy/discovery/install.sh`:

```bash
#!/bin/bash
set -euo pipefail

# 安装 VDI 发现服务：拷贝 server.py，部署 systemd unit，启动
LOG_TAG="[vdi-discovery]"

echo "$LOG_TAG 安装发现服务..."

# 1. 定位 server.py（ISO 内或源码）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_SRC=""
for _s in "${SCRIPT_DIR}/server.py" "/cdrom/scripts/deploy/discovery/server.py" "/opt/vdi/discovery/server.py"; do
    if [ -f "$_s" ]; then
        SERVER_SRC="$_s"
        break
    fi
done

if [ -z "$SERVER_SRC" ]; then
    echo "$LOG_TAG 错误: server.py 未找到"
    exit 1
fi

# 2. 部署文件
mkdir -p /opt/vdi/discovery
cp "$SERVER_SRC" /opt/vdi/discovery/server.py
chmod +x /opt/vdi/discovery/server.py

# 3. 部署 systemd unit
UNIT_SRC=""
for _u in "${SCRIPT_DIR}/vdi-discovery.service" "/cdrom/scripts/deploy/discovery/vdi-discovery.service"; do
    if [ -f "$_u" ]; then
        UNIT_SRC="$_u"
        break
    fi
done
if [ -n "$UNIT_SRC" ]; then
    cp "$UNIT_SRC" /etc/systemd/system/vdi-discovery.service
    systemctl daemon-reload
    systemctl enable vdi-discovery
    systemctl restart vdi-discovery
    sleep 2
    if systemctl is-active --quiet vdi-discovery; then
        echo "$LOG_TAG 发现服务已启动 (0.0.0.0:8090)"
    else
        echo "$LOG_TAG 警告: 发现服务启动失败，查看 journalctl -u vdi-discovery"
        exit 1
    fi
else
    echo "$LOG_TAG 错误: vdi-discovery.service 未找到"
    exit 1
fi
```

- [ ] **Step 3: 赋可执行权限 + 语法校验**

Run: 
```bash
cd /home/zcq/Github/VDI
chmod +x deploy/discovery/install.sh
bash -n deploy/discovery/install.sh && echo "syntax OK"
python3 -c "import ast; ast.parse(open('deploy/discovery/server.py').read()); print('server.py syntax OK')"
```

Expected: `syntax OK` + `server.py syntax OK`

- [ ] **Step 4: 提交**

```bash
cd /home/zcq/Github/VDI
git add deploy/discovery/vdi-discovery.service deploy/discovery/install.sh
git commit -m "feat(iso-builder): 发现服务 systemd unit 与安装脚本"
```

---

## Task 6: deploy.py 新增 `enable-discovery` step

**Files:**
- Modify: `tui/backend/deploy.py`

- [ ] **Step 1: 定位 deploy.py 的 step 路由与 SCRIPT_MAP**

Read `iso-builder/tui/backend/deploy.py`，确认 `execute_step` 的 `if step_id == ...` 路由链（约 66-82 行）和 `SCRIPT_MAP`/`OFFLINE_SCRIPT_MAP`（约 12-31 行）。

- [ ] **Step 2: 在 execute_step 路由链加 enable-discovery**

Modify `tui/backend/deploy.py`。在 `execute_step` 方法的特殊步骤处理链中（`elif step_id == "start-pxe":` 之后），加：

```python
        elif step_id == "enable-discovery":
            return self._enable_discovery(config)
```

- [ ] **Step 3: 实现 _enable_discovery 方法**

在 `DeployEngine` 类中（`_setup_pxe_service` 方法之后、`_get_kk_path` 之前）加：

```python
    def _enable_discovery(self, config):
        """安装并启动 Master 发现服务（仅 master 模式）"""
        install_script = "/cdrom/scripts/deploy/discovery/install.sh"
        if not os.path.exists(install_script):
            # 源码环境回退
            for candidate in ["deploy/discovery/install.sh",
                              "/opt/vdi/discovery/install.sh"]:
                if os.path.exists(candidate):
                    install_script = candidate
                    break
        if not os.path.exists(install_script):
            logger.warning("Discovery install script not found, skipping")
            self._reset_log_buffer("enable-discovery")
            self._append_log_line("[warn] discovery install.sh not found")
            return True  # 非致命，允许继续

        # 发现服务需要 install.key 存在（bootstrap 模式 config_generator 已生成）
        return self._run_streaming(["bash", install_script],
                                   "enable-discovery", timeout=120)
```

- [ ] **Step 4: 语法校验**

Run:
```bash
cd /home/zcq/Github/VDI/iso-builder/tui
python3 -c "from backend.deploy import DeployEngine; e=DeployEngine(); print('import OK, has _enable_discovery:', hasattr(e, '_enable_discovery'))"
```

Expected: `import OK, has _enable_discovery: True`

- [ ] **Step 5: 提交**

```bash
cd /home/zcq/Github/VDI
git add iso-builder/tui/backend/deploy.py
git commit -m "feat(iso-builder): 新增 enable-discovery 部署步骤"
```

---

## Task 7: bootstrap DEPLOY_STEPS 加 enable-discovery

**Files:**
- Modify: `tui/screens/progress.py`

- [ ] **Step 1: 在 DEPLOY_STEPS 模式 1/2 末尾加 enable-discovery**

Modify `tui/screens/progress.py`。找到 `DEPLOY_STEPS` 字典的模式 1 块（约 19-27 行）:

```python
    1: [  # 全新安装
        ("System Init", "os-init"),
        ("Deploy K8s Cluster", "kubekey-deploy-k8s"),
        ("Deploy kube-vip", "kubevip-deploy"),
        ("Deploy Kube-OVN", "kubeovn-deploy"),
        ("Deploy Longhorn", "longhorn-deploy"),
        ("Deploy KubeVirt", "kubevirt-deploy"),
        ("Deploy kagent", "kagent-deploy"),
    ],
```

改为（末尾加 enable-discovery）:

```python
    1: [  # 全新安装
        ("System Init", "os-init"),
        ("Deploy K8s Cluster", "kubekey-deploy-k8s"),
        ("Deploy kube-vip", "kubevip-deploy"),
        ("Deploy Kube-OVN", "kubeovn-deploy"),
        ("Deploy Longhorn", "longhorn-deploy"),
        ("Deploy KubeVirt", "kubevirt-deploy"),
        ("Deploy kagent", "kagent-deploy"),
        ("Enable Discovery Service", "enable-discovery"),
    ],
```

对模式 2 块（约 28-36 行）做同样修改——末尾加 `("Enable Discovery Service", "enable-discovery"),`。

- [ ] **Step 2: 语法校验 + 步骤计数验证**

Run:
```bash
cd /home/zcq/Github/VDI/iso-builder/tui
python3 -c "
from screens.progress import DEPLOY_STEPS
print('mode 1 steps:', len(DEPLOY_STEPS[1]))
print('mode 2 steps:', len(DEPLOY_STEPS[2]))
assert DEPLOY_STEPS[1][-1] == ('Enable Discovery Service', 'enable-discovery')
assert DEPLOY_STEPS[2][-1] == ('Enable Discovery Service', 'enable-discovery')
print('OK')
"
```

Expected: `mode 1 steps: 8` / `mode 2 steps: 8` / `OK`

- [ ] **Step 3: 提交**

```bash
cd /home/zcq/Github/VDI
git add iso-builder/tui/screens/progress.py
git commit -m "feat(iso-builder): bootstrap 部署流程末尾启动发现服务"
```

---

## Task 8: complete.py 显示 VIP + install-key

**Files:**
- Modify: `tui/screens/complete.py`

- [ ] **Step 1: 在 CompleteScreen 读 install.key 并在消息中显示**

Modify `tui/screens/complete.py`。找到 `show` 方法里 `had_skip` 逻辑之后、`if self.mode in (1, 2):` 之前（约 32-42 行区域），加 install-key 读取：

```python
        vip = self.config.get("vip", "N/A")
        had_skip = self.config.get("_had_skip", False)
        # 读取 install-key（bootstrap 模式生成，供后续 control-plane join）
        install_key = ""
        for _kp in ["/etc/vdi/install.key",
                    os.path.expanduser("~/vdi-config/install.key")]:
            try:
                with open(_kp) as f:
                    install_key = f.read().strip()
                if install_key:
                    break
            except (OSError, IOError):
                continue
```

然后在模式 1/2 的 `message`（现有 `VDI Cluster Deployed Successfully!\n\n...` 块）末尾的 `Log Directory` 行之后，加 install-key 提示。找到：

```python
                f"Log Directory: /var/log/vdi-deploy/"
            )
```

改为：

```python
                f"Log Directory: /var/log/vdi-deploy/"
            )
        if install_key:
            message += (
                f"\n--- Control-Plane Join Key ---\n"
                f"  Install Key: {install_key}\n"
                f"  (第 2/3 台 Master 装机时填此 key 加入集群)"
            )
```

（注意：这段 `if install_key:` 要放在 `if self.mode in (1, 2): message = (...)` 块之外、`elif self.mode == 3:` 之前，使它只对 master 模式追加）

- [ ] **Step 2: 语法校验**

Run:
```bash
cd /home/zcq/Github/VDI/iso-builder/tui
python3 -c "from screens.complete import CompleteScreen; print('import OK')"
```

Expected: `import OK`

- [ ] **Step 3: 提交**

```bash
cd /home/zcq/Github/VDI
git add iso-builder/tui/screens/complete.py
git commit -m "feat(iso-builder): Complete 屏幕显示 VIP 与 install-key"
```

---

## Task 9: os-init 确保 jq 安装

**Files:**
- Modify: `deploy/skills/os-init/scripts/init.sh`

- [ ] **Step 1: 在 os-init 基础依赖段确认 jq**

Modify `deploy/skills/os-init/scripts/init.sh`。找到"安装基础依赖"段（约 60-77 行），现有离线/在线安装后，确保 jq 存在。在 `systemctl enable --now iscsid` 之前加 jq 校验：

```python
# 确保 jq 可用（discovery 服务返回 JSON，curl + jq 解析）
if ! command -v jq &>/dev/null; then
    echo "$LOG_TAG 安装 jq..."
    if [ -n "${OFFLINE_PACKAGES:-}" ] && [ -d "${OFFLINE_PACKAGES}" ]; then
        dpkg -i "${OFFLINE_PACKAGES}"/jq*.deb 2>/dev/null || true
    else
        apt-get install -y -qq jq 2>/dev/null || true
    fi
fi
```

- [ ] **Step 2: 语法校验**

Run: `cd /home/zcq/Github/VDI && bash -n deploy/skills/os-init/scripts/init.sh && echo "syntax OK"`

Expected: `syntax OK`

- [ ] **Step 3: 提交**

```bash
cd /home/zcq/Github/VDI
git add deploy/skills/os-init/scripts/init.sh
git commit -m "feat(iso-builder): os-init 确保 jq 安装（discovery JSON 解析）"
```

---

## Task 10: 单 VM 端到端验证

**Files:** 无代码改动，手动验证清单

- [ ] **Step 1: 构建 ISO**

Run:
```bash
cd /home/zcq/Github/VDI/iso-builder && make iso
```

Expected: `dist/vdi-offline-v1.0.0.iso` 生成

- [ ] **Step 2: 挂载 ISO 确认 discovery 文件已打入**

Run:
```bash
sudo mount -o loop,ro dist/vdi-offline-v1.0.0.iso /mnt
ls /mnt/scripts/deploy/discovery/
# 期望: install.sh  server.py  vdi-discovery.service
sudo umount /mnt
```

Expected: 三个文件都在

- [ ] **Step 3: VMware 启动单 VM，走 bootstrap 模式（模式2）**

启动 ISO → TUI → 模式 2 → 填配置 → 确认 → 部署。观察：
- 进度条到 100%，最后一步 `Enable Discovery Service` 显示 `[OK]`
- Complete 屏幕显示 `Cluster VIP: 192.168.220.100` 和 `Install Key: <24 字符>`

- [ ] **Step 4: 验证发现服务各端点**

在 VM 内（或同网段另一台机器）curl 各端点。替换 `<VIP>` 为实际 VIP，`<KEY>` 为 Complete 屏幕的 install-key：

```bash
# healthz（无需 key）
curl -s http://<VIP>:8090/healthz | jq .
# 期望: {"status":"ok","vip":"192.168.220.100","k8s_version":"v1.34.3"}

# cluster-info（无需 key）
curl -s http://<VIP>:8090/cluster-info | jq .
# 期望: {"vip":"...","pod_cidr":"...","svc_cidr":"...","k8s_version":"...","vip_interface":"..."}

# join-token（无需 key）
curl -s http://<VIP>:8090/join-token | jq .
# 期望: {"token":"...","ca_cert_hash":"sha256:...","join_command":"kubeadm join <VIP>:6443 ..."}

# cp-join（需 key）
curl -s "http://<VIP>:8090/cp-join?key=<KEY>" | jq .
# 期望: {"token":"...","certificate_key":"...","ca_cert_hash":"...","join_command":"kubeadm join <VIP>:6443 ... --control-plane --certificate-key ..."}

# 鉴权失败验证（无 key → 403）
curl -s -o /dev/null -w "%{http_code}\n" http://<VIP>:8090/cp-join
# 期望: 403
```

Expected: 各端点返回正确 JSON，无 key 的 cp-join 返回 403

- [ ] **Step 5: 提交验证记录**

记录验证结果到 commit message（无代码变更则跳过 commit，记录在会话/PR）：

```bash
# 若一切正常，打 tag 标记阶段一完成
cd /home/zcq/Github/VDI
git tag -a ha-bootstrap-phase1-done -m "阶段一完成：发现服务 + bootstrap 增强在单 VM 验证通过"
git push --tags
```

---

## 阶段一完成准则

- [ ] 9 个 discovery server 单元测试通过
- [ ] 3 个 config_generator 单元测试通过
- [ ] ISO 内含 `scripts/deploy/discovery/` 三文件
- [ ] 单 VM bootstrap 模式部署成功，发现服务 systemd 启动
- [ ] 5 个 HTTP 端点 curl 返回正确，install-key 鉴权生效

## 后续阶段（待阶段一验证后另起计划）

- **阶段二**：TUI 4→3 模式重构（`welcome.py`）、`cp_join_config.py`（curl cluster-info 自动填充 + install-key 输入）、`deploy/cp-join/deploy.sh`（kubeadm join --control-plane --certificate-key + kube-vip + enable-discovery）、progress.py 模式② DEPLOY_STEPS、installer.py 模式路由。需 3 VM 验证。
- **阶段三**：`join_config.py` 重构（curl join-token）、`deploy/worker-join/deploy.sh`、`storage_config` 提升为所有模式通用步骤、progress.py 模式③ DEPLOY_STEPS。需 4+ VM 验证。
