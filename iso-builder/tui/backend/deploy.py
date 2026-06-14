"""部署执行引擎

按模式编排部署步骤，调用 deploy/skills/ 中的脚本。
所有子进程执行统一走 _run_streaming()：逐行读 stdout，既落盘日志文件，
又追加到线程安全 ring buffer，供 ProgressScreen 实时渲染日志面板。
"""
import os
import subprocess
import logging
import threading
from collections import deque

logger = logging.getLogger("vdi-installer")

# 部署脚本映射（相对于 deploy/ 目录）
SCRIPT_MAP = {
    "os-install": "skills/os-install/scripts/install.sh",
    "os-init": "skills/os-init/scripts/init.sh",
    "kubekey-deploy-k8s": "k8s/deploy.sh",
    "kubevip-deploy": "kube-vip/deploy-kube-vip.sh",
    "kubeovn-deploy": "kube-ovn/deploy.sh",
    "longhorn-deploy": "longhorn/deploy.sh",
    "kubevirt-deploy": "kubevirt/deploy.sh",
    "kagent-deploy": "kagent/deploy-agents.sh",
}

# 离线环境下的脚本路径（在 ISO 中）
OFFLINE_SCRIPT_MAP = {
    "os-install": "/cdrom/scripts/deploy/skills/os-install/scripts/install.sh",
    "os-init": "/cdrom/scripts/deploy/skills/os-init/scripts/init.sh",
    "kubekey-deploy-k8s": "/cdrom/scripts/deploy/k8s/deploy.sh",
    "kubevip-deploy": "/cdrom/scripts/deploy/kube-vip/deploy-kube-vip.sh",
    "kubeovn-deploy": "/cdrom/scripts/deploy/kube-ovn/deploy.sh",
    "longhorn-deploy": "/cdrom/scripts/deploy/longhorn/deploy.sh",
    "kubevirt-deploy": "/cdrom/scripts/deploy/kubevirt/deploy.sh",
    "kagent-deploy": "/cdrom/scripts/deploy/kagent/deploy-agents.sh",
}


