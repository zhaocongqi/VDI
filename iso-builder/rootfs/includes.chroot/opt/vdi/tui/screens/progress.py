"""部署进度界面"""
import os
import sys
import time
import subprocess
import threading
import logging
from utils.whiptail_wrapper import Whiptail

logger = logging.getLogger("vdi-installer")


# 部署步骤定义（按模式）
DEPLOY_STEPS = {
    1: [  # 全新安装
        ("System Init", "os-init"),
        ("Deploy K8s Cluster", "kubekey-deploy-k8s"),
        ("Deploy kube-vip", "kubevip-deploy"),
        ("Deploy Kube-OVN", "kubeovn-deploy"),
        ("Deploy Longhorn", "longhorn-deploy"),
        ("Deploy KubeVirt", "kubevirt-deploy"),
        ("Deploy kagent", "kagent-deploy"),
    ],
    2: [  # 追加部署（同模式 1 但跳过 OS 安装）
        ("System Init", "os-init"),
        ("Deploy K8s Cluster", "kubekey-deploy-k8s"),
        ("Deploy kube-vip", "kubevip-deploy"),
        ("Deploy Kube-OVN", "kubeovn-deploy"),
        ("Deploy Longhorn", "longhorn-deploy"),
        ("Deploy KubeVirt", "kubevirt-deploy"),
        ("Deploy kagent", "kagent-deploy"),
    ],
    3: [  # 添加节点
        ("Load Offline Images", "load-images"),
        ("Join Cluster", "join-cluster"),
        ("Verify Node Status", "verify-join"),
    ],
    4: [  # PXE 服务
        ("Get Join Token", "get-join-token"),
        ("Setup DHCP Service", "setup-dhcp"),
        ("Setup TFTP Service", "setup-tftp"),
        ("Setup HTTP Service", "setup-http"),
        ("Start PXE Service", "start-pxe"),
    ],
}


class ProgressScreen:
    """部署进度显示界面

    使用 whiptail --gauge 显示进度条，每步完成后更新。
    """

    def __init__(self, mode):
        self.mode = mode
        self.steps = DEPLOY_STEPS.get(mode, [])
        self.current_step = 0
        self.log_file = "/var/log/vdi-deploy/installer.log"

    def run(self, deploy_engine, mode, config):
        """执行部署并显示进度

        返回: True=成功, False=失败
        """
        total = len(self.steps)
        if total == 0:
            logger.warning(f"No deploy steps defined for mode {mode}")
            return True

        # 使用 gauge 进度条显示
        gauge_proc = self._start_gauge()

        try:
            for i, (step_name, step_id) in enumerate(self.steps):
                self.current_step = i
                percent = int((i / total) * 100)

                # 更新进度
                self._update_gauge(gauge_proc, percent, step_name, i, total)

                # 执行部署步骤
                logger.info(f"执行步骤 [{i+1}/{total}]: {step_name}")
                success = deploy_engine.execute_step(step_id, mode, config)

                if not success:
                    logger.error(f"Step failed: {step_name}")
                    self._stop_gauge(gauge_proc)
                    from screens.error import ErrorScreen
                    ErrorScreen(
                        f"Deploy failed: {step_name}\n\n"
                        f"Check log: {self.log_file}"
                    ).show()
                    return False

            # 完成
            self._update_gauge(gauge_proc, 100, "Deploy Complete", total, total)
            self._stop_gauge(gauge_proc)
            return True

        except Exception as e:
            logger.exception("Deploy process exception")
            self._stop_gauge(gauge_proc)
            return False

    def _start_gauge(self):
        """启动 whiptail gauge 进程"""
        proc = subprocess.Popen(
            ["whiptail",
             "--title", "Deploy Progress",
             "--backtitle", "VDI Cluster Offline Deploy",
             "--gauge", "Preparing...", "20", "70", "0"],
            stdin=subprocess.PIPE,
            text=True
        )
        return proc

    def _update_gauge(self, proc, percent, current_name, step_idx, total):
        """更新 gauge 进度"""
        # 构建进度文本
        lines = [f"Running: {current_name}", ""]

        for i, (name, _) in enumerate(self.steps):
            if i < step_idx:
                lines.append(f"  [OK] {name}")
            elif i == step_idx:
                lines.append(f"  --> {name} ...")
            else:
                lines.append(f"      {name}")

        lines.extend(["", f"Log: {self.log_file}"])

        # gauge 格式：XXX PERCENT\n 描述文本
        msg = f"XXX\n{percent}\n" + "\n".join(lines) + "\nXXX\n"
        try:
            proc.stdin.write(msg)
            proc.stdin.flush()
        except BrokenPipeError:
            pass

    def _stop_gauge(self, proc):
        """停止 gauge 进程"""
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.terminate()
