#!/bin/bash
set -euo pipefail

# live-build bootstrap + chroot 阶段

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

ROOTFS_DIR="${WORKSPACE}/rootfs"
CACHE_DIR="${WORKSPACE}/cache"
ROOTFS_CACHE="${CACHE_DIR}/rootfs"
LB_DIR="${CACHE_DIR}/lb-work"

rm -rf "${LB_DIR}"
mkdir -p "${LB_DIR}"

cd "${LB_DIR}"

step "lb config"
lb config noauto \
    --distribution jammy \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --bootloader syslinux \
    --debian-installer none \
    --memtest none \
    --iso-application "VDI Offline Deploy" \
    --iso-publisher "VDI" \
    --iso-volume "VDI-INSTALL" \
    --parent-distribution jammy \
    --parent-mirror-bootstrap "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-chroot "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-chroot-security "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-binary "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-binary-security "http://mirrors.aliyun.com/ubuntu" \
    --mirror-bootstrap "http://mirrors.aliyun.com/ubuntu" \
    --mirror-chroot "http://mirrors.aliyun.com/ubuntu" \
    --mirror-chroot-security "http://mirrors.aliyun.com/ubuntu" \
    --mirror-binary "http://mirrors.aliyun.com/ubuntu" \
    --mirror-binary-security "http://mirrors.aliyun.com/ubuntu" \
    --archive-areas "main universe" \
    --security true \
    --backports false \
    --chroot-filesystem squashfs \
    --initramfs live-boot \
    --initsystem systemd \
    --bootappend-live "boot=live live-media-path=/casper console=ttyS0,115200 console=tty0"
ok "lb config 完成"

step "同步配置到 config/"
if [ -d "${ROOTFS_DIR}/package-lists" ]; then
    mkdir -p config/package-lists
    cp "${ROOTFS_DIR}"/package-lists/*.chroot config/package-lists/ 2>/dev/null || true
fi
if [ -d "${ROOTFS_DIR}/includes.chroot" ]; then
    mkdir -p config/includes.chroot
    rsync -a "${ROOTFS_DIR}/includes.chroot/" config/includes.chroot/
fi

step "lb bootstrap"
lb bootstrap

step "lb chroot"
lb chroot

step "复制 rootfs 到缓存"
rm -rf "${ROOTFS_CACHE}"
cp -a "${LB_DIR}/chroot" "${ROOTFS_CACHE}"
rm -rf "${LB_DIR}"

ok "Bootstrap + chroot 完成"
