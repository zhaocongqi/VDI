"""文本输入组件"""
import curses
from .helpers import calc_box_size, draw_box, wrap_text, init_colors, COLOR_SELECTED, COLOR_DIM


def inputbox(stdscr, title, text, default="", backtitle="VDI Cluster Offline Installer"):
    """文本输入框

    Args:
        stdscr: curses 标准屏幕
        title: 对话框标题
        text: 提示文本
        default: 默认值

    Returns:
        输入的文本 (str)，ESC/取消返回 None
    """
    init_colors()
    curses.curs_set(1)

    content_h = 10
    content_w = 60

    y, x, h, w = calc_box_size(stdscr, content_h, content_w)
    win = curses.newwin(h, w, y, x)
    win.keypad(True)

    text_lines = wrap_text(text, w - 4)
    input_row = min(len(text_lines) + 2, h - 4)
    input_w = w - 6

    value = list(default)
    cursor = len(default)
    scroll_offset = 0

    def _draw():
        win.clear()
        draw_box(win, title, backtitle)

        # 提示文本
        row = 1
        for line in text_lines[:input_row - 1]:
            if row < h - 3:
                try:
                    win.addstr(row, 2, line[:w - 4])
                except curses.error:
                    pass
            row += 1

        # 输入框
        display_start = max(0, cursor - input_w + 1)
        scroll_offset = display_start
        display = ''.join(value[scroll_offset:scroll_offset + input_w])
        try:
            win.addstr(input_row, 2, ' ' * (input_w + 2), COLOR_SELECTED)
            win.addstr(input_row, 3, display[:input_w])
        except curses.error:
            pass

        # 光标
        cursor_display = cursor - scroll_offset
        win.move(input_row, 3 + min(cursor_display, input_w - 1))

        # 底部提示
        try:
            hint = "<Enter> Confirm  <ESC> Cancel"
            win.addstr(h - 1, 2, hint[:w - 4], COLOR_DIM)
        except curses.error:
            pass

        win.refresh()

    _draw()

    while True:
        ch = win.getch()

        if ch in (10, 13, curses.KEY_ENTER):
            result = ''.join(value)
            return result if result else default

        elif ch == 27:  # ESC
            return None

        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if cursor > 0:
                value.pop(cursor - 1)
                cursor -= 1
                _draw()

        elif ch == curses.KEY_DC:  # Delete
            if cursor < len(value):
                value.pop(cursor)
                _draw()

        elif ch == curses.KEY_LEFT:
            if cursor > 0:
                cursor -= 1
                _draw()

        elif ch == curses.KEY_RIGHT:
            if cursor < len(value):
                cursor += 1
                _draw()

        elif ch == curses.KEY_HOME:
            cursor = 0
            _draw()

        elif ch == curses.KEY_END:
            cursor = len(value)
            _draw()

        elif ch == curses.KEY_IC:  # Insert - toggle insert mode (no-op, keep simple)
            pass

        elif 32 <= ch < 127:
            value.insert(cursor, chr(ch))
            cursor += 1
            _draw()

        # 忽略其他控制字符

    del win
