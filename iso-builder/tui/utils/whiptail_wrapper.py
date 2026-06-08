"""whiptail TUI 组件封装

通过 subprocess 调用 whiptail，提供与 Ubuntu Server 安装器一致的外观。
"""
import subprocess
import logging

logger = logging.getLogger("vdi-installer")


class Whiptail:
    """whiptail 调用封装"""

    def __init__(self, title="VDI 离线部署", backtitle="VDI 集群离线部署工具 v1.0",
                 height=20, width=70):
        self.title = title
        self.backtitle = backtitle
        self.height = height
        self.width = width
        self.list_height = 10

    def _run(self, args, input_data=None):
        """执行 whiptail 命令"""
        cmd = [
            "whiptail",
            "--title", self.title,
            "--backtitle", self.backtitle,
            *args
        ]

        try:
            result = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                text=True
            )
            # whiptail 返回 0 表示确定，1 表示取消，255 表示 ESC
            return result.returncode, result.stdout
        except FileNotFoundError:
            logger.error("whiptail 未安装")
            return 255, ""

    def msgbox(self, message, height=None, width=None):
        """消息框"""
        h = height or self.height
        w = width or self.width
        rc, _ = self._run([
            "--msgbox", message, str(h), str(w)
        ])
        return rc == 0

    def yesno(self, message, height=None, width=None):
        """是/否确认框"""
        h = height or self.height
        w = width or self.width
        rc, _ = self._run([
            "--yesno", message, str(h), str(w)
        ])
        return rc == 0  # True=是, False=否

    def menu(self, text, items, height=None, width=None):
        """菜单选择

        items: [(tag, description), ...]
        返回: 选择的 tag，取消返回 None
        """
        h = height or self.height
        w = width or self.width
        args = ["--menu", text, str(h), str(w), str(self.list_height)]
        for tag, desc in items:
            args.extend([tag, desc])

        rc, output = self._run(args)
        if rc == 0:
            return output.strip()
        return None

    def inputbox(self, text, default="", height=None, width=None):
        """输入框

        返回: 输入的文本，取消返回 None
        """
        h = height or self.height
        w = width or self.width
        args = ["--inputbox", text, str(h), str(w), default]

        rc, output = self._run(args)
        if rc == 0:
            return output.strip()
        return None

    def passwordbox(self, text, height=None, width=None):
        """密码输入框

        返回: 输入的密码，取消返回 None
        """
        h = height or self.height
        w = width or self.width
        args = ["--passwordbox", text, str(h), str(w)]

        rc, output = self._run(args)
        if rc == 0:
            return output.strip()
        return None

    def checklist(self, text, items, height=None, width=None):
        """多选框

        items: [(tag, description, status), ...]  status="ON" or "OFF"
        返回: 选择的 tag 列表，取消返回 None
        """
        h = height or self.height
        w = width or self.width
        args = ["--checklist", text, str(h), str(w), str(self.list_height)]
        for tag, desc, status in items:
            args.extend([tag, desc, status])

        rc, output = self._run(args)
        if rc == 0:
            # whiptail 返回 "tag1" "tag2" 格式
            return [item.strip('"') for item in output.split() if item.strip('"')]
        return None

    def radiolist(self, text, items, height=None, width=None):
        """单选框

        items: [(tag, description, status), ...]  仅一个 status="ON"
        返回: 选择的 tag，取消返回 None
        """
        h = height or self.height
        w = width or self.width
        args = ["--radiolist", text, str(h), str(w), str(self.list_height)]
        for tag, desc, status in items:
            args.extend([tag, desc, status])

        rc, output = self._run(args)
        if rc == 0:
            return output.strip().strip('"')
        return None

    def gauge(self, text, percent, height=None, width=None):
        """进度条（非阻塞模式 - 仅更新进度）

        注意：gauge 需要持续输入，此处提供简化接口
        """
        # gauge 需要通过管道持续输入，此处为简化版本
        pass

    def infobox(self, message, height=None, width=None):
        """信息提示框（自动消失）"""
        h = height or self.height
        w = width or self.width
        self._run(["--infobox", message, str(h), str(w)])
