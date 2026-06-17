#!/bin/bash
set -euo pipefail

# ISO引导验证脚本
# 验证ISO文件是否包含正确的引导结构

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

# 检查ISO文件
check_iso() {
    info "=========================================="
    info "ISO文件验证"
    info "=========================================="

    if [ ! -f "$ISO_PATH" ]; then
        error "ISO文件不存在: $ISO_PATH"
        return 1
    fi

    info "文件: $ISO_PATH"
    info "大小: $(du -h "$ISO_PATH" | cut -f1)"
    info "类型: $(file "$ISO_PATH")"
    echo ""
}

# 检查ISO内部结构
check_iso_structure() {
    info "=========================================="
    info "ISO内部结构验证"
    info "=========================================="

    local mount_point="/tmp/iso-verify-$$"
    mkdir -p "$mount_point"

    # 挂载ISO
    if ! mount -o loop,ro "$ISO_PATH" "$mount_point" 2>/dev/null; then
        error "无法挂载ISO"
        return 1
    fi

    # 检查关键文件
    local checks=0
    local passed=0

    # 1. 检查isolinux（BIOS引导）
    info "检查 BIOS 引导文件 (isolinux)..."
    if [ -f "$mount_point/isolinux/isolinux.bin" ]; then
        info "✓ isolinux.bin 存在"
        ((passed++))
    else
        error "✗ isolinux.bin 不存在"
    fi
    ((checks++))

    if [ -f "$mount_point/isolinux/isolinux.cfg" ]; then
        info "✓ isolinux.cfg 存在"
        ((passed++))
    else
        error "✗ isolinux.cfg 不存在"
    fi
    ((checks++))

    # 2. 检查GRUB（UEFI引导）
    info "检查 UEFI 引导文件 (GRUB)..."
    if [ -f "$mount_point/boot/grub/grub.cfg" ]; then
        info "✓ grub.cfg 存在"
        ((passed++))
    else
        error "✗ grub.cfg 不存在"
    fi
    ((checks++))

    if [ -f "$mount_point/boot/grub/efi.img" ] || [ -f "$mount_point/efi/boot/efiboot.img" ]; then
        info "✓ EFI引导镜像存在"
        ((passed++))
    else
        error "✗ EFI引导镜像不存在"
    fi
    ((checks++))

    # 3. 检查内核和initrd
    info "检查内核文件..."
    if [ -f "$mount_point/casper/vmlinuz" ]; then
        info "✓ vmlinuz 存在 ($(du -h "$mount_point/casper/vmlinuz" | cut -f1))"
        ((passed++))
    else
        error "✗ vmlinuz 不存在"
    fi
    ((checks++))

    if [ -f "$mount_point/casper/initrd" ]; then
        info "✓ initrd 存在 ($(du -h "$mount_point/casper/initrd" | cut -f1))"
        ((passed++))
    else
        error "✗ initrd 不存在"
    fi
    ((checks++))

    if [ -f "$mount_point/casper/filesystem.squashfs" ]; then
        info "✓ filesystem.squashfs 存在 ($(du -h "$mount_point/casper/filesystem.squashfs" | cut -f1))"
        ((passed++))
    else
        error "✗ filesystem.squashfs 不存在"
    fi
    ((checks++))

    # 4. 检查部署脚本
    info "检查部署脚本..."
    if [ -d "$mount_point/scripts/deploy" ]; then
        info "✓ deploy 目录存在"
        ((passed++))

        # 检查os-install脚本
        if [ -f "$mount_point/scripts/deploy/skills/os-install/scripts/install.sh" ]; then
            info "✓ os-install 安装脚本存在"
            ((passed++))

            # 检查是否包含BIOS Boot分区配置
            if grep -q "BIOS Boot" "$mount_point/scripts/deploy/skills/os-install/scripts/install.sh"; then
                info "✓ 包含 BIOS Boot 分区配置（修复已应用）"
                ((passed++))
            else
                error "✗ 缺少 BIOS Boot 分区配置（修复未应用）"
            fi
            ((checks++))
        else
            error "✗ os-install 安装脚本不存在"
        fi
        ((checks++))
    else
        error "✗ deploy 目录不存在"
    fi
    ((checks++))

    # 5. 检查TUI安装器
    info "检查 TUI 安装器..."
    if [ -d "$mount_point/opt/vdi/tui" ]; then
        info "✓ TUI 安装器目录存在"
        ((passed++))
    else
        warn "⚠ TUI 安装器目录不存在（可能在其他位置）"
    fi
    ((checks++))

    # 卸载ISO
    umount "$mount_point" 2>/dev/null || true
    rmdir "$mount_point" 2>/dev/null || true

    echo ""
    info "=========================================="
    info "验证结果: $passed/$checks 通过"
    info "=========================================="

    if [ "$passed" -eq "$checks" ]; then
        info "✓ ISO结构完整，包含所有必要的引导文件"
        return 0
    else
        warn "⚠ 部分检查未通过，请查看上方详情"
        return 1
    fi
}

