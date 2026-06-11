#!/bin/bash
set -euo pipefail

# 生成 cache/bundle/metadata.yaml 结构化索引

SELF="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-v1.0.0}"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
BUNDLE_DIR="${WORKSPACE}/cache/bundle"
META_FILE="${BUNDLE_DIR}/metadata.yaml"

require_cmds yq

# Header
cat > "$META_FILE" << HEADER
# VDI 离线资源索引
# 由 build-bundle 自动生成，请勿手动编辑
version: "${VERSION}"
created: "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
platform: amd64
HEADER

# Images
echo "images:" >> "$META_FILE"
COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")
for comp in $COMPONENTS; do
    images=$(yq ".components.${comp}.images[]" "$MANIFEST" 2>/dev/null || true)
    [ -z "$images" ] && continue
    while IFS= read -r image; do
        [ -z "$image" ] && continue
        safe_name=$(echo "$image" | sed 's|[/:]|_|g')
        zst_file="${BUNDLE_DIR}/images/${comp}/${safe_name}.tar.zst"
        if [ -f "$zst_file" ]; then
            digest=$(sha256_file "$zst_file")
            name="${image%:*}"
            tag="${image##*:}"
            cat >> "$META_FILE" << ENTRY
  - name: "${name}"
    tag: "${tag}"
    file: "images/${comp}/${safe_name}.tar.zst"
    digest: "sha256:${digest}"
ENTRY
        fi
    done <<< "$images"
done

# Binaries
echo "binaries:" >> "$META_FILE"
for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.binaries | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue
    for i in $(seq 0 $((count - 1))); do
        name=$(yq ".components.${comp}.binaries[${i}].name" "$MANIFEST")
        version=$(yq ".components.${comp}.binaries[${i}].version" "$MANIFEST")
        bin_file="${BUNDLE_DIR}/binaries/${name}"
        if [ -f "$bin_file" ]; then
            digest=$(sha256_file "$bin_file")
            cat >> "$META_FILE" << ENTRY
  - name: "${name}"
    version: "${version}"
    file: "binaries/${name}"
    digest: "sha256:${digest}"
ENTRY
        fi
    done
done

# Charts
echo "charts:" >> "$META_FILE"
for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.charts | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue
    for i in $(seq 0 $((count - 1))); do
        chart_name=$(yq ".components.${comp}.charts[${i}].name" "$MANIFEST")
        chart_dir="${BUNDLE_DIR}/charts/${chart_name}"
        if [ -d "$chart_dir" ] && [ -f "${chart_dir}/Chart.yaml" ]; then
            chart_version=$(yq '.version' "${chart_dir}/Chart.yaml" 2>/dev/null || echo "unknown")
            tgz_file="${BUNDLE_DIR}/charts/${chart_name}-${chart_version}.tgz"
            if [ ! -f "$tgz_file" ]; then
                tar -czf "$tgz_file" -C "${BUNDLE_DIR}/charts" "${chart_name}"
            fi
            digest=$(sha256_file "$tgz_file")
            cat >> "$META_FILE" << ENTRY
  - name: "${chart_name}"
    version: "${chart_version}"
    file: "charts/${chart_name}-${chart_version}.tgz"
    digest: "sha256:${digest}"
ENTRY
        fi
    done
done

ok "metadata.yaml 已生成: ${META_FILE}"
