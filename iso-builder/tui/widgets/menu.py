"""菜单选择组件"""
import curses
from .helpers import calc_box_size, draw_box, wrap_text, init_colors, COLOR_SELECTED, COLOR_DIM


def menu(stdscr, title, text, items, backtitle="VDI Cluster Offline Installer", selected=0):
    """列表选择菜单

    Args:
        stdscr: curses 标准屏幕
        title: 对话框标题
        text: 说明文本
        items: [(tag, description), ...]
        backtitle: 底部标题
        selected: 默认选中索引

    Returns:
        选中的 tag (str)，ESC/取消返回 None
    """
    init_colors()
    curses.curs_set(0)

    item_count = len(items)
    # 根据最长描述计算所需宽度
    max_desc = max(len(tag) + len(desc) + 6 for tag, desc in items)
    content_w = max(70, min(max_desc + 4, 78))
    content_h = max(12, item_count + 7)

    while True:
        y, x, h, w = calc_box_size(stdscr, content_h, content_w)
        win = curses.newwin(h, w, y, x)
        win.keypad(True)
        win.bkgd(' ', COLOR_SELECTED & ~curses.A_BOLD)

        # 计算文本区和列表区
        text_lines = wrap_text(text, w - 4)
        # 文本区最多占一半高度，保证列表区至少有 item_count 行
        max_text_rows = max(1, (h - item_count - 4) // 2)
        text_lines = text_lines[:max_text_rows]
        list_start = len(text_lines) + 2
        list_h = min(item_count, h - list_start - 2)
        if list_h < 1:
            list_h = 1

        # 滚动偏移
        scroll = 0
        if selected >= list_h:
            scroll = selected - list_h + 1

        top_idx = selected

        def _draw():
            win.clear()
            draw_box(win, title, backtitle)

            # 绘制说明文本
            row = 1
            for line in text_lines:
                if row < list_start - 1:
                    try:
                        win.addstr(row, 2, line[:w - 4])
                    except curses.error:
                        pass
                row += 1

            # 绘制列表项
            for i in range(list_h):
                idx = scroll + i
                if idx >= item_count:
                    break
                row = list_start + i
                tag, desc = items[idx]

                marker = ">" if idx == top_idx else " "
                line = f" {marker} {tag}  {desc}"

                if len(line) > w - 4:
                    line = line[:w - 5] + "~"

                if idx == top_idx:
                    try:
                        win.addstr(row, 1, line[:w - 2], COLOR_SELECTED)
                    except curses.error:
                        pass
                else:
                    try:
                        win.addstr(row, 1, line[:w - 2])
                    except curses.error:
                        pass

            # 底部提示
            try:
                hint = "<Enter> Select  <ESC> Cancel  ↑↓ Move"
                win.addstr(h - 1, 2, hint[:w - 4], COLOR_DIM)
            except curses.error:
                pass

            win.refresh()

        _draw()

        while True:
            ch = win.getch()
            if ch in (curses.KEY_UP, ord('k')):
                if top_idx > 0:
                    top_idx -= 1
                    if top_idx < scroll:
                        scroll = top_idx
                    _draw()
            elif ch in (curses.KEY_DOWN, ord('j')):
                if top_idx < item_count - 1:
                    top_idx += 1
                    if top_idx >= scroll + list_h:
                        scroll = top_idx - list_h + 1
                    _draw()
            elif ch in (curses.KEY_PPAGE, ord('K')):
                top_idx = max(0, top_idx - list_h)
                scroll = max(0, scroll - list_h)
                _draw()
            elif ch in (curses.KEY_NPAGE, ord('J')):
                top_idx = min(item_count - 1, top_idx + list_h)
                scroll = min(max(0, item_count - list_h), scroll + list_h)
                _draw()
            elif ch in (curses.KEY_HOME, ord('g')):
                top_idx = 0
                scroll = 0
                _draw()
            elif ch in (curses.KEY_END, ord('G')):
                top_idx = item_count - 1
                scroll = max(0, item_count - list_h)
                _draw()
            elif ch in (10, 13, curses.KEY_ENTER):
                return items[top_idx][0]
            elif ch == 27:  # ESC
                return None
            elif ch == ord('q'):
                return None

        del win