# 检查引导配置内容
check_boot_config() {
    info "=========================================="
    info "引导配置内容验证"
    info "=========================================="

    local mount_point="/tmp/iso-boot-verify-$$"
    mkdir -p "$mount_point"

    if ! mount -o loop,ro "$ISO_PATH" "$mount_point" 2>/dev/null; then
        error "无法挂载ISO"
        return 1
    fi

    # 检查isolinux配置
    info "BIOS 引导配置 (isolinux.cfg):"
    if [ -f "$mount_point/isolinux/isolinux.cfg" ]; then
        echo "----------------------------------------"
        cat "$mount_point/isolinux/isolinux.cfg"
        echo "----------------------------------------"
        echo ""
    fi

    # 检查GRUB配置
    info "UEFI 引导配置 (grub.cfg):"
    if [ -f "$mount_point/boot/grub/grub.cfg" ]; then
        echo "----------------------------------------"
        cat "$mount_point/boot/grub/grub.cfg"
        echo "----------------------------------------"
        echo ""
    fi

    # 检查安装脚本中的分区配置
    info "OS安装脚本分区配置:"
    if [ -f "$mount_point/scripts/deploy/skills/os-install/scripts/install.sh" ]; then
        echo "----------------------------------------"
        grep -A10 "开始分区" "$mount_point/scripts/deploy/skills/os-install/scripts/install.sh" | head -20
        echo "----------------------------------------"
        echo ""
    fi

    umount "$mount_point" 2>/dev/null || true
    rmdir "$mount_point" 2>/dev/null || true
}

# QEMU启动测试
test_qemu_boot() {
    local mode=$1
    local timeout=${2:-15}

    info "=========================================="
    info "QEMU $mode 模式启动测试"
    info "=========================================="

    local qemu_args=(
        -m 2048
        -nographic
        -serial mon:stdio
        -cdrom "$ISO_PATH"
        -boot d
        -no-reboot
    )

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

        qemu_args+=(
            -drive if=pflash,format=raw,readonly=on,file="$ovmf_code"
        )
    fi

    if [ -c /dev/kvm ]; then
        qemu_args+=(-enable-kvm)
    fi

    info "启动 QEMU（${timeout}s超时）..."
    local output_file="/tmp/qemu-$mode-verify.log"

    timeout "${timeout}" qemu-system-x86_64 "${qemu_args[@]}" > "$output_file" 2>&1 &
    local qemu_pid=$!

    sleep 3

    local success=0
    if [ -f "$output_file" ]; then
        local lines=$(wc -l < "$output_file")
        info "QEMU输出: $lines 行"

        if grep -q "GRUB" "$output_file"; then
            info "✓ 检测到 GRUB 引导"
            ((success++))
        fi

        if grep -q "Linux" "$output_file"; then
            info "✓ 检测到 Linux 内核"
            ((success++))
        fi

        if grep -q "casper" "$output_file"; then
            info "✓ 检测到 Live 环境"
            ((success++))
        fi

        if grep -q "ISOLINUX" "$output_file"; then
            info "✓ 检测到 ISOLINUX"
            ((success++))
        fi

        # 显示前几行输出
        info "QEMU输出前10行:"
        head -10 "$output_file" | sed 's/^/    /'
    fi

    kill $qemu_pid 2>/dev/null || true
    wait $qemu_pid 2>/dev/null || true

    echo ""
    if [ "$success" -gt 0 ]; then
        info "✓ $mode 模式启动成功（检测到 $success 个关键特征）"
        return 0
    else
        warn "⚠ $mode 模式未检测到预期输出，可能需要更长时间启动"
        return 1
    fi
}

# 主函数
main() {
    local mode="${1:-all}"

    case "$mode" in
        structure)
            check_iso
            check_iso_structure
            ;;
        config)
            check_iso
            check_boot_config
            ;;
        bios)
            check_iso
            test_qemu_boot "BIOS" 20
            ;;
        uefi)
            check_iso
            test_qemu_boot "UEFI" 20
            ;;
        all)
            check_iso
            check_iso_structure
            echo ""
            check_boot_config
            echo ""
            test_qemu_boot "BIOS" 20
            echo ""
            test_qemu_boot "UEFI" 20
            ;;
        *)
            error "用法: $0 [structure|config|bios|uefi|all]"
            exit 1
            ;;
    esac

    echo ""
    info "=========================================="
    info "验证完成"
    info "=========================================="
    info "如果所有检查都通过，ISO应该能正常引导。"
    info ""
    info "下一步：在VMware中进行完整装机测试"
    info "参考: QUICK-TEST.md 或 TESTING.md"
}

main "$@"
