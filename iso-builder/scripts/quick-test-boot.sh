#!/bin/bash
set -euo pipefail

# 快速引导测试脚本
# 验证 ISO 是否能正常引导（BIOS 和 UEFI）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ISO_PATH="${PROJECT_DIR}/dist/vdi-offline-v1.0.0.iso"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# 检查 ISO
if [ ! -f "$ISO_PATH" ]; then
    error "ISO 不存在: $ISO_PATH"
    echo "请先运行: sudo make iso"
    exit 1
fi

info "ISO 文件: $(ls -lh "$ISO_PATH" | awk '{print $5, $9}')"

# 创建临时目录
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

# 创建测试磁盘
qemu-img create -f qcow2 "$TMPDIR/test-disk.qcow2" 20G >/dev/null 2>&1

# 测试函数
test_boot() {
    local mode=$1
    local timeout=${2:-30}

    info "=========================================="
    info "测试 $mode 模式引导"
    info "=========================================="

    local qemu_args=(
        -m 2048
        -nographic
        -serial mon:stdio
        -cdrom "$ISO_PATH"
        -hda "$TMPDIR/test-disk.qcow2"
        -boot d
        -no-reboot
    )

    # UEFI 模式需要 OVMF
    if [ "$mode" = "UEFI" ]; then
        local ovmf_code=""
        for path in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd; do
            if [ -f "$path" ]; then
                ovmf_code="$path"
                break
            fi
        done

        if [ -z "$ovmf_code" ]; then
            warn "找不到 OVMF，跳过 UEFI 测试"
            return 0
        fi

        # 创建 VARS
        cp /usr/share/OVMF/OVMF_VARS_4M.fd "$TMPDIR/uefi-vars.fd" 2>/dev/null || \
        dd if=/dev/zero of="$TMPDIR/uefi-vars.fd" bs=1M count=4 2>/dev/null

        qemu_args+=(
            -drive if=pflash,format=raw,readonly=on,file="$ovmf_code"
            -drive if=pflash,format=raw,file="$TMPDIR/uefi-vars.fd"
        )
    fi

    # 启用 KVM（如果可用）
    if [ -c /dev/kvm ]; then
        qemu_args+=(-enable-kvm)
    fi

    info "启动 QEMU（超时: ${timeout}s）..."
    info "观察是否出现 GRUB 菜单或内核启动信息..."
    echo ""

    # 运行 QEMU 并捕获输出
    local output_file="$TMPDIR/qemu-output-$mode.txt"
    timeout "${timeout}" qemu-system-x86_64 "${qemu_args[@]}" > "$output_file" 2>&1 &
    local qemu_pid=$!

    # 等待启动
    sleep 5

    # 检查输出
    if [ -f "$output_file" ]; then
        local lines=$(wc -l < "$output_file")
        if [ "$lines" -gt 10 ]; then
            info "✓ QEMU 启动成功（输出 $lines 行）"

            # 检查关键信息
            if grep -q "GRUB" "$output_file"; then
                info "✓ 检测到 GRUB 引导"
            fi
            if grep -q "Linux" "$output_file"; then
                info "✓ 检测到 Linux 内核启动"
            fi
            if grep -q "casper" "$output_file"; then
                info "✓ 检测到 Live 环境启动"
            fi
        else
            warn "QEMU 输出较少（$lines 行），可能启动失败"
        fi
    fi

    # 终止 QEMU
    kill $qemu_pid 2>/dev/null || true
    wait $qemu_pid 2>/dev/null || true

    echo ""
    info "$mode 模式测试完成"
}

# 主函数
main() {
    local mode="${1:-both}"

    case "$mode" in
        bios)
            test_boot "BIOS" 30
            ;;
        uefi)
            test_boot "UEFI" 30
            ;;
        both)
            test_boot "BIOS" 30
            echo ""
            test_boot "UEFI" 30
            ;;
        *)
            error "用法: $0 [bios|uefi|both]"
            exit 1
            ;;
    esac

    info "=========================================="
    info "测试总结"
    info "=========================================="
    info "如果看到 '✓ 检测到 GRUB 引导' 或 '✓ 检测到 Linux 内核启动'"
    info "说明 ISO 引导正常，修复有效。"
    echo ""
    info "下一步：在 VMware 中完整测试装机流程"
    info "  1. 使用新 ISO 启动"
    info "  2. 完成装机"
    info "  3. 移除 ISO 后重启"
    info "  4. 应该从磁盘引导，不再进入 PXE"
}

main "$@"
