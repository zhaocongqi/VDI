#!/bin/bash
set -euo pipefail

# 下载 K8s Manifest YAML

SELF="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
MANIFESTS_DIR="${WORKSPACE}/cache/bundle/k8s-manifests"

require_cmds wget yq

mkdir -p "$MANIFESTS_DIR"

COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")

for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.manifests | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue

    step "组件 ${comp}: ${count} 个 manifest"

    for i in $(seq 0 $((count - 1))); do
        name=$(yq ".components.${comp}.manifests[${i}].name" "$MANIFEST")
        path=$(yq ".components.${comp}.manifests[${i}].path" "$MANIFEST")
        url=$(yq ".components.${comp}.manifests[${i}].url // \"\"" "$MANIFEST" 2>/dev/null || echo "")

        dest="${MANIFESTS_DIR}/$(basename "$path")"

        if [ -f "$dest" ]; then
            info "已存在: ${name}"
            continue
        fi

        if [ -n "$url" ]; then
            download_with_progress "$url" "$dest" "$name"
        fi
    done
done

ok "K8s Manifest 下载完成"
