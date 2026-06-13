"""curses 通用绘制工具"""
import curses


def get_size(stdscr):
    """获取终端可用行列数"""
    return stdscr.getmaxyx()


def calc_box_size(stdscr, content_h, content_w, min_h=10, min_w=40):
    """计算对话框尺寸，居中，自适应终端大小"""
    max_h, max_w = get_size(stdscr)
    h = min(content_h, max_h - 2)
    w = min(content_w, max_w - 2)
    h = max(h, min_h)
    w = max(w, min_w)
    y = max(0, (max_h - h) // 2)
    x = max(0, (max_w - w) // 2)
    return y, x, h, w


def draw_box(win, title="", backtitle=""):
    """绘制边框和标题"""
    win.border()
    if title:
        win.addstr(0, 2, f" {title} ", curses.A_BOLD)
    if backtitle:
        max_h, max_w = win.getmaxyx()
        try:
            win.addstr(max_h - 1, 2, f" {backtitle} ", curses.A_DIM)
        except curses.error:
            pass


def wrap_text(text, width):
    """将文本按宽度折行，返回行列表"""
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append('')
            continue
        while len(paragraph) > width:
            # 尽量在空格处折行
            cut = width
            space = paragraph.rfind(' ', 0, width)
            if space > width // 3:
                cut = space
            lines.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        if paragraph:
            lines.append(paragraph)
    return lines


# 颜色常量（安全初始化）
COLOR_BORDER = 0
COLOR_TITLE = 0
COLOR_SELECTED = 0
COLOR_NORMAL = 0
COLOR_HIGHLIGHT = 0
COLOR_DIM = 0
COLOR_OK = 0
COLOR_FAIL = 0
COLOR_BAR = 0
COLOR_BAR_BG = 0

_initialized = False


def init_colors():
    """初始化颜色对（仅调用一次）"""
    global COLOR_BORDER, COLOR_TITLE, COLOR_SELECTED, COLOR_NORMAL
    global COLOR_HIGHLIGHT, COLOR_DIM, COLOR_OK, COLOR_FAIL
    global COLOR_BAR, COLOR_BAR_BG, _initialized

    if _initialized:
        return
    _initialized = True

    if not curses.has_colors():
        return

    curses.start_color()
    curses.use_default_colors()

    # 定义颜色对
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)    # 选中项
    curses.init_pair(2, curses.COLOR_CYAN, -1)                    # 标题
    curses.init_pair(3, curses.COLOR_YELLOW, -1)                  # 高亮
    curses.init_pair(4, curses.COLOR_GREEN, -1)                   # 成功
    curses.init_pair(5, curses.COLOR_RED, -1)                     # 失败
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_CYAN)    # 进度条
    curses.init_pair(7, -1, curses.COLOR_BLUE)                    # 进度条背景
    curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_RED)     # 警告选中

    COLOR_SELECTED = curses.color_pair(1) | curses.A_BOLD
    COLOR_TITLE = curses.color_pair(2) | curses.A_BOLD
    COLOR_HIGHLIGHT = curses.color_pair(3)
    COLOR_OK = curses.color_pair(4)
    COLOR_FAIL = curses.color_pair(5)
    COLOR_BAR = curses.color_pair(6)
    COLOR_BAR_BG = curses.color_pair(7)
    COLOR_BORDER = 0
    COLOR_NORMAL = 0
    COLOR_DIM = curses.A_DIM
