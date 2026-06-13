"""whiptail TUI 组件封装

通过 subprocess.run() 调用 whiptail，并在调用前后保存/恢复终端设置。

关键设计：
- 使用 subprocess.run() 替代 os.system()，避免 /bin/sh -c 中间层干扰终端状态
- 调用前通过 termios 保存终端属性，调用后恢复，防止 SLang/newt 残留 raw mode
- stdout 重定向到临时文件（捕获用户选择），stderr 保留为子进程继承的终端 fd
- 调用前后完整重置终端状态（scroll region + ACS + 属性 + 清屏 + 光标归位），
  解决 TERM=linux 无 alternate screen buffer 问题：Linux fbcon 不支持 smcup/rmcup，
  SLang 直接在主屏幕 buffer 渲染，且 CUP 相对于 scroll region 而非屏幕原点，
  退出后必须重置全部状态才能避免后续对话框渲染位置偏移和字符混乱
"""
import os
import re
import shlex
import subprocess
import sys
import tempfile
import logging
import termios
import tty

logger = logging.getLogger("vdi-installer")

# ANSI 转义码匹配模式（用于清理输出）
ANSI_RE = re.compile(
    r'\x1b\[\??[0-9;]*[a-zA-Z]'
    r'|\x1b[\(\)][B0UK]'
    r'|\x1b[><]'
    r'|\x1b.'
    r'|[\x00-\x1f\x7f]'
)


def _strip_ansi(text):
    """移除 ANSI 转义码和控制字符，返回纯文本"""
    cleaned = ANSI_RE.sub('', text)
    # 二次清理：移除残留的非打印字符（ASCII 0-31, 127）
    cleaned = ''.join(c for c in cleaned if c >= ' ' or c in '\t\n')
    return cleaned.strip()


def _save_terminal_state(fd):
    """保存终端属性，返回原始设置"""
    try:
        return termios.tcgetattr(fd)
    except termios.error:
        return None


def _restore_terminal_state(fd, original_attrs):
    """恢复终端属性到原始设置

    若 original_attrs 为 None（保存失败），则强制恢复为 cooked mode。
    SLang/newt 退出后可能遗留 raw mode，必须确保恢复 ICANON + ECHO，
    否则后续 bash 交互无法正常工作。
    """
    if original_attrs is None:
        _force_cooked_mode(fd)
        return
    try:
        # 先刷出待输出数据
        termios.tcdrain(fd)
        # 恢复原始终端属性
        termios.tcsetattr(fd, termios.TCSANOW, original_attrs)
        # 二次确认：如果恢复后仍处于 raw mode（SLang 可能篡改保存的属性），
        # 强制恢复 cooked mode
        current = termios.tcgetattr(fd)
        if not (current[3] & termios.ICANON):
            _force_cooked_mode(fd)
    except termios.error:
        _force_cooked_mode(fd)


def _force_cooked_mode(fd):
    """强制将终端设为 cooked mode（canonical + echo）

    当 SLang/newt 遗留 raw mode 时使用，确保 bash 能正常读取输入。
    """
    try:
        attrs = list(termios.tcgetattr(fd))
        attrs[3] |= termios.ICANON | termios.ECHO | termios.ECHOE | termios.ECHOK
        attrs[3] &= ~termios.ECHONL
        attrs[0] &= ~(termios.BRKINT | termios.INPCK | termios.ISTRIP)
        attrs[0] |= termios.ICRNL
        attrs[1] |= termios.OPOST
        attrs[6][termios.VMIN] = 1
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except termios.error:
        pass


