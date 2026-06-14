"""配置确认界面"""
import curses
import logging
from widgets import yesno

logger = logging.getLogger("vdi-installer")

MODE_NAMES = {
    1: "Master Node (Install OS + Deploy VDI Cluster)",
    2: "Worker Node (Install OS + Join existing cluster)",
}


class ConfirmScreen:
    """配置确认界面"""

    def __init__(self, config):
        self.config = config

    def show(self, stdscr):
        """显示配置摘要并请求确认

        Args:
            stdscr: curses 标准屏幕

        Returns:
            True=确认, False=取消
        """
        mode = self.config.get("mode", "Unknown")
        lines = [
            f"Deployment Mode: {MODE_NAMES.get(mode, mode)}",
            "",
            "--- Disk ---",
            f"  Install Disk:   {self.config.get('install_disk', '-')}",
            f"  Part Scheme:    {self.config.get('partition_scheme', '-')}",
            f"  Swap Size:      {self.config.get('swap_size', '-')}",
            "",
            "--- Network ---",
            f"  Hostname:       {self.config.get('hostname', '-')}",
            f"  Node IP:        {self.config.get('node_ip', '-')}/{self.config.get('netmask', '24')}",
            f"  Gateway:        {self.config.get('gateway', '-')}",
            f"  DNS:            {self.config.get('dns', '-')}",
        ]

        if mode == 1:
            lines.extend([
                "",
                "--- Cluster ---",
                f"  Node Role:      {self.config.get('role', '-')}",
                f"  VIP:            {self.config.get('vip', '-')}",
                f"  VIP Interface:  {self.config.get('vip_interface', '-')}",
                f"  Pod CIDR:       {self.config.get('pod_cidr', '-')}",
                f"  Service CIDR:   {self.config.get('svc_cidr', '-')}",
                f"  K8s Version:    {self.config.get('k8s_version', '-')}",
                "",
                "--- Storage ---",
                f"  LH Disk:        {self.config.get('longhorn_disk', '-')}",
                f"  Data Dir:       {self.config.get('longhorn_data_dir', '-')}",
                f"  Replicas:       {self.config.get('longhorn_replicas', '3')}",
            ])

        if mode == 2:
            lines.extend([
                "",
                "--- Join Config ---",
                f"  Master IP:      {self.config.get('master_ip', '-')}",
                f"  Join Method:    {self.config.get('join_method', '-')}",
            ])

        lines.extend([
            "",
            "Offline Resources: " + (
                "Detected (/cdrom/offline)" if self.config.get("offline_available") else "Not detected"
            ),
            "",
            "Confirm the above configuration to start deployment.",
        ])

        message = "\n".join(lines)
        return yesno(stdscr,
                     title="Confirm Configuration",
                     text=message)
