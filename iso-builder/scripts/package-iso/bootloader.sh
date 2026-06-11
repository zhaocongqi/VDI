#!/bin/bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"
source "${WORKSPACE}/scripts/lib/iso.sh"
source "${WORKSPACE}/scripts/lib/template.sh"

CACHE_DIR="${WORKSPACE}/cache"
ISO_ROOT="${CACHE_DIR}/iso-staging"
ISO_TEMPLATES="${WORKSPACE}/iso"
VERSION="${1:-v1.0.0}"

step "配置 isolinux (BIOS)"
copy_isolinux_files "${ISO_ROOT}/isolinux"
render_template "${ISO_TEMPLATES}/isolinux/isolinux.cfg" \
    "${ISO_ROOT}/isolinux/isolinux.cfg"
ok "isolinux 配置完成"

step "配置 GRUB (UEFI)"
render_template "${ISO_TEMPLATES}/boot/grub/grub.cfg" \
    "${ISO_ROOT}/boot/grub/grub.cfg" \
    "vdi_version=${VERSION}"
ok "GRUB 配置完成"

step "创建 EFI 引导镜像"
create_efi_image "${ISO_ROOT}/efi/boot/efiboot.img"
ok "EFI 引导镜像创建完成"
