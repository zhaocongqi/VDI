#!/bin/bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"

CACHE_DIR="${WORKSPACE}/cache"
ROOTFS_CACHE="${CACHE_DIR}/rootfs"
ISO_ROOT="${CACHE_DIR}/iso-staging"

validate_dir "${ROOTFS_CACHE}" "rootfs" || exit 1

KERNEL=$(find "${ROOTFS_CACHE}/boot" -name "vmlinuz-*" -type f 2>/dev/null | head -1)
INITRD=$(find "${ROOTFS_CACHE}/boot" -name "initrd.img-*" -type f 2>/dev/null | head -1)

if [ -n "$KERNEL" ] && [ -n "$INITRD" ]; then
    cp "$KERNEL" "${ISO_ROOT}/casper/vmlinuz"
    cp "$INITRD" "${ISO_ROOT}/casper/initrd"
    ok "内核和 initrd 已复制"
else
    error "未找到内核文件"
    exit 1
fi

rm -f "${ISO_ROOT}/casper/filesystem.squashfs"
mksquashfs "$ROOTFS_CACHE" "${ISO_ROOT}/casper/filesystem.squashfs" \
    -comp xz -no-progress -noappend \
    -e boot/grub -e var/cache -e var/lib/apt/lists

ok "squashfs 已创建 ($(du -sh "${ISO_ROOT}/casper/filesystem.squashfs" | cut -f1))"
