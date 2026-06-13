"""部署进度界面

使用 curses 内建进度条组件，不依赖 whiptail --gauge 子进程，
从根源避免终端状态损坏问题。
"""
import os
import sys
import time
import threading
import logging
import curses
from widgets import ProgressBar

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
    2: [  # 追加部署
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
    """部署进度显示界面"""

    def __init__(self, mode):
        self.mode = mode
        self.steps = DEPLOY_STEPS.get(mode, [])
        self.log_file = "/var/log/vdi-deploy/installer.log"

    def run(self, stdscr, deploy_engine, mode, config):
        """执行部署并显示进度

        Args:
            stdscr: curses 标准屏幕
            deploy_engine: 部署引擎
            mode: 部署模式
            config: 配置字典

        Returns:
            True=成功, False=失败
        """
        total = len(self.steps)
        if total == 0:
            logger.warning(f"No deploy steps defined for mode {mode}")
            return True

        step_names = [name for name, _ in self.steps]
        pb = ProgressBar(stdscr, "Deploy Progress", step_names)

        try:
            for i, (step_name, step_id) in enumerate(self.steps):
                # 更新进度
                pb.update(i, step_name)

                # 检查是否取消
                if pb.wait_cancel():
                    logger.info("用户取消部署")
                    pb.close()
                    return False

                # 执行部署步骤
                logger.info(f"执行步骤 [{i+1}/{total}]: {step_name}")
                success = deploy_engine.execute_step(step_id, mode, config)
                pb.set_step_result(i, success)

                if not success:
                    logger.error(f"Step failed: {step_name}")
                    pb.close()
                    from screens.error import ErrorScreen
                    ErrorScreen(
                        f"Deploy failed: {step_name}\n\n"
                        f"Check log: {self.log_file}"
                    ).show(stdscr)
                    return False

            # 完成
            pb.update(total - 1, step_names[-1], 100)
            for i in range(total):
                pb.set_step_result(i, True)
            pb.finish(True)

            # 等待用户确认
            while True:
                ch = pb.win.getch()
                if ch in (10, 13, curses.KEY_ENTER, 27, ord('q')):
                    break

            pb.close()
            return True

        except Exception as e:
            logger.exception("Deploy process exception")
            pb.close()
            return False
