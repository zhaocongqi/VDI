"""消息框组件"""
import curses
from .helpers import calc_box_size, draw_box, wrap_text, init_colors, COLOR_DIM


def msgbox(stdscr, title, text, backtitle="VDI Cluster Offline Installer"):
    """消息框

    Args:
        stdscr: curses 标准屏幕
        title: 对话框标题
        text: 消息文本

    Returns:
        True（用户按 Enter 确认）
    """
    init_colors()
    curses.curs_set(0)

    text_lines = wrap_text(text, 66)
    content_h = max(8, len(text_lines) + 5)
    content_w = 70

    y, x, h, w = calc_box_size(stdscr, content_h, content_w)
    win = curses.newwin(h, w, y, x)
    win.keypad(True)

    def _draw():
        win.clear()
        draw_box(win, title, backtitle)

        # 消息文本（支持滚动）
        for i, line in enumerate(text_lines[:h - 4]):
            try:
                win.addstr(1 + i, 2, line[:w - 4])
            except curses.error:
                pass

        # 底部按钮
        btn_text = " [ OK ] "
        btn_x = (w - len(btn_text)) // 2
        try:
            win.addstr(h - 2, btn_x, btn_text, curses.A_REVERSE)
        except curses.error:
            pass

        # 提示
        try:
            hint = "<Enter> OK"
            win.addstr(h - 1, 2, hint[:w - 4], COLOR_DIM)
        except curses.error:
            pass

        win.refresh()

    _draw()

    while True:
        ch = win.getch()
        if ch in (10, 13, curses.KEY_ENTER, 27, ord('q')):
            break

    del win
    return True
