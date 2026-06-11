#!/bin/bash
set -euo pipefail

# 下载系统 deb 包并创建本地 APT 仓库

SELF="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
DEB_DIR="${WORKSPACE}/cache/bundle/packages/deb"

require_cmds apt-get dpkg-scanpackages yq

mkdir -p "$DEB_DIR"

PACKAGES=$(yq '.packages.deb[]' "$MANIFEST" 2>/dev/null || true)
if [ -z "$PACKAGES" ]; then
    info "manifest.yaml 中无 deb 包定义"
    exit 0
fi

step "更新 APT 索引"
apt-get update -qq

for pkg in $PACKAGES; do
    info "下载: ${pkg}"
    cd "$DEB_DIR"
    apt-get download "$pkg" 2>/dev/null || continue

    deps=$(apt-cache depends --recurse --no-recommends --no-suggests \
        --no-conflicts --no-breaks --no-replaces --no-enhances \
        "$pkg" 2>/dev/null | grep "Depends:" | cut -d: -f2 | tr -d ' ' || true)
    for dep in $deps; do
        apt-get download "$dep" 2>/dev/null || true
    done
done

step "生成 APT 仓库元数据"
cd "$DEB_DIR"
dpkg-scanpackages . /dev/null 2>/dev/null | gzip -9c > Packages.gz

DEB_COUNT=$(ls "$DEB_DIR"/*.deb 2>/dev/null | wc -l)
info "已下载 ${DEB_COUNT} 个 deb 包"

ok "系统包下载完成"
