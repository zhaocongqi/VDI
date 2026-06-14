"""部署完成界面"""
import os
import logging
from widgets import menu, msgbox

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

    def show(self, stdscr):
        """显示部署结果并引导下一步操作

        Args:
            stdscr: curses 标准屏幕

        Returns:
            "reboot"/"shell"（用户选择重启或回到 shell）
        """
        vip = self.config.get("vip", "N/A")
        had_skip = self.config.get("_had_skip", False)
        # 有步骤被跳过时顶部加警告（ASCII，避免 TERM=linux 下符号乱码）
        skip_warning = ""
        if had_skip:
            skip_warning = (
                "[WARNING] Deployment completed with skipped steps.\n"
                "Some components may NOT be installed. Verify cluster state:\n"
                "  kubectl get nodes\n"
                "  kubectl get pods -A\n\n"
            )

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

        message = skip_warning + message
        choice = menu(stdscr,
                      title="Deploy Complete",
                      text=message + "\n\nWhat would you like to do next?",
                      items=[
                          ("1", "Reboot - Restart system (recommended)"),
                          ("2", "Shell   - Return to bash shell"),
                      ])

        if choice == "1":
            logger.info("用户选择重启系统")
            return "reboot"
        else:
            logger.info("用户选择回到 shell")
            return "shell"
