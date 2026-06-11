#!/bin/bash
set -euo pipefail

# 下载容器镜像（docker-archive + zstd 压缩）

SELF="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"
source "${SCRIPT_DIR}/../lib/image.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
IMAGES_DIR="${WORKSPACE}/cache/bundle/images"

require_cmds skopeo zstd yq

COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")

total_images=0
downloaded=0
failed=0

for comp in $COMPONENTS; do
    images=$(yq ".components.${comp}.images[]" "$MANIFEST" 2>/dev/null || true)
    [ -z "$images" ] && continue

    mkdir -p "${IMAGES_DIR}/${comp}"

    echo ""
    step "组件 ${comp}: $(echo "$images" | wc -l) 个镜像"

    while IFS= read -r image; do
        [ -z "$image" ] && continue
        total_images=$((total_images + 1))

        safe_name=$(image_safe_name "$image")
        zst_file="${IMAGES_DIR}/${comp}/${safe_name}.tar.zst"

        if [ -f "$zst_file" ]; then
            info "已存在: ${image}"
            downloaded=$((downloaded + 1))
            continue
        fi

        if image_pull_and_compress "$image" "$IMAGES_DIR" "$comp"; then
            downloaded=$((downloaded + 1))
        else
            failed=$((failed + 1))
        fi
    done <<< "$images"
done

echo ""
echo "镜像下载统计: 总计=${total_images} 成功=${downloaded} 失败=${failed}"
if [ "$failed" -gt 0 ]; then
    warn "有 ${failed} 个镜像下载失败"
fi
ok "镜像下载完成: ${downloaded}/${total_images} 成功"
