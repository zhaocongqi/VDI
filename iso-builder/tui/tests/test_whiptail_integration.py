#!/usr/bin/env python3
"""whiptail 集成冒烟测试（需要 TTY 环境）

验证修改后的 Whiptail._run() 通过 subprocess.run() 真实调用 whiptail 的行为。
运行方式：python3 tests/test_whiptail_integration.py
要求：1) 本机安装了 whiptail  2) 在真实终端中运行（非管道/后台）
"""
import sys
import os
import time
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.whiptail_wrapper import Whiptail, _strip_ansi, _save_terminal_state, _restore_terminal_state


def check_tty():
    """检查是否在真实 TTY 中运行"""
    if not sys.stdin.isatty():
        print("SKIP: 此测试需要在真实终端中运行（检测到 stdin 非 TTY）")
        return False
    return True


def test_msgbox():
    """测试 msgbox 显示"""
    wt = Whiptail(title="集成测试 - msgbox")
    result = wt.msgbox("这是一个测试消息框。\n\n按 Enter 关闭。")
    assert result is True, "msgbox 应返回 True"
    print("  ✅ msgbox 正常")


def test_yesno():
    """测试 yesno 确认框"""
    wt = Whiptail(title="集成测试 - yesno")
    result = wt.yesno("请选择 Yes 或 No：\n\nTab 切换，Enter 确认。")
    print(f"  ✅ yesno 返回: {result} (True=Yes, False=No)")


def test_inputbox():
    """测试 inputbox 输入框"""
    wt = Whiptail(title="集成测试 - inputbox")
    result = wt.inputbox("请输入任意文本：", default="hello")
    print(f"  ✅ inputbox 返回: {repr(result)}")


def test_menu():
    """测试 menu 菜单选择"""
    wt = Whiptail(title="集成测试 - menu")
    items = [
        ("1", "选项一"),
        ("2", "选项二"),
        ("3", "选项三"),
    ]
    result = wt.menu("请选择一个选项：", items)
    print(f"  ✅ menu 返回: {repr(result)}")


def test_radiolist():
    """测试 radiolist 单选"""
    wt = Whiptail(title="集成测试 - radiolist")
    items = [
        ("a", "选项 A", "ON"),
        ("b", "选项 B", "OFF"),
        ("c", "选项 C", "OFF"),
    ]
    result = wt.radiolist("请选择一项：", items)
    print(f"  ✅ radiolist 返回: {repr(result)}")


def test_terminal_restore():
    """测试终端状态保存/恢复"""
    import termios
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)

    # 模拟 whiptail 修改了终端设置
    _save_terminal_state(fd)
    modified = list(original)
    modified[3] = modified[3] | termios.ECHO  # 确保 ECHO 开启
    termios.tcsetattr(fd, termios.TCSANOW, modified)

    # 恢复
    _restore_terminal_state(fd, original)
    restored = termios.tcgetattr(fd)

    assert restored == original, "终端属性应完全恢复"
    print("  ✅ 终端状态保存/恢复正常")


def test_strip_ansi():
    """测试 ANSI 清理"""
    cases = [
        ("\x1b[32mOK\x1b[0m", "OK"),
        ("hello world", "hello world"),
        ("\x1b[1;32m  text  \x1b[0m", "text"),
        ("", ""),
    ]
    for input_text, expected in cases:
        result = _strip_ansi(input_text)
        assert result == expected, f"_strip_ansi({repr(input_text)}) = {repr(result)}, 期望 {repr(expected)}"
    print("  ✅ _strip_ansi 正常")


def main():
    print("=" * 50)
    print("whiptail 集成冒烟测试")
    print("=" * 50)

    if not check_tty():
        # 非 TTY 环境，只运行非交互式测试
        print("\n--- 非交互式测试 ---")
        test_strip_ansi()
        print("\n所有非交互式测试通过 ✅")
        print("交互式测试需要在真实终端中运行：")
        print("  $ python3 tests/test_whiptail_integration.py")
        return 0

    print(f"\n终端: TERM={os.environ.get('TERM')}, TTY={os.ttyname(sys.stdin.fileno())}")
    print()

    # 非交互式测试
    print("[1/7] ANSI 清理...")
    test_strip_ansi()

    print("\n[2/7] 终端状态保存/恢复...")
    test_terminal_restore()

    # 交互式测试
    print("\n--- 以下为交互式测试，需要手动操作 ---\n")

    print("[3/7] msgbox 测试（按 Enter 关闭）...")
    test_msgbox()

    print("\n[4/7] yesno 测试（Tab 切换，Enter 确认）...")
    test_yesno()

    print("\n[5/7] inputbox 测试（输入文本，Enter 确认）...")
    test_inputbox()

    print("\n[6/7] menu 测试（方向键选择，Enter 确认）...")
    test_menu()

    print("\n[7/7] radiolist 测试（方向键+空格选择，Enter 确认）...")
    test_radiolist()

    print("\n" + "=" * 50)
    print("所有测试通过 ✅")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