class DeployEngine:
    """部署执行引擎"""

    def __init__(self):
        self.log_dir = os.environ.get("VDI_LOG_DIR", "/var/log/vdi-deploy")
        try:
            os.makedirs(self.log_dir, exist_ok=True)
        except PermissionError:
            # 非 root 环境回退到用户目录
            self.log_dir = os.path.expanduser("~/vdi-deploy-logs")
            os.makedirs(self.log_dir, exist_ok=True)
        # env-config.sh 来源优先级：TUI 生成 > ISO 内置 > 离线包
        self.env_config = "/etc/vdi/env-config.sh"
        if not os.path.exists(self.env_config):
            for candidate in ["/cdrom/scripts/deploy/env-config.sh", "/cdrom/offline/env-config.sh"]:
                if os.path.exists(candidate):
                    self.env_config = candidate
                    break
        # 实时日志缓冲（线程安全 ring buffer）
        self._log_lines = deque(maxlen=500)
        self._log_lock = threading.Lock()

    # ── 实时日志缓冲 API ──────────────────────────────────────

    def _reset_log_buffer(self, step_id):
        """步骤开始前清空缓冲区"""
        with self._log_lock:
            self._log_lines.clear()

    def _append_log_line(self, line):
        """追加一行日志（worker 线程调用）"""
        with self._log_lock:
            self._log_lines.append(line)

    def get_recent_logs(self, n=8):
        """返回最近 n 行日志快照（UI 线程调用，返回独立 list）"""
        with self._log_lock:
            snapshot = list(self._log_lines)
        return snapshot[-n:] if len(snapshot) >= n else snapshot

    # ── 统一流式执行器 ────────────────────────────────────────

    def _run_streaming(self, cmd, step_id, timeout=1800):
        """流式执行命令：逐行读 stdout，同时写日志文件 + 实时缓冲。

        Args:
            cmd: list[str] 命令（如 ["bash","-c","..."]）或字符串（自动包成 bash -c）
            step_id: 步骤标识，决定日志文件名（{step_id}.log）
            timeout: 超时秒数

        Returns:
            True=成功(returncode 0), False=失败/超时/异常
        """
        if isinstance(cmd, str):
            cmd = ["bash", "-c", cmd]

        log_file = os.path.join(self.log_dir, f"{step_id}.log")
        self._reset_log_buffer(step_id)

        proc = None
        try:
            with open(log_file, "w") as log:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,  # 行缓冲（text 模式）
                )
                # 逐行读：既写文件（持久化），又追加缓冲（实时 UI）
                for line in proc.stdout:
                    log.write(line)
                    log.flush()
                    self._append_log_line(line.rstrip("\n"))
                proc.stdout.close()
                proc.wait(timeout=timeout)

            if proc.returncode == 0:
                logger.info(f"步骤 {step_id} 执行成功")
                return True
            else:
                logger.error(f"Step {step_id} failed (exit {proc.returncode})")
                return False

        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
            logger.error(f"Step {step_id} timed out")
            return False
        except FileNotFoundError as e:
            self._append_log_line(f"[error] command not found: {e}")
            logger.error(f"Step {step_id} command not found: {e}")
            return False
        except Exception as e:
            self._append_log_line(f"[error] {e}")
            logger.error(f"Step {step_id} exception: {e}")
            return False

    # ── 步骤执行 ──────────────────────────────────────────────

    def execute_step(self, step_id, mode, config):
        """执行单个部署步骤

        Args:
            step_id: 步骤标识（如 'os-init', 'kubeovn-deploy'）
            mode: 部署模式 (1=首节点, 2=管理节点, 3=工作节点)
            config: 配置字典

        Returns:
            True=成功, False=失败
        """
        logger.info(f"执行步骤: {step_id} (模式 {mode})")

        # 特殊步骤处理
        if step_id == "load-images":
            return self._load_offline_images(mode, config)
        elif step_id == "join-cluster":
            return self._join_cluster(config)
        elif step_id == "verify-join":
            return self._verify_join()
        elif step_id == "enable-discovery":
            return self._enable_discovery(config)

        # 通用部署步骤
        script_path = self._resolve_script(step_id)
        if not script_path:
            logger.error(f"Script not found: {step_id}")
            self._reset_log_buffer(step_id)
            self._append_log_line(f"[error] script not found for step: {step_id}")
            return False

        return self._run_script(script_path, step_id)

    def _resolve_script(self, step_id):
        """解析脚本路径（ISO 内优先）"""
        relative = SCRIPT_MAP.get(step_id)
        if relative:
            for base in ["/cdrom/scripts/deploy", "deploy"]:
                full_path = os.path.join(base, relative)
                if os.path.exists(full_path):
                    return full_path

        offline_path = OFFLINE_SCRIPT_MAP.get(step_id)
        if offline_path and os.path.exists(offline_path):
            return offline_path

        return None

    def _run_script(self, script_path, step_id):
        """执行部署脚本（先 source env-config.sh）"""
        env_setup = f"source {self.env_config} 2>/dev/null || true; "
        cmd = f"{env_setup}bash {script_path}"
        return self._run_streaming(cmd, step_id, timeout=1800)

    def _load_offline_images(self, mode, config):
        """加载离线容器镜像"""
        script = "/cdrom/scripts/load-offline-images"
        if not os.path.exists(script):
            logger.warning("Offline image loader not found, skipping")
            return True
        component = "all" if mode == 1 else "worker"
        return self._run_streaming(["bash", script, component], "load-images", timeout=3600)

    def _join_cluster(self, config):
        """加入集群（管理节点控制面 / 工作节点）

        优先使用从 discovery 服务获取的 join_command；
        回退到手动拼接 kubeadm join 命令。
        管理节点的 join_command 已包含 --control-plane --certificate-key。
        """
        # 优先使用 discovery 服务返回的完整 join command
        join_cmd = config.get("join_command", "")
        if join_cmd:
            logger.info(f"使用 discovery 获取的 join command (method={config.get('join_method')})")
            return self._run_streaming(join_cmd, "join-cluster", timeout=1800)

        # 回退：手动拼接
        master_ip = config.get("master_ip", "")
        token = config.get("join_token", "")
        ca_hash = config.get("ca_cert_hash", "")
        join_method = config.get("join_method", "worker")

        if token and master_ip:
            cmd = f"kubeadm join {master_ip}:6443 --token {token}"
            if ca_hash:
                cmd += f" --discovery-token-ca-cert-hash {ca_hash}"
            else:
                cmd += " --discovery-token-unsafe-skip-ca-verification"
            if join_method == "control-plane":
                cert_key = config.get("certificate_key", "")
                cmd += " --control-plane"
                if cert_key:
                    cmd += f" --certificate-key {cert_key}"
            return self._run_streaming(cmd, "join-cluster", timeout=1800)

        self._reset_log_buffer("join-cluster")
        self._append_log_line("[error] no join token or master IP available")
        return False

    def _verify_join(self):
        """验证节点加入状态"""
        return self._run_streaming(["kubectl", "get", "nodes"], "verify-join", timeout=30)

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

    def _get_kk_path(self):
        """获取 kk 二进制路径"""
        for path in ["/cdrom/offline/binaries/kk", "/usr/local/bin/kk", "kk"]:
            if os.path.exists(path):
                return path
        return "kk"
