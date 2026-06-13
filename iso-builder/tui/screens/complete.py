"""部署完成界面"""
import os
import subprocess
import logging
from utils.whiptail_wrapper import Whiptail

logger = logging.getLogger("vdi-installer")

MODE_NAMES = {
    1: "Fresh Install",
    2: "Append Deploy",
    3: "Join Node",
    4: "PXE Server",
}


class CompleteScreen:
    """部署完成界面"""

    def __init__(self, mode, config):
        self.mode = mode
        self.config = config
        self.wt = Whiptail(title="Deploy Complete", height=22, width=70)

    def show(self):
        """显示部署结果并引导下一步操作

        返回: "reboot"/"shell"（用户选择重启或回到 shell）
        """
        vip = self.config.get("vip", "N/A")

        if self.mode in (1, 2):
            message = (
                f"VDI Cluster Deployed Successfully!\n\n"
                f"Deploy Mode: {MODE_NAMES.get(self.mode, '')}\n"
                f"Cluster VIP: {vip}\n"
                f"K8s Version: {self.config.get('k8s_version', '')}\n"
                f"Pod CIDR:    {self.config.get('pod_cidr', '')}\n\n"
                f"--- Verify Commands ---\n"
                f"  kubectl get nodes\n"
                f"  kubectl get pods -A\n"
                f"  kubectl get sc\n\n"
                f"--- Add Worker Nodes ---\n"
                f"Boot other nodes with this ISO, select Mode 3 (Join Node)\n"
                f"or select Mode 4 (PXE Server) for batch deployment.\n\n"
                f"--- Add Worker Manually ---\n"
                f"  kubeadm token create --print-join-command\n\n"
                f"Log Directory: /var/log/vdi-deploy/"
            )
        elif self.mode == 3:
            message = (
                "Worker node joined cluster successfully!\n\n"
                f"Node IP:   {self.config.get('node_ip', '')}\n"
                f"Hostname:  {self.config.get('hostname', '')}\n\n"
                f"Verify on Master node:\n"
                f"  kubectl get nodes\n"
                f"  kubectl get pods -A | grep {self.config.get('hostname', '')}\n\n"
                f"Log Directory: /var/log/vdi-deploy/"
            )
        elif self.mode == 4:
            message = (
                "PXE Server Started!\n\n"
                f"DHCP Range:       {self.config.get('dhcp_start', '')}-{self.config.get('dhcp_end', '')}\n"
                f"Expected Workers: {self.config.get('worker_count', '')}\n\n"
                "Worker node deployment steps:\n"
                "1. Set Worker nodes to PXE network boot\n"
                "2. Workers auto-get IP and start installation\n"
                "3. After install, workers auto-join the cluster\n\n"
                "Monitor Worker installation:\n"
                f"  tail -f /var/log/vdi-deploy/pxe.log\n\n"
                f"Log Directory: /var/log/vdi-deploy/"
            )
        else:
            message = "Deployment complete."

        # MODE_FRESH 需要重启到硬盘；其他模式也需要重启或回到 shell
        choice = self.wt.menu(
            message + "\n\nWhat would you like to do next?",
            [
                ("1", "Reboot - Restart system (recommended for Fresh Install)"),
                ("2", "Shell  - Return to bash shell"),
            ]
        )

        if choice == "1":
            logger.info("用户选择重启系统")
            return "reboot"
        else:
            logger.info("用户选择回到 shell")
            return "shell"
