"""Yes/No 确认组件"""
import curses
from .helpers import calc_box_size, draw_box, wrap_text, init_colors, COLOR_SELECTED, COLOR_DIM


def yesno(stdscr, title, text, backtitle="VDI Cluster Offline Installer"):
    """是/否确认框

    Args:
        stdscr: curses 标准屏幕
        title: 对话框标题
        text: 提示文本

    Returns:
        True=Yes, False=No
    """
    init_colors()
    curses.curs_set(0)

    text_lines = wrap_text(text, 66)
    content_h = max(8, len(text_lines) + 5)
    content_w = 70

    y, x, h, w = calc_box_size(stdscr, content_h, content_w)
    win = curses.newwin(h, w, y, x)
    win.keypad(True)

    focus = 0  # 0=Yes, 1=No

    def _draw():
        win.clear()
        draw_box(win, title, backtitle)

        for i, line in enumerate(text_lines[:h - 4]):
            try:
                win.addstr(1 + i, 2, line[:w - 4])
            except curses.error:
                pass

        # 按钮
        btn_y = h - 2
        yes_text = " < Yes > "
        no_text = " < No > "
        total_w = len(yes_text) + len(no_text) + 2
        start_x = (w - total_w) // 2

        if focus == 0:
            win.addstr(btn_y, start_x, yes_text, COLOR_SELECTED)
            win.addstr(btn_y, start_x + len(yes_text) + 2, no_text)
        else:
            win.addstr(btn_y, start_x, yes_text)
            win.addstr(btn_y, start_x + len(yes_text) + 2, no_text, COLOR_SELECTED)

        try:
            hint = "← → Switch  <Enter> Confirm"
            win.addstr(h - 1, 2, hint[:w - 4], COLOR_DIM)
        except curses.error:
            pass

        win.refresh()

    _draw()

    while True:
        ch = win.getch()
        if ch in (curses.KEY_LEFT, ord('h')):
            focus = 0
            _draw()
        elif ch in (curses.KEY_RIGHT, ord('l')):
            focus = 1
            _draw()
        elif ch in (10, 13, curses.KEY_ENTER):
            return focus == 0
        elif ch == 27:  # ESC
            return False
        elif ch == ord('q'):
            return False

    del win
