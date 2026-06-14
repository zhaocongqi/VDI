"""部署完成界面"""
import os
import logging
from widgets import menu, msgbox

logger = logging.getLogger("vdi-installer")

MODE_NAMES = {
    1: "首节点",
    2: "管理节点",
    3: "工作节点",
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
        resumed = self.config.get("resumed", False)
        need_reboot = self.config.get("_need_reboot", False)

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

        # 有步骤被跳过时顶部加警告
        skip_warning = ""
        if had_skip:
            skip_warning = (
                "[WARNING] Deployment completed with skipped steps.\n"
                "Some components may NOT be installed. Verify cluster state:\n"
                "  kubectl get nodes\n"
                "  kubectl get pods -A\n\n"
            )

        # Mode 1 Phase 1 完成（OS 已写入磁盘，需要重启进入 Phase 2）
        if need_reboot and not resumed:
            disk = self.config.get("install_disk", "N/A")
            message = (
                f"OS Installation Phase 1 Complete!\n\n"
                f"Deploy Mode: {MODE_NAMES.get(self.mode, '')}\n"
                f"Target Disk: {disk}\n\n"
                f"--- Next Step ---\n"
                f"1. Remove the CD-ROM / ISO from this machine\n"
                f"2. Reboot to boot from the installed disk\n"
                f"3. VDI deployment (Phase 2) will start automatically\n\n"
                f"DO NOT reboot with the CD-ROM still attached\n"
                f"unless you want to re-enter the Live environment.\n\n"
                f"Log Directory: /var/log/vdi-deploy/"
            )
            choice = menu(stdscr,
                          title="OS Installed - Reboot Required",
                          text=message + "\n\nWhat would you like to do next?",
                          items=[
                              ("1", "Reboot - Remove CD-ROM first, then reboot (recommended)"),
                              ("2", "Shell   - Return to bash shell"),
                          ])
            if choice == "1":
                logger.info("用户选择重启（Phase 1 完成，进入 Phase 2）")
                return "reboot"
            else:
                logger.info("用户选择回到 shell")
                return "shell"

        if self.mode == 1:
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
                f"--- Add More Nodes ---\n"
                f"Mode 2 (管理节点): Join as control plane for HA\n"
                f"Mode 3 (工作节点): Join as worker to run desktops\n\n"
                f"Log Directory: /var/log/vdi-deploy/"
            )
        elif self.mode == 2:
            message = (
                "Control plane node joined cluster successfully!\n\n"
                f"Node IP:   {self.config.get('node_ip', '')}\n"
                f"Hostname:  {self.config.get('hostname', '')}\n\n"
                f"Verify:\n"
                f"  kubectl get nodes\n"
                f"  kubectl get pods -A | grep {self.config.get('hostname', '')}\n\n"
                f"Log Directory: /var/log/vdi-deploy/"
            )
        elif self.mode == 3:
            message = (
                "Worker node joined cluster successfully!\n\n"
                f"Node IP:   {self.config.get('node_ip', '')}\n"
                f"Hostname:  {self.config.get('hostname', '')}\n\n"
                f"Verify on first node:\n"
                f"  kubectl get nodes\n"
                f"  kubectl get pods -A | grep {self.config.get('hostname', '')}\n\n"
                f"Log Directory: /var/log/vdi-deploy/"
            )
        else:
            message = "Deployment complete."

        if install_key and self.mode == 1:
            message += (
                f"\n--- Control-Plane Join Key ---\n"
                f"  Install Key: {install_key}\n"
                f"  (第 2/3 台 Master 装机时填此 key 加入集群)"
            )

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
