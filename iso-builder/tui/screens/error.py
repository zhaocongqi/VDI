"""错误界面"""
import curses
import logging
from widgets import menu, msgbox

logger = logging.getLogger("vdi-installer")


class ErrorScreen:
    """错误显示界面

    show() 返回 'retry' / 'skip' / 'exit'（已去除无意义的 'log'，
    View Log 选项看完日志后循环回菜单继续操作）。

    Args:
        error_message: 错误描述
        solution: 可选的处理建议
        log_file: 日志文件路径（供 View Log 读取）
        fatal: 致命异常时为 True，只显示 View Log/Exit（不让用户 retry
               一个 Python 异常，那没有意义）
    """

    def __init__(self, error_message, solution=None, log_file=None, fatal=False):
        self.error_message = error_message
        self.solution = solution
        self.log_file = log_file or "/var/log/vdi-deploy/installer.log"
        self.fatal = fatal

    def show(self, stdscr):
        """显示错误信息和操作建议

        返回: 'retry' / 'skip' / 'exit'
        """
        message = self._build_message()

        # 循环直到用户做出明确决定（retry/skip/exit）；
        # View Log 看完日志后 continue 回菜单继续选择
        while True:
            if self.fatal:
                items = [
                    ("1", "View Log - Open log file"),
                    ("2", "Exit     - Quit the installer"),
                ]
                choice = menu(stdscr, title="Installer Error", text=message, items=items)
                if choice == "1":
                    self._show_log(stdscr)
                    continue
                else:
                    return "exit"
            else:
                items = [
                    ("1", "Retry    - Re-run the failed step"),
                    ("2", "Skip     - Skip and continue"),
                    ("3", "View Log - Open log file"),
                    ("4", "Exit     - Quit the installer"),
                ]
                choice = menu(stdscr, title="Deploy Failed", text=message, items=items)

                if choice == "1":
                    return "retry"
                elif choice == "2":
                    return "skip"
                elif choice == "3":
                    self._show_log(stdscr)
                    continue
                else:
                    # choice == "4" 或 None（ESC/取消）都视为退出
                    return "exit"

    def _build_message(self):
        """构建错误信息文本"""
        m = f"Error: {self.error_message}\n\n"
        if self.solution:
            m += f"Suggestion:\n{self.solution}\n\n"
        else:
            m += (
                "Suggested actions:\n"
                "1. Check network connectivity and node reachability\n"
                "2. Check disk space and resource availability\n"
                "3. Use 'View Log' for detailed error output\n\n"
            )
        m += f"Log File: {self.log_file}"
        return m

    def _show_log(self, stdscr):
        """显示日志内容（按 Enter 返回，调用方循环回菜单）"""
        try:
            with open(self.log_file, "r") as f:
                lines = f.readlines()
                content = "".join(lines[-50:])
            msgbox(stdscr, title="Deploy Log", text=content)
        except FileNotFoundError:
            msgbox(stdscr, title="Deploy Log", text=f"Log file not found: {self.log_file}")
        except Exception as e:
            msgbox(stdscr, title="Deploy Log", text=f"Failed to read log: {e}")
