#!/bin/bash
set -euo pipefail

# 在 chroot 中执行 hooks

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

ROOTFS_DIR="${WORKSPACE}/rootfs"
ROOTFS_CACHE="${WORKSPACE}/cache/rootfs"
HOOKS_DIR="${ROOTFS_DIR}/hooks"

if [ ! -d "${HOOKS_DIR}" ]; then
    info "无 chroot hooks 目录"
    exit 0
fi

CHROOT_DIR="${ROOTFS_CACHE}"
validate_dir "${CHROOT_DIR}" "rootfs 缓存" || exit 1

step "执行 chroot hooks"

for hook in "${HOOKS_DIR}"/*.chroot; do
    [ -f "$hook" ] || continue
    hook_name="$(basename "$hook")"
    info "执行 hook: ${hook_name}"

    cp "$hook" "${CHROOT_DIR}/tmp/${hook_name}"
    chmod +x "${CHROOT_DIR}/tmp/${hook_name}"

    if chroot "${CHROOT_DIR}" "/tmp/${hook_name}"; then
        ok "Hook 成功: ${hook_name}"
    else
        error "Hook 失败: ${hook_name}"
        exit 1
    fi

    rm -f "${CHROOT_DIR}/tmp/${hook_name}"
done

ok "所有 chroot hooks 执行完成"
