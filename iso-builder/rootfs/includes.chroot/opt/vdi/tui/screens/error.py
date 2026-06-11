"""错误界面"""
import logging
from utils.whiptail_wrapper import Whiptail

logger = logging.getLogger("vdi-installer")


class ErrorScreen:
    """错误显示界面"""

    def __init__(self, error_message, solution=None, log_file=None):
        self.error_message = error_message
        self.solution = solution
        self.log_file = log_file or "/var/log/vdi-deploy/installer.log"

    def show(self):
        """显示错误信息和操作建议

        返回: 用户选择（retry/skip/log/exit）
        """
        wt = Whiptail(title="Deploy Failed", height=22, width=70)

        # 构建错误信息
        message = f"Error: {self.error_message}\n\n"

        # 可能的原因和建议
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

        choice = wt.menu(
            message,
            [
                ("1", "Retry - Re-run the failed step"),
                ("2", "Skip - Skip this step and continue"),
                ("3", "View Log - Open log file"),
                ("4", "Exit - Quit the installer"),
            ]
        )

        if choice == "1":
            return "retry"
        elif choice == "2":
            return "skip"
        elif choice == "3":
            self._show_log()
            return "log"
        else:
            return "exit"

    def _show_log(self):
        """显示日志内容"""
        wt = Whiptail(title="Deploy Log", height=25, width=80)
        try:
            with open(self.log_file, "r") as f:
                # 读取最后 50 行
                lines = f.readlines()
                content = "".join(lines[-50:])
            wt.msgbox(content, height=25, width=80)
        except FileNotFoundError:
            wt.msgbox(f"Log file not found: {self.log_file}")
