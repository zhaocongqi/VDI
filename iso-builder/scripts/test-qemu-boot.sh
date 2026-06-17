#!/bin/bash
set -euo pipefail

# QEMU 引导测试脚本
# 测试 ISO 在 BIOS 和 UEFI 两种模式下的引导能力
#
# 用法：
#   ./scripts/test-qemu-boot.sh [bios|uefi|both]
#
# 依赖：
#   - qemu-system-x86_64
#   - OVMF (UEFI 固件，仅 UEFI 模式需要)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ISO_PATH="${PROJECT_DIR}/dist/vdi-offline-v1.0.0.iso"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# 检查依赖
check_deps() {
    local missing=()
    command -v qemu-system-x86_64 >/dev/null 2>&1 || missing+=("qemu-system-x86")

    if [ ${#missing[@]} -gt 0 ]; then
        error "缺少依赖: ${missing[*]}"
        echo "安装命令: sudo apt install ${missing[*]}"
        exit 1
    fi
}

# 检查 ISO 文件
check_iso() {
    if [ ! -f "$ISO_PATH" ]; then
        error "ISO 文件不存在: $ISO_PATH"
        echo "请先运行: make iso"
        exit 1
    fi
    info "ISO 文件: $ISO_PATH ($(du -h "$ISO_PATH" | cut -f1))"
}

# 创建临时磁盘（模拟安装目标）
create_test_disk() {
    local disk_path="$1"
    local size="${2:-20G}"
    qemu-img create -f qcow2 "$disk_path" "$size" >/dev/null 2>&1
    info "创建测试磁盘: $disk_path ($size)"
}

# BIOS 模式测试
test_bios() {
    info "=========================================="
    info "开始 BIOS 模式引导测试"
    info "=========================================="

    local test_disk="/tmp/vdi-test-bios.qcow2"
    create_test_disk "$test_disk" "20G"

    info "启动 QEMU (BIOS 模式)..."
    info "预期行为："
    info "  1. 从 ISO 启动进入 Live 环境"
    info "  2. 运行 TUI 安装器"
    info "  3. 安装到磁盘后重启"
    info "  4. 从磁盘引导（不进入 PXE）"
    echo ""
    info "测试要点："
    info "  - 检查是否出现 GRUB 菜单"
    info "  - 安装完成后移除 ISO"
    info "  - 重启后观察是否从磁盘引导"
    echo ""
    info "按 Ctrl+C 退出测试"
    echo ""

    # QEMU BIOS 模式参数
    # -m 4096: 4GB 内存
    # -cpu host: 使用宿主机 CPU 特性（需要 KVM）
    # -enable-kvm: 启用 KVM 加速（如果可用）
    # -cdrom: ISO 文件
    # -hda: 测试磁盘
    # -boot d: 优先从 CDROM 启动
    # -serial mon:stdio: 串口输出到终端
    # -vga virtio: 虚拟显卡

    local qemu_args=(
        -m 4096
        -cpu host
        -smp 2
        -cdrom "$ISO_PATH"
        -hda "$test_disk"
        -boot d
        -serial mon:stdio
        -vga virtio
        -display gtk
        -usb
        -device usb-tablet
    )

    # 如果有 KVM 支持则启用
    if [ -c /dev/kvm ]; then
        qemu_args+=(-enable-kvm)
        info "KVM 加速: 已启用"
    else
        warn "KVM 加速: 未启用（测试将较慢）"
    fi

    qemu-system-x86_64 "${qemu_args[@]}" || true

    info "BIOS 模式测试结束"
    rm -f "$test_disk"
}

# UEFI 模式测试
test_uefi() {
    info "=========================================="
    info "开始 UEFI 模式引导测试"
    info "=========================================="

    # 查找 OVMF 固件
    local ovmf_code=""
    local ovars=""

    # 常见 OVMF 路径
    for path in \
        /usr/share/OVMF/OVMF_CODE_4M.fd \
        /usr/share/OVMF/OVMF_CODE.fd \
        /usr/share/edk2/ovmf/OVMF_CODE.fd \
        /usr/share/qemu/OVMF_CODE.fd; do
        if [ -f "$path" ]; then
            ovmf_code="$path"
            break
        fi
    done

    for path in \
        /usr/share/OVMF/OVMF_VARS_4M.fd \
        /usr/share/OVMF/OVMF_VARS.fd \
        /usr/share/edk2/ovmf/OVMF_VARS.fd \
        /usr/share/qemu/OVMF_VARS.fd; do
        if [ -f "$path" ]; then
            ovars="$path"
            break
        fi
    done

    if [ -z "$ovmf_code" ]; then
        error "找不到 OVMF 固件"
        echo "安装命令: sudo apt install ovmf"
        exit 1
    fi

    info "OVMF 固件: $ovmf_code"

    local test_disk="/tmp/vdi-test-uefi.qcow2"
    create_test_disk "$test_disk" "20G"

    # 创建可写的 VARS 副本（UEFI 启动项存储）
    local vars_copy="/tmp/vdi-test-uefi-vars.fd"
    if [ -n "$ovars" ]; then
        cp "$ovars" "$vars_copy"
    else
        # 如果没有 VARS 文件，创建一个空的
        dd if=/dev/zero of="$vars_copy" bs=1M count=4 2>/dev/null
    fi

    info "启动 QEMU (UEFI 模式)..."
    info "预期行为："
    info "  1. 从 ISO 启动进入 GRUB UEFI 菜单"
    info "  2. 运行 TUI 安装器"
    info "  3. 安装到磁盘后重启"
    info "  4. 从磁盘 UEFI 引导（不进入 PXE）"
    echo ""
    info "测试要点："
    info "  - 检查是否出现 GRUB UEFI 菜单"
    info "  - 安装完成后移除 ISO"
    info "  - 重启后观察是否从磁盘 UEFI 引导"
    echo ""
    info "按 Ctrl+C 退出测试"
    echo ""

    local qemu_args=(
        -m 4096
        -cpu host
        -smp 2
        -drive if=pflash,format=raw,readonly=on,file="$ovmf_code"
        -drive if=pflash,format=raw,file="$vars_copy"
        -cdrom "$ISO_PATH"
        -hda "$test_disk"
        -boot d
        -serial mon:stdio
        -vga virtio
        -display gtk
        -usb
        -device usb-tablet
    )

    if [ -c /dev/kvm ]; then
        qemu_args+=(-enable-kvm)
        info "KVM 加速: 已启用"
    else
        warn "KVM 加速: 未启用（测试将较慢）"
    fi

    qemu-system-x86_64 "${qemu_args[@]}" || true

    info "UEFI 模式测试结束"
    rm -f "$test_disk" "$vars_copy"
}

# 主函数
main() {
    local mode="${1:-both}"

    check_deps
    check_iso

    case "$mode" in
        bios)
            test_bios
            ;;
        uefi)
            test_uefi
            ;;
        both)
            test_bios
            echo ""
            echo ""
            test_uefi
            ;;
        *)
            error "未知模式: $mode"
            echo "用法: $0 [bios|uefi|both]"
            exit 1
            ;;
    esac
}

main "$@"
