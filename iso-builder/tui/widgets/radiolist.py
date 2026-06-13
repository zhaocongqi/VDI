"""单选列表组件"""
import curses
from .helpers import calc_box_size, draw_box, wrap_text, init_colors, COLOR_SELECTED, COLOR_DIM


def radiolist(stdscr, title, text, items, backtitle="VDI Cluster Offline Installer"):
    """单选列表

    Args:
        stdscr: curses 标准屏幕
        title: 对话框标题
        text: 提示文本
        items: [(tag, description, selected), ...]  selected=True/False

    Returns:
        选中的 tag (str)，ESC/取消返回 None
    """
    init_colors()
    curses.curs_set(0)

    item_count = len(items)
    content_h = max(10, item_count + 7)
    content_w = 60

    # 解析 items，找到默认选中项
    tags = [t for t, _, _ in items]
    descs = [d for _, d, _ in items]
    selected_idx = 0
    for i, (_, _, s) in enumerate(items):
        if s == "ON" or s is True:
            selected_idx = i

    cursor = selected_idx

    y, x, h, w = calc_box_size(stdscr, content_h, content_w)
    win = curses.newwin(h, w, y, x)
    win.keypad(True)

    text_lines = wrap_text(text, w - 4)
    list_start = min(len(text_lines) + 2, h - 5)
    list_h = h - list_start - 3
    if list_h < 1:
        list_h = 1

    scroll = 0
    if cursor >= list_h:
        scroll = cursor - list_h + 1

    def _draw():
        win.clear()
        draw_box(win, title, backtitle)

        # 提示文本
        row = 1
        for line in text_lines[:list_start - 1]:
            if row < h - 3:
                try:
                    win.addstr(row, 2, line[:w - 4])
                except curses.error:
                    pass
            row += 1

        # 单选项
        for i in range(list_h):
            idx = scroll + i
            if idx >= item_count:
                break
            row = list_start + i

            # ( ) 或 (*) 单选符号
            radio = "(*)" if idx == selected_idx else "( )"
            line = f" {radio} {tags[idx]}  {descs[idx]}"
            if len(line) > w - 4:
                line = line[:w - 5] + "~"

            if idx == cursor:
                try:
                    win.addstr(row, 1, line[:w - 2], COLOR_SELECTED)
                except curses.error:
                    pass
            else:
                try:
                    win.addstr(row, 1, line[:w - 2])
                except curses.error:
                    pass

        # 提示
        try:
            hint = "<Enter> Select  <Space> Toggle  <ESC> Cancel"
            win.addstr(h - 1, 2, hint[:w - 4], COLOR_DIM)
        except curses.error:
            pass

        win.refresh()

    _draw()

    while True:
        ch = win.getch()

        if ch in (curses.KEY_UP, ord('k')):
            if cursor > 0:
                cursor -= 1
                if cursor < scroll:
                    scroll = cursor
                _draw()
        elif ch in (curses.KEY_DOWN, ord('j')):
            if cursor < item_count - 1:
                cursor += 1
                if cursor >= scroll + list_h:
                    scroll = cursor - list_h + 1
                _draw()
        elif ch == ord(' '):
            selected_idx = cursor
            _draw()
        elif ch in (10, 13, curses.KEY_ENTER):
            return tags[selected_idx]
        elif ch == 27:
            return None
        elif ch == ord('q'):
            return None

    del win
