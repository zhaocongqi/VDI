"""部署进度条组件

基于 curses 绘制，不依赖外部进程（whiptail --gauge），
从根源避免终端状态损坏问题。

布局（h=22, w=70 典型）：
  行 0       边框 + 标题
  行 1       [████████████░░░░░░░░░░] 45%   进度条
  行 2       （空行分隔）
  行 3-6     步骤列表（固定 4 行，带滚动，当前步骤始终可见）
  行 7       ── Live Log ─────────── 分隔线
  行 8+      日志面板（自适应高度，最新行高亮，长行截断尾部 …）
  行 h-1     底部提示 + backtitle
"""
import curses
import threading
from .helpers import (calc_box_size, draw_box, init_colors,
                      COLOR_OK, COLOR_FAIL, COLOR_WARN, COLOR_BAR, COLOR_BAR_BG,
                      COLOR_DIM, COLOR_HIGHLIGHT)


class ProgressBar:
    """curses 进度条

    用法:
        pb = ProgressBar(stdscr, "Deploy Progress", steps,
                         log_source=lambda n: engine.get_recent_logs(n))
        pb.update(0, "System Init")
        # ... 执行步骤（引擎实时填缓冲，UI 每 0.3s 取快照渲染）...
        pb.set_step_result(0, "ok")
        pb.finish()
    """

    def __init__(self, stdscr, title, step_names,
                 backtitle="VDI Cluster Offline Installer", log_source=None):
        """
        Args:
            stdscr: curses 标准屏幕
            title: 对话框标题
            step_names: 步骤名称列表
            backtitle: 底部标题
            log_source: 可选，Callable[[int], list[str]]，返回最近 N 行实时日志。
                        传入后日志面板显示；不传则日志面板留空。
        """
        self.stdscr = stdscr
        self.title = title
        self.backtitle = backtitle
        self.step_names = step_names
        self.total = len(step_names)
        self.current_step = 0
        self.current_percent = 0
        self.step_status = {}  # idx -> "ok" / "fail" / "skip"
        self.running = True
        self._log_source = log_source

        init_colors()
        curses.curs_set(0)

        # 窗口放大到能容纳日志面板（calc_box_size 会钳到 max_h-2）
        content_h = max(22, self.total + 8)
        content_w = 70
        self.y, self.x, self.h, self.w = calc_box_size(stdscr, content_h, content_w)

        # 布局参数
        self.list_start = 3
        self.list_h = 4                       # 固定 4 行步骤列表（带滚动）
        self.log_sep_y = 7                    # "── Live Log ──" 分隔线行
        self.log_start = 8                    # 日志面板起始行
        # 日志面板高度：边框(2) + 进度条(1) + 空行(1) + 步骤(4) + 分隔线(1) + 底部提示(1) = 10
        self.log_h = max(3, self.h - 10)
        self.scroll = 0
        self.win = curses.newwin(self.h, self.w, self.y, self.x)
        self.win.keypad(True)
        self._lock = threading.Lock()
        self._draw()

    def update(self, step_idx, step_name=None, percent=None):
        """更新进度"""
        with self._lock:
            self.current_step = step_idx
            if step_name:
                self.step_names[step_idx] = step_name
            if percent is not None:
                self.current_percent = percent
            else:
                self.current_percent = int((step_idx / self.total) * 100) if self.total else 0
            # 确保当前步骤在可视区
            if step_idx >= self.scroll + self.list_h:
                self.scroll = step_idx - self.list_h + 1
            if step_idx < self.scroll:
                self.scroll = step_idx
            self._draw()

    def set_step_result(self, step_idx, result):
        """标记步骤完成状态

        Args:
            result: "ok" / "fail" / "skip"（兼容旧 bool: True->"ok", False->"fail"）
        """
        if result is True:
            result = "ok"
        elif result is False:
            result = "fail"
        with self._lock:
            self.step_status[step_idx] = result
            self._draw()

    def clear_step_result(self, step_idx):
        """清除步骤状态标记（retry 前调用，让该步重新显示 --> ）"""
        with self._lock:
            self.step_status.pop(step_idx, None)
            self._draw()

    def finish(self, success=True):
        """完成进度条"""
        with self._lock:
            self.running = False
            self.current_percent = 100 if success else self.current_percent
            self._draw()

    def _draw(self):
        """绘制进度界面（5 段布局）"""
        self.win.clear()
        draw_box(self.win, self.title, self.backtitle)

        # (1) 进度条 —— 行 1
        bar_y = 1
        bar_w = self.w - 8   # 右侧留 6 列给 "NNN%"
        filled = int(bar_w * self.current_percent / 100)
        try:
            self.win.addstr(bar_y, 2, ' ' * bar_w, COLOR_BAR_BG)
            if filled > 0:
                self.win.addstr(bar_y, 2, ' ' * filled, COLOR_BAR)
            self.win.addstr(bar_y, bar_w + 2, f" {self.current_percent:3d}%", COLOR_HIGHLIGHT)
        except curses.error:
            pass

        # (2) 步骤列表 —— 行 3..6
        for i in range(self.list_h):
            idx = self.scroll + i
            if idx >= self.total:
                break
            row = self.list_start + i
            name = self.step_names[idx] if idx < len(self.step_names) else "?"

            if idx in self.step_status:
                st = self.step_status[idx]
                if st == "ok":
                    marker, color = "  [OK]  ", COLOR_OK
                elif st == "skip":
                    marker, color = " [SKIP] ", COLOR_WARN
                else:  # fail
                    marker, color = " [FAIL] ", COLOR_FAIL
            elif idx == self.current_step:
                marker, color = "  -->   ", COLOR_HIGHLIGHT
            else:
                marker, color = "        ", 0

            line = f"{marker}{name}"
            if len(line) > self.w - 4:
                line = line[:self.w - 5] + "~"
            try:
                self.win.addstr(row, 1, line[:self.w - 2], color)
            except curses.error:
                pass

        # (3) 日志分隔线 —— 行 7
        log_title = " Live Log "
        left_w = self.w - 4 - len(log_title)
        if left_w > 0:
            sep = "─" * (left_w // 2) + log_title + "─" * (left_w - left_w // 2)
            try:
                self.win.addstr(self.log_sep_y, 2, sep[:self.w - 4], COLOR_DIM)
            except curses.error:
                pass

        # (4) 日志面板 —— 行 8..8+log_h-1
        lines = []
        if self._log_source:
            try:
                lines = self._log_source(self.log_h) or []
            except Exception:
                lines = []
        # 不足 log_h 行时顶部补空（最新行在底部，像 tail -f）
        padded = [""] * (self.log_h - len(lines)) + lines
        max_col = self.w - 4
        for i, raw in enumerate(padded):
            row = self.log_start + i
            if not raw:
                continue
            if len(raw) > max_col:
                text = raw[:max_col - 1] + "…"
            else:
                text = raw
            try:
                # 最新一行（底部）高亮，其余 dim
                is_latest = (i == self.log_h - 1) and bool(lines)
                attr = COLOR_HIGHLIGHT if is_latest else COLOR_DIM
                self.win.addstr(row, 2, text[:self.w - 2], attr)
            except curses.error:
                pass

        # (5) 底部提示 —— 行 h-1
        try:
            hint = "<ESC> Cancel" if self.running else "<Enter> Continue"
            self.win.addstr(self.h - 1, 2, hint[:self.w - 4], COLOR_DIM)
        except curses.error:
            pass

        self.win.refresh()

    def close(self):
        """关闭进度条窗口"""
        try:
            self.win.clear()
            self.win.refresh()
        except Exception:
            pass
