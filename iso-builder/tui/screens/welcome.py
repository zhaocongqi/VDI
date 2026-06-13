"""欢迎界面 - 选择部署模式"""
import curses
import logging
from widgets import menu

logger = logging.getLogger("vdi-installer")

MODES = [
    ("1", "Fresh Install  - OS + VDI Cluster (Master)"),
    ("2", "Append Deploy  - VDI Cluster only (Master)"),
    ("3", "Join Node      - Add Worker to cluster"),
    ("4", "PXE Server     - Network boot service"),
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
        text = "Select deployment mode:"

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
