"""欢迎界面 - 选择部署模式"""
import curses
import logging
from widgets import menu

logger = logging.getLogger("vdi-installer")

MODES = [
    ("1", "Fresh Install - Install Ubuntu OS + VDI Cluster"),
    ("2", "Append Deploy - Deploy VDI Cluster on existing OS"),
    ("3", "Join Node - Add Worker node to existing cluster"),
    ("4", "PXE Server - Start PXE server for network install"),
]


class WelcomeScreen:
    """欢迎界面，选择部署模式"""

    def show(self, stdscr):
        """显示部署模式选择菜单

        Args:
            stdscr: curses 标准屏幕

        Returns:
            模式编号 (1-4)，取消返回 None
        """
        text = (
            "Select deployment mode:\n\n"
            "Mode 1: Install Ubuntu on bare metal, then deploy full VDI cluster (Master)\n"
            "Mode 2: Ubuntu already installed, deploy VDI cluster directly (Master)\n"
            "Mode 3: Join this node as Worker to an existing VDI cluster\n"
            "Mode 4: Configure this node as PXE server for other nodes"
        )

        choice = menu(stdscr,
                      title="VDI Cluster Offline Installer v1.0",
                      text=text,
                      items=MODES,
                      backtitle="VDI Cluster Offline Deploy")

        if choice is None:
            return None

        mode = int(choice)
        logger.info(f"用户选择部署模式: {mode} ({dict(MODES)[choice]})")
        return mode
