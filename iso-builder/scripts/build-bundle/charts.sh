#!/bin/bash
set -euo pipefail

# 下载 Helm Chart

SELF="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
VDI_ROOT="$(cd "${WORKSPACE}/.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
CHARTS_DIR="${WORKSPACE}/cache/bundle/charts"

require_cmds helm yq

mkdir -p "$CHARTS_DIR"

# Kube-OVN（本地）
step "Kube-OVN: 复制本地 Helm chart"
KUBEOVN_SRC="${VDI_ROOT}/deploy/kube-ovn/chart"
KUBEOVN_DST="${CHARTS_DIR}/kube-ovn"
if [ -d "$KUBEOVN_SRC" ]; then
    rm -rf "$KUBEOVN_DST"
    cp -r "$KUBEOVN_SRC" "$KUBEOVN_DST"
    ok "Kube-OVN chart 已复制"
else
    info "deploy/kube-ovn/chart/ 不存在"
fi

# Longhorn（远程）
step "Longhorn: 下载远程 Helm chart"
LH_VERSION=$(yq '.components.longhorn.version' "$MANIFEST" 2>/dev/null || echo "")
if [ -n "$LH_VERSION" ]; then
    helm repo add longhorn https://charts.longhorn.io 2>/dev/null || true
    helm repo update longhorn
    helm pull "longhorn/longhorn" --version "${LH_VERSION#v}" --destination "$CHARTS_DIR"
    mkdir -p "${CHARTS_DIR}/longhorn"
    tar -xzf "${CHARTS_DIR}/longhorn-${LH_VERSION#v}.tgz" -C "$CHARTS_DIR"
    ok "Longhorn chart 已下载"
fi

# kagent（远程或本地）
step "kagent: 准备 Helm chart"
KAGENT_VERSION=$(yq '.components.kagent.version' "$MANIFEST" 2>/dev/null || echo "")
if [ -n "$KAGENT_VERSION" ]; then
    if helm pull "oci://ghcr.io/kagent-dev/charts/kagent" --version "${KAGENT_VERSION}" --destination "$CHARTS_DIR" 2>/dev/null; then
        mkdir -p "${CHARTS_DIR}/kagent"
        tar -xzf "${CHARTS_DIR}/kagent-${KAGENT_VERSION}.tgz" -C "$CHARTS_DIR"
        ok "kagent chart 已从 OCI 拉取"
    else
        KAGENT_SRC="${VDI_ROOT}/kagent/helm"
        if [ -d "$KAGENT_SRC" ]; then
            cp -r "$KAGENT_SRC" "${CHARTS_DIR}/kagent"
            [ -f "${CHARTS_DIR}/kagent/Chart.yaml" ] && helm dependency update "${CHARTS_DIR}/kagent" 2>/dev/null || true
            ok "kagent chart 已从源码构建"
        fi
    fi
fi

ok "Helm Chart 下载完成"
