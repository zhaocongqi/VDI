"""部署进度条组件

基于 curses 绘制，不依赖外部进程（whiptail --gauge），
从根源避免终端状态损坏问题。
"""
import curses
import threading
import time
from .helpers import calc_box_size, draw_box, init_colors, COLOR_OK, COLOR_FAIL, COLOR_BAR, COLOR_BAR_BG, COLOR_DIM, COLOR_HIGHLIGHT


class ProgressBar:
    """curses 进度条

    用法:
        pb = ProgressBar(stdscr, "Deploy Progress", steps)
        pb.update(0, "System Init")
        # ... 执行步骤 ...
        pb.update(1, "Deploy K8s Cluster")
        pb.finish()
    """

    def __init__(self, stdscr, title, step_names, backtitle="VDI Cluster Offline Installer"):
        """
        Args:
            stdscr: curses 标准屏幕
            title: 对话框标题
            step_names: 步骤名称列表
            backtitle: 底部标题
        """
        self.stdscr = stdscr
        self.title = title
        self.backtitle = backtitle
        self.step_names = step_names
        self.total = len(step_names)
        self.current_step = 0
        self.current_percent = 0
        self.step_status = {}  # idx -> True/False
        self.running = True

        init_colors()
        curses.curs_set(0)

        content_h = max(12, self.total + 8)
        content_w = 70
        self.y, self.x, self.h, self.w = calc_box_size(stdscr, content_h, content_w)
        self.list_start = 3
        self.list_h = min(self.total, self.h - 7)
        self.scroll = 0
        self.win = curses.newwin(self.h, self.w, self.y, self.x)
        self.win.keypad(True)
        self._lock = threading.Lock()
        self._draw()

    def update(self, step_idx, step_name=None, percent=None):
        """更新进度

        Args:
            step_idx: 当前步骤索引
            step_name: 步骤名称（可选，覆盖默认）
            percent: 百分比（可选，自动计算）
        """
        with self._lock:
            self.current_step = step_idx
            if step_name:
                self.step_names[step_idx] = step_name
            if percent is not None:
                self.current_percent = percent
            else:
                self.current_percent = int((step_idx / self.total) * 100)
            # 确保滚动可见
            if step_idx >= self.scroll + self.list_h:
                self.scroll = step_idx - self.list_h + 1
            if step_idx < self.scroll:
                self.scroll = step_idx
            self._draw()

    def set_step_result(self, step_idx, success):
        """标记步骤完成状态"""
        with self._lock:
            self.step_status[step_idx] = success
            self._draw()

    def finish(self, success=True):
        """完成进度条"""
        with self._lock:
            self.running = False
            self.current_percent = 100 if success else self.current_percent
            self._draw()

    def wait_cancel(self):
        """等待用户按 ESC 取消（非阻塞检查用）

        Returns:
            True 如果用户请求取消
        """
        self.win.timeout(0)
        try:
            ch = self.win.getch()
            if ch == 27 or ch == ord('q'):
                return True
        except curses.error:
            pass
        finally:
            self.win.timeout(-1)
        return False

    def _draw(self):
        """绘制进度界面"""
        self.win.clear()
        draw_box(self.win, self.title, self.backtitle)

        # 进度条
        bar_y = 1
        bar_w = self.w - 6
        filled = int(bar_w * self.current_percent / 100)

        try:
            self.win.addstr(bar_y, 2, ' ' * bar_w, COLOR_BAR_BG)
            if filled > 0:
                self.win.addstr(bar_y, 2, ' ' * filled, COLOR_BAR)
            self.win.addstr(bar_y, bar_w + 2, f" {self.current_percent:3d}%", COLOR_HIGHLIGHT)
        except curses.error:
            pass

        # 步骤列表
        for i in range(self.list_h):
            idx = self.scroll + i
            if idx >= self.total:
                break
            row = self.list_start + i
            name = self.step_names[idx] if idx < len(self.step_names) else "?"

            if idx in self.step_status:
                status = self.step_status[idx]
                marker = "  [OK] " if status else " [FAIL]"
                color = COLOR_OK if status else COLOR_FAIL
            elif idx == self.current_step:
                marker = "  -->  "
                color = COLOR_HIGHLIGHT
            else:
                marker = "       "
                color = 0

            line = f"{marker}{name}"
            if len(line) > self.w - 4:
                line = line[:self.w - 5] + "~"

            try:
                self.win.addstr(row, 1, line[:self.w - 2], color)
            except curses.error:
                pass

        # 底部提示
        try:
            hint = "<ESC> Cancel" if self.running else "<Enter> Continue"
            self.win.addstr(self.h - 1, 2, hint[:self.w - 4], COLOR_DIM)
        except curses.error:
            pass

        self.win.refresh()

    def close(self):
        """关闭进度条窗口"""
        try:
            del self.win
        except Exception:
            pass
