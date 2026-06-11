#!/bin/bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"

CACHE_DIR="${WORKSPACE}/cache"
DIST_DIR="${WORKSPACE}/dist"
PXE_DIR="${DIST_DIR}/pxe"

mkdir -p "${PXE_DIR}"

# 尝试从 staging 目录复制（iso.sh 可能还没清理）
if [ -f "${CACHE_DIR}/iso-staging/casper/vmlinuz" ]; then
    cp "${CACHE_DIR}/iso-staging/casper/vmlinuz" "${PXE_DIR}/"
    cp "${CACHE_DIR}/iso-staging/casper/initrd" "${PXE_DIR}/"
    cp "${CACHE_DIR}/iso-staging/casper/filesystem.squashfs" "${PXE_DIR}/rootfs.squashfs"
else
    # 从已生成的 ISO 中提取
    ISO_FILE=$(ls -t "${DIST_DIR}"/*.iso 2>/dev/null | head -1)
    if [ -n "$ISO_FILE" ]; then
        step "从 ISO 提取 PXE 文件"
        xorriso -osirrox on -indev "$ISO_FILE" \
            -extract /casper/vmlinuz "${PXE_DIR}/vmlinuz" \
            -extract /casper/initrd "${PXE_DIR}/initrd" \
            -extract /casper/filesystem.squashfs "${PXE_DIR}/rootfs.squashfs"
    else
        warn "无可用 ISO 或 staging 目录，跳过 PXE 产物生成"
        exit 0
    fi
fi

ok "PXE 产物已生成: ${PXE_DIR}/"
ls -lh "${PXE_DIR}/"
