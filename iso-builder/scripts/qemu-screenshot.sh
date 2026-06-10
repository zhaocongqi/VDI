#!/bin/bash
# QEMU TUI 截图工具
# 通过 VGA 帧缓冲捕获 whiptail TUI 界面截图
#
# 根因：QEMU -nographic 模式无 VGA 设备，screendump 无法捕获 whiptail 渲染
# 方案：使用 VGA + VNC + monitor socket，通过 HMP screendump 捕获帧缓冲
#
# 已知限制（VGA 帧缓冲机制）：
#   QEMU -vga std 模式下，Linux 内核启动流程：
#     1. BIOS/GRUB → VGA text mode (80x25)
#     2. kernel 加载 vesafb/fbcon → 切换到图形帧缓冲
#     3. fbcon 在帧缓冲上渲染 whiptail TUI
#   screendump 捕获的是 QEMU 虚拟 VGA 设备的帧缓冲内存快照。
#   当 fbcon 使用 dirty region tracking 时，部分更新可能写入
#   QEMU 不追踪的内存区域，导致截图内容滞后或不完整。
#   VNC 客户端看到的是同一份帧缓冲，不存在此差异。
#
# 用法:
#   ./scripts/qemu-screenshot.sh start [ISO文件]   # 后台启动 QEMU
#   ./scripts/qemu-screenshot.sh capture [名称]     # 截取当前帧
#   ./scripts/qemu-screenshot.sh stop               # 停止 QEMU
#
# 依赖: qemu-system-x86_64, socat, ImageMagick（可选，PPM→PNG）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MONITOR_SOCK="/tmp/vdi-qemu-monitor.sock"
PID_FILE="/tmp/vdi-qemu.pid"
SCREENSHOT_DIR="${PROJECT_DIR}/docs/screenshots"
VNC_DISPLAY=":0"

# ─── 输出工具 ───────────────────────────────────────────
info()  { printf '\033[36m[i]\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m[✓]\033[0m %s\n' "$*"; }
err()   { printf '\033[31m[✗]\033[0m %s\n' "$*" >&2; }