def _reset_terminal(fd):
    r"""完整重置终端状态：scroll region + 属性 + 字符集 + 清屏 + 光标归位

    SLang/newt 在渲染对话框时会修改多项终端状态：
    1. Scroll Region (DECSTBM \E[r) — SLang 用 csr 为列表区域设定滚动范围
    2. Character Set — SLang 用 ^N (SO) 切换到 ACS 画边框字符
    3. Attributes — 颜色、粗体、反色等

    退出时 SLang_reset_tty() 仅恢复 termios 属性（raw mode 等），
    不重置通过转义序列设置的 scroll region 和字符集。

    关键问题：Linux fbcon 上 \E[H (CUP) 的光标定位相对于 scroll region 顶部，
    而非屏幕绝对原点。如果 scroll region 未重置，\E[H 会定位到错误位置，
    导致后续对话框渲染位置偏移，产生字符重叠和混乱。

    完整重置序列（对齐 linux terminfo 的 sgr0 + clear + csr）：
      \E[r       — DECSTBM 无参数：重置 scroll region 为全屏
      \E[0m\017  — sgr0：重置属性 + 退出 ACS（\017 = Ctrl-O = SI = rmacs）
      \E[2J      — ED 2：清除整个屏幕（不受 scroll region 影响）
      \E[H       — CUP(1,1)：光标归位（scroll region 已重置，故为绝对原点）
    """
    if fd < 0:
        return
    try:
        os.write(fd, b'\033[r\033[0m\017\033[2J\033[H')
    except OSError:
        pass


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

        使用 subprocess.run() 直接调用 whiptail：
        - stdin 继承父进程（终端），whiptail 通过此 fd 读取键盘输入
        - stdout 重定向到临时文件（捕获用户选择结果）
        - stderr 显式指向 /dev/tty（SLang 通过此 fd 渲染 TUI）
          即使父进程 stderr 被重定向（如 profile.d 中 2>>log），
          SLang 也通过直接打开 /dev/tty 确保 TUI 渲染正确
        - 调用前后保存/恢复终端属性，防止 SLang 残留 raw mode
        - 调用前后完整重置终端状态（scroll region + ACS + 属性 + 清屏 + 光标归位），
          解决 TERM=linux 无 alternate screen buffer 问题：
          Linux fbcon 的 CUP 相对于 scroll region 而非屏幕原点，
          SLang 退出后若不重置 scroll region，后续对话框渲染位置偏移
        """
        cmd = [
            "whiptail",
            "--clear",        # whiptail 退出时清屏（在 linux console 上清除主 buffer 残影）
            "--notags",
            "--title", self.title,
            "--backtitle", self.backtitle,
            *args
        ]

        tmpfile = tempfile.mktemp(prefix='.whiptail_')

        # 获取终端 fd
        tty_fd = -1
        try:
            tty_fd = sys.stdin.fileno()
            if not os.isatty(tty_fd):
                tty_fd = -1
        except (ValueError, OSError):
            pass

        # 保存终端属性
        original_attrs = None
        if tty_fd >= 0:
            original_attrs = _save_terminal_state(tty_fd)

        # 确保 stderr 指向真实终端
        # SLang/newt 通过 stderr 写入 TUI 渲染码，如果 stderr 不指向终端
        # （如被 profile.d hook 重定向到日志文件），SLang 会退而写入 stdout，
        # 导致 TUI 渲染码与选择结果混合，产生字符重复/混乱
        stderr_target = None  # 默认继承
        stderr_fd = -1
        try:
            tty_path = os.ttyname(sys.stderr.fileno())
            # stderr 已经指向终端，直接用 stderr fd 做清屏
            try:
                stderr_fd = sys.stderr.fileno()
            except (ValueError, OSError):
                pass
        except (OSError, ValueError):
            # stderr 不指向终端 — 打开 /dev/tty 作为替代
            try:
                stderr_target = open('/dev/tty', 'w')
                stderr_fd = stderr_target.fileno()
            except OSError:
                pass  # 无法打开 /dev/tty，使用默认行为

        # 调用前：完整重置终端状态，确保 SLang 在干净的画面上渲染
        _reset_terminal(stderr_fd)

        try:
            with open(tmpfile, 'w') as tmp_out:
                result = subprocess.run(
                    cmd,
                    stdin=None,            # 继承父进程 stdin（终端）
                    stdout=tmp_out,        # 选择结果写入临时文件
                    stderr=stderr_target,  # 指向 /dev/tty（或 None=继承）
                )

            retcode = result.returncode

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
            # 调用后：完整重置终端状态，消除 SLang 残留的渲染内容和状态
            # 重置 scroll region + ACS 字符集 + 属性 + 清屏 + 光标归位
            _reset_terminal(stderr_fd)

            # 恢复终端属性（关键：防止 SLang 残留 raw mode）
            if tty_fd >= 0:
                _restore_terminal_state(tty_fd, original_attrs)

            # 关闭显式打开的 /dev/tty fd
            if stderr_target is not None:
                try:
                    stderr_target.close()
                except OSError:
                    pass

            # 清理临时文件
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
        # 二次 ANSI 清理：即使 _run() 已清理过，这里也再清理一次确保安全
        cleaned = _strip_ansi(output)

        # 1. 整个输出就是有效 tag（正常情况）
        if cleaned in tags:
            return cleaned

        # 2. 从输出末尾逐行查找有效 tag
        for line in reversed(cleaned.split('\n')):
            line = line.strip()
            if line in tags:
                return line

        # 3. 从输出中查找独立的有效 tag（前后非数字字符）
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
