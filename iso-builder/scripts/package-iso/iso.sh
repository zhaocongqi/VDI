#!/bin/bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"
source "${WORKSPACE}/scripts/lib/iso.sh"

CACHE_DIR="${WORKSPACE}/cache"
DIST_DIR="${WORKSPACE}/dist"
ISO_ROOT="${CACHE_DIR}/iso-staging"
VERSION="${1:-v1.0.0}"
ISO_NAME="vdi-offline-${VERSION}"

mkdir -p "${DIST_DIR}"

pack_iso \
    "${DIST_DIR}/${ISO_NAME}.iso" \
    "${ISO_ROOT}" \
    "${ISO_ROOT}/efi/boot/efiboot.img" \
    "VDI-INSTALL"

rm -rf "${ISO_ROOT}"
