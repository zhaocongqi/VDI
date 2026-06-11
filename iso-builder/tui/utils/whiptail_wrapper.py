"""whiptail TUI 组件封装

通过 os.system() + shell 重定向调用 whiptail。
关键：不能用 subprocess.PIPE 捕获 stdout，因为 whiptail 的 SLang 库
会将 TUI 转义码写入 stdout，与用户选择结果混合在一起导致解析失败。

解决方案：
- 使用 shell 重定向将 stdout（选择结果）写入临时文件
- SLang 通过 /dev/tty 直接访问终端进行 TUI 渲染和键盘输入
- stderr 重定向到 /dev/tty，确保错误信息可见
"""
import os
import re
import shlex
import tempfile
import logging

logger = logging.getLogger("vdi-installer")

# ANSI 转义码匹配模式（用于清理输出）
# 覆盖：CSI 序列、CSI ? 序列、两字节 ESC 序列、控制字符
ANSI_RE = re.compile(r'\x1b\[\??[0-9;]*[a-zA-Z]|\x1b[\(\)][B0UK]|\x1b[><]|\x1b.|[\x00-\x1f\x7f]')


def _strip_ansi(text):
    """移除 ANSI 转义码和控制字符，返回纯文本"""
    cleaned = ANSI_RE.sub('', text)
    # 二次清理：移除残留的非打印字符（ASCII 0-31, 127）
    cleaned = ''.join(c for c in cleaned if c >= ' ' or c in '\t\n')
    return cleaned.strip()


class Whiptail:
    """whiptail 调用封装"""

    def __init__(self, title="VDI Offline Deploy", backtitle="VDI Cluster Offline Installer v1.0",
                 height=20, width=70):
        self.title = title
        self.backtitle = backtitle
        self.height = height
        self.width = width
        self.list_height = 10

    def _run(self, args, input_data=None):
        """执行 whiptail 命令

        使用 os.system() + shell 重定向：
        - stdout → 临时文件（捕获用户选择结果）
        - stderr → /dev/tty（错误信息显示在终端）
        - stdin → 终端（SLang 通过 /dev/tty 直接读取键盘输入）
        """
        cmd = [
            "whiptail",
            "--notags",
            "--clear",
            "--title", self.title,
            "--backtitle", self.backtitle,
            *args
        ]

        tmpfile = tempfile.mktemp(prefix='.whiptail_')

        # 构建 shell 命令：stdout → 文件，stderr → 终端
        # SLang 直接打开 /dev/tty 进行 TUI 渲染和键盘输入，不依赖 stdin fd
        shell_cmd = ' '.join(shlex.quote(c) for c in cmd)
        full_cmd = f'{shell_cmd} >{shlex.quote(tmpfile)} 2>/dev/tty'

        try:
            retcode = os.system(full_cmd)

            # 转换 os.system() 的返回值格式
            if os.WIFEXITED(retcode):
                retcode = os.WEXITSTATUS(retcode)
            else:
                retcode = 255

            # 从临时文件读取选择结果
            output = ""
            if os.path.exists(tmpfile):
                with open(tmpfile) as f:
                    raw = f.read()
                # 清理 ANSI 转义码（SLang 可能将部分渲染码混入 stdout）
                output = _strip_ansi(raw)

            return retcode, output

        except Exception as e:
            logger.error(f"whiptail call exception: {e}")
            return 255, ""
        finally:
            try:
                os.unlink(tmpfile)
            except OSError:
                pass

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
            return self._extract_tag(output, items)
        return None

    def _extract_tag(self, output, items):
        """从 whiptail 输出中鲁棒地提取选择 tag

        SLang 可能在 stdout 中混入 TUI 渲染文本，
        需要从清理后的输出中精确提取有效 tag。
        """
        tags = {tag for tag, _ in items}
        cleaned = output.strip()

        # 1. 整个输出就是有效 tag（正常情况）
        if cleaned in tags:
            return cleaned

        # 2. 从输出末尾逐行查找有效 tag
        for line in reversed(cleaned.split('\n')):
            line = line.strip()
            if line in tags:
                return line

        # 3. 从输出中查找独立的有效 tag（前后非数字字符）
        import re
        for match in re.finditer(r'(?:^|\s|[^\d])(\d+)(?:\s|$|[^\d])', cleaned):
            candidate = match.group(1)
            if candidate in tags:
                return candidate

        # 4. 兜底：返回最后一行
        logger.warning(f"无法从 whiptail 输出中提取有效 tag: {repr(cleaned[:200])}")
        last = cleaned.split('\n')[-1].strip() if cleaned else None
        return last

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
            # whiptail 返回 "tag1" "tag2" 格式，提取引号内的 tag
            tags = {tag for tag, _, _ in items}
            result = [item.strip('"') for item in output.split()
                      if item.strip('"') in tags]
            return result if result else None
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
