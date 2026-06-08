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
        wt = Whiptail(title="✗ 部署失败", height=22, width=70)

        # 构建错误信息
        message = f"错误信息: {self.error_message}\n\n"

        # 可能的原因和建议
        if self.solution:
            message += f"建议操作:\n{self.solution}\n\n"
        else:
            message += (
                "建议操作:\n"
                "1. 检查网络连接和节点可达性\n"
                "2. 检查磁盘空间和资源是否充足\n"
                "3. 查看详细日志获取更多信息\n\n"
            )

        message += f"日志文件: {self.log_file}"

        choice = wt.menu(
            message,
            [
                ("1", "重试 - 重新执行失败的步骤"),
                ("2", "跳过 - 跳过此步骤继续"),
                ("3", "查看日志 - 打开日志文件"),
                ("4", "退出 - 退出安装器"),
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
        wt = Whiptail(title="部署日志", height=25, width=80)
        try:
            with open(self.log_file, "r") as f:
                # 读取最后 50 行
                lines = f.readlines()
                content = "".join(lines[-50:])
            wt.msgbox(content, height=25, width=80)
        except FileNotFoundError:
            wt.msgbox(f"日志文件不存在: {self.log_file}")
