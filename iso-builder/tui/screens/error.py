"""错误界面"""
import curses
import logging
from widgets import menu, msgbox

logger = logging.getLogger("vdi-installer")


class ErrorScreen:
    """错误显示界面"""

    def __init__(self, error_message, solution=None, log_file=None):
        self.error_message = error_message
        self.solution = solution
        self.log_file = log_file or "/var/log/vdi-deploy/installer.log"

    def show(self, stdscr):
        """显示错误信息和操作建议

        Args:
            stdscr: curses 标准屏幕

        Returns:
            用户选择（retry/skip/log/exit）
        """
        message = f"Error: {self.error_message}\n\n"

        if self.solution:
            message += f"Suggestion:\n{self.solution}\n\n"
        else:
            message += (
                "Suggested actions:\n"
                "1. Check network connectivity and node reachability\n"
                "2. Check disk space and resource availability\n"
                "3. Check detailed logs for more information\n\n"
            )

        message += f"Log File: {self.log_file}"

        choice = menu(stdscr,
                      title="Deploy Failed",
                      text=message,
                      items=[
                          ("1", "Retry    - Re-run the failed step"),
                          ("2", "Skip     - Skip and continue"),
                          ("3", "View Log - Open log file"),
                          ("4", "Exit     - Quit the installer"),
                      ])

        if choice == "1":
            return "retry"
        elif choice == "2":
            return "skip"
        elif choice == "3":
            self._show_log(stdscr)
            return "log"
        else:
            return "exit"

    def _show_log(self, stdscr):
        """显示日志内容"""
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
                content = "".join(lines[-50:])
            msgbox(stdscr, title="Deploy Log", text=content)
        except FileNotFoundError:
            msgbox(stdscr, title="Deploy Log", text=f"Log file not found: {self.log_file}")
