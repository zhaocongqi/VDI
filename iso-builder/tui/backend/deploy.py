"""部署执行引擎

按模式编排部署步骤，调用 deploy/skills/ 中的脚本。
"""
import os
import subprocess
import logging

logger = logging.getLogger("vdi-installer")

# 部署脚本映射（相对于 deploy/ 目录）
SCRIPT_MAP = {
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
        self.env_config = "/etc/vdi/env-config.sh"

    def execute_step(self, step_id, mode, config):
        """执行单个部署步骤

        Args:
            step_id: 步骤标识（如 'os-init', 'kubeovn-deploy'）
            mode: 部署模式 (1-4)
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
        elif step_id == "get-join-token":
            return self._get_join_token(config)
        elif step_id == "setup-dhcp":
            return self._setup_pxe_service("dhcp", config)
        elif step_id == "setup-tftp":
            return self._setup_pxe_service("tftp", config)
        elif step_id == "setup-http":
            return self._setup_pxe_service("http", config)
        elif step_id == "start-pxe":
            return self._setup_pxe_service("start", config)

        # 通用部署步骤
        script_path = self._resolve_script(step_id)
        if not script_path:
            logger.error(f"Script not found: {step_id}")
            return False

        return self._run_script(script_path, step_id)

    def _resolve_script(self, step_id):
        """解析脚本路径（离线优先）"""
        # 优先使用离线路径
        if os.path.isdir("/cdrom/offline"):
            offline_path = OFFLINE_SCRIPT_MAP.get(step_id)
            if offline_path and os.path.exists(offline_path):
                return offline_path

        # 回退到在线路径
        relative = SCRIPT_MAP.get(step_id)
        if relative:
            # 尝试多个可能的基础路径
            for base in ["/cdrom/scripts/deploy", "deploy"]:
                full_path = os.path.join(base, relative)
                if os.path.exists(full_path):
                    return full_path

        return None

    def _run_script(self, script_path, step_id):
        """执行脚本并记录日志"""
        log_file = os.path.join(self.log_dir, f"{step_id}.log")

        try:
            with open(log_file, "w") as log:
                # source env-config.sh 再执行脚本
                env_setup = f"source {self.env_config} 2>/dev/null || true; "
                result = subprocess.run(
                    ["bash", "-c", f"{env_setup}bash {script_path}"],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=1800  # 30 分钟超时
                )

            if result.returncode == 0:
                logger.info(f"步骤 {step_id} 执行成功")
                return True
            else:
                logger.error(f"Step {step_id} failed (exit code {result.returncode})")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Step {step_id} timed out")
            return False
        except Exception as e:
            logger.error(f"Step {step_id} exception: {e}")
            return False

    def _load_offline_images(self, mode, config):
        """加载离线容器镜像"""
        script = "/cdrom/scripts/load-offline-images"
        if not os.path.exists(script):
            logger.warning("Offline image loader not found, skipping")
            return True

        component = "all" if mode in (1, 2, 4) else "worker"
        log_file = os.path.join(self.log_dir, "load-images.log")

        try:
            with open(log_file, "w") as log:
                result = subprocess.run(
                    ["bash", script, component],
                    stdout=log, stderr=subprocess.STDOUT,
                    text=True, timeout=3600
                )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Image loading exception: {e}")
            return False

    def _join_cluster(self, config):
        """Worker 节点加入集群"""
        method = config.get("join_method", "kk")
        master_ip = config.get("master_ip", "")

        if method == "kk":
            # 使用 KubeKey join
            join_cmd = f"{self._get_kk_path()} join cluster"
            log_file = os.path.join(self.log_dir, "join.log")

            try:
                with open(log_file, "w") as log:
                    result = subprocess.run(
                        ["bash", "-c", join_cmd],
                        stdout=log, stderr=subprocess.STDOUT,
                        text=True, timeout=1800
                    )
                return result.returncode == 0
            except Exception as e:
                logger.error(f"Cluster join exception: {e}")
                return False
        else:
            # 使用 kubeadm join
            token = config.get("join_token", "")
            join_cmd = f"kubeadm join {master_ip}:6443 --token {token} --discovery-token-unsafe-skip-ca-verification"
            log_file = os.path.join(self.log_dir, "join.log")

            try:
                with open(log_file, "w") as log:
                    result = subprocess.run(
                        ["bash", "-c", join_cmd],
                        stdout=log, stderr=subprocess.STDOUT,
                        text=True, timeout=1800
                    )
                return result.returncode == 0
            except Exception as e:
                logger.error(f"Cluster join exception: {e}")
                return False

    def _verify_join(self):
        """验证节点加入状态"""
        try:
            result = subprocess.run(
                ["kubectl", "get", "nodes"],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False

    def _get_join_token(self, config):
        """从 Master 获取 Join Token"""
        master_ip = config.get("master_ip", "")
        try:
            result = subprocess.run(
                ["kubectl", "token", "create", "--print-join-command"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                config["join_command"] = result.stdout.strip()
            return True
        except Exception:
            return True  # 非关键步骤

    def _setup_pxe_service(self, service, config):
        """配置 PXE 服务"""
        script = "/cdrom/pxe/start-pxe.sh"
        if not os.path.exists(script):
            logger.warning("PXE startup script not found")
            return True

        log_file = os.path.join(self.log_dir, f"pxe-{service}.log")
        try:
            with open(log_file, "w") as log:
                result = subprocess.run(
                    ["bash", script, service],
                    stdout=log, stderr=subprocess.STDOUT,
                    text=True, timeout=300
                )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"PXE config exception: {e}")
            return False

    def _get_kk_path(self):
        """获取 kk 二进制路径"""
        for path in ["/cdrom/offline/binaries/kk", "/usr/local/bin/kk", "kk"]:
            if os.path.exists(path):
                return path
        return "kk"
