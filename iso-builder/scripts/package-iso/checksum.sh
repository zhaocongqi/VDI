#!/bin/bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-v1.0.0}"
ISO_NAME="vdi-offline-${VERSION}"

source "${WORKSPACE}/scripts/common.sh"

DIST_DIR="${WORKSPACE}/dist"
ISO_FILE="${DIST_DIR}/${ISO_NAME}.iso"
MANIFEST="${WORKSPACE}/manifest.yaml"

if [ -f "$ISO_FILE" ]; then
    sha256sum "$ISO_FILE" > "${ISO_FILE}.sha256"
    ok "校验和已生成"

    ISO_SIZE=$(du -m "$ISO_FILE" | cut -f1)
    ISO_SHA=$(sha256sum "$ISO_FILE" | cut -d' ' -f1)

    cat > "${DIST_DIR}/version.yaml" << VERSION
# VDI 离线 ISO 构建信息
name: vdi-offline-iso
version: "${VERSION}"
buildDate: "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
buildHost: "$(hostname)"
arch: amd64
os: ubuntu-22.04
pipeline: "3-stage (build-rootfs / build-bundle / package-iso)"
VERSION

    if [ -f "$MANIFEST" ]; then
        echo "components:" >> "${DIST_DIR}/version.yaml"
        for comp in kubernetes kube-vip kube-ovn longhorn kubevirt cdi kagent; do
            ver=$(yq ".components.${comp}.version // \"\"" "$MANIFEST" 2>/dev/null || echo "")
            [ -n "$ver" ] && echo "  ${comp}: \"${ver}\"" >> "${DIST_DIR}/version.yaml"
        done
    fi

    cat >> "${DIST_DIR}/version.yaml" << VERSION

isoSize: "${ISO_SIZE}MB"
isoSha256: "${ISO_SHA}"
VERSION

    ok "version.yaml 已生成"
fi