# ─── 依赖检查 ───────────────────────────────────────────
check_deps() {
    local missing=()
    command -v qemu-system-x86_64 &>/dev/null || missing+=(qemu-system-x86_64)
    command -v socat &>/dev/null || missing+=(socat)

    if [[ ${#missing[@]} -gt 0 ]]; then
        err "缺少依赖: ${missing[*]}"
        err "安装: apt install qemu-system-x86 socat"
        exit 1
    fi
}

# ─── 发送 HMP 命令到 QEMU monitor ──────────────────────
monitor_cmd() {
    local cmd="$1"
    printf '%s\n' "$cmd" | socat - UNIX-CONNECT:"$MONITOR_SOCK" >/dev/null 2>&1 || true
}

# ─── 检查 QEMU 是否存活 ────────────────────────────────
is_qemu_alive() {
    [[ -S "$MONITOR_SOCK" ]] && monitor_cmd "info status" 2>/dev/null
}

# ─── 启动 QEMU ─────────────────────────────────────────
start_qemu() {
    local iso="${1:-}"

    # 自动查找 ISO
    if [[ -z "$iso" ]]; then
        iso="$(ls "$PROJECT_DIR"/dist/vdi-offline-*.iso 2>/dev/null | head -1)"
    fi

    if [[ -z "$iso" ]] || [[ ! -f "$iso" ]]; then
        err "ISO 文件不存在: ${iso:-未找到匹配文件}"
        err "请先运行: make iso"
        exit 1
    fi

    # 检查已有实例
    if is_qemu_alive; then
        err "QEMU 已在运行 (Monitor: $MONITOR_SOCK)"
        err "如需重启: $0 stop && $0 start"
        exit 1
    fi

    # 清理残留
    rm -f "$MONITOR_SOCK" "$PID_FILE"

    check_deps
    mkdir -p "$SCREENSHOT_DIR"

    local iso_abs
    iso_abs="$(realpath "$iso")"
    local vnc_display_num="${VNC_DISPLAY#:}"
    local vnc_port=$((5900 + vnc_display_num))

    info "启动 QEMU 截图模式"
    echo "  ISO:      $iso_abs"
    echo "  VNC:      vnc://localhost:${vnc_port}"
    echo "  Monitor:  $MONITOR_SOCK"
    echo "  截图目录: $SCREENSHOT_DIR/"
    echo ""
    echo "  截图:  $0 capture [名称]"
    echo "  停止:  $0 stop"
    echo ""

    # 启动 QEMU（后台守护模式）
    # 关键参数:
    #   -vga std          标准 VGA 帧缓冲，支持 Linux fbcon 渲染 whiptail
    #   -display none     不弹出窗口（配合 -vnc 使用）
    #   -vnc :0           VNC 服务，可实时查看 TUI 交互
    #   -monitor unix:... QEMU HMP monitor socket，用于发送 screendump
    #   -daemonize        后台运行，释放终端
    qemu-system-x86_64 \
        $(test -w /dev/kvm && echo -enable-kvm) \
        -m 2048 -smp 2 \
        -cdrom "$iso_abs" -boot d \
        -vga std \
        -display none \
        -vnc "${VNC_DISPLAY}" \
        -monitor "unix:${MONITOR_SOCK},server,nowait" \
        -net nic -net user \
        -daemonize \
        -pidfile "$PID_FILE"

    # 等待 monitor socket 就绪
    local retries=0
    while [[ ! -S "$MONITOR_SOCK" ]] && [[ $retries -lt 30 ]]; do
        sleep 1
        retries=$((retries + 1))
    done

    if [[ -S "$MONITOR_SOCK" ]]; then
        ok "QEMU 已启动 (PID: $(cat "$PID_FILE" 2>/dev/null || echo '?'))"
        info "等待 Live 系统启动... 通过 VNC 查看进度: vncviewer localhost:${vnc_port}"
        info "TUI 就绪后执行: $0 capture welcome"
    else
        err "QEMU 启动超时"
        exit 1
    fi
}

# ─── 截取当前 VGA 帧 ───────────────────────────────────
capture_screenshot() {
    local name="${1:-screenshot-$(date +%Y%m%d-%H%M%S)}"

    if ! is_qemu_alive; then
        err "QEMU 未运行 (Monitor socket: $MONITOR_SOCK)"
        err "请先运行: $0 start"
        exit 1
    fi

    mkdir -p "$SCREENSHOT_DIR"

    local shot_dir
    shot_dir="$(realpath "$SCREENSHOT_DIR")"
    local ppm_path="${shot_dir}/${name}.ppm"
    local png_path="${shot_dir}/${name}.png"

    # 通过 QEMU HMP screendump 捕获 VGA 帧缓冲
    # 注意：路径是宿主机路径，QEMU 以守护进程方式运行时
    #       解析相对于自身工作目录，使用绝对路径确保可靠
    monitor_cmd "screendump ${ppm_path}"

    # 等待文件写入完成
    local retries=0
    while [[ ! -f "$ppm_path" ]] && [[ $retries -lt 10 ]]; do
        sleep 0.2
        retries=$((retries + 1))
    done

    if [[ ! -f "$ppm_path" ]]; then
        err "截图失败：PPM 文件未生成"
        err "可能原因:"
        err "  1. VGA 帧缓冲未激活（确认未使用 -nographic）"
        err "  2. Live 系统尚未启动完成，帧缓冲无内容"
        err "  3. QEMU monitor 通信失败"
        exit 1
    fi

    # PPM → PNG 转换
    if command -v convert &>/dev/null; then
        convert "$ppm_path" "$png_path" 2>/dev/null && rm -f "$ppm_path"
        ok "截图已保存: $png_path"
    elif command -v pnmtopng &>/dev/null; then
        pnmtopng "$ppm_path" > "$png_path" 2>/dev/null && rm -f "$ppm_path"
        ok "截图已保存: $png_path"
    else
        ok "截图已保存: $ppm_path"
        info "安装 ImageMagick 可自动转 PNG: apt install imagemagick"
    fi
}

# ─── 停止 QEMU ─────────────────────────────────────────
stop_qemu() {
    if is_qemu_alive; then
        monitor_cmd "quit"
        sleep 1
        ok "QEMU 已停止"
    elif [[ -f "$PID_FILE" ]]; then
        local pid
        pid="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            ok "QEMU 已停止 (SIGTERM → PID $pid)"
        else
            info "QEMU 进程已不存在 (残留 PID: $pid)"
        fi
    else
        info "QEMU 未在运行"
    fi

    rm -f "$MONITOR_SOCK" "$PID_FILE"
}

# ─── 主入口 ─────────────────────────────────────────────
case "${1:-help}" in
    start)   shift; start_qemu "${1:-}" ;;
    capture) shift; capture_screenshot "${1:-}" ;;
    stop)    stop_qemu ;;
    help|*)
        echo "QEMU TUI 截图工具 — 通过 VGA 帧缓冲捕获 whiptail 界面"
        echo ""
        echo "用法:"
        echo "  $0 start [ISO]      后台启动 QEMU（VGA + VNC + monitor socket）"
        echo "  $0 capture [名称]   截取当前 VGA 帧（PPM/PNG）"
        echo "  $0 stop             停止后台 QEMU"
        echo ""
        echo "截图命名示例:"
        echo "  $0 capture welcome        → docs/screenshots/welcome.png"
        echo "  $0 capture network-config → docs/screenshots/network-config.png"
        echo "  $0 capture                → docs/screenshots/screenshot-20260610-143022.png"
        echo ""
        echo "工作原理:"
        echo "  QEMU -vga std 提供 VGA 帧缓冲 → Linux fbcon 渲染 whiptail TUI"
        echo "  → QEMU monitor HMP screendump 捕获帧缓冲像素 → PPM → PNG"
        echo ""
        echo "限制:"
        echo "  不适用于 -nographic 模式（该模式无 VGA 设备）"
        echo "  screendump 捕获 VGA 帧缓冲快照，fbcon dirty region 可能导致截图滞后"
        echo "  VNC 客户端看到的是实时帧缓冲，截图如有差异请以 VNC 为准"
        echo "  依赖: qemu-system-x86_64, socat, ImageMagick（可选）"
        ;;
esac
