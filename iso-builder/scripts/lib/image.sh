#!/bin/bash
# 镜像拉取/保存/校验函数库
# 参考 Harvester scripts/lib/image 的设计模式

# 生成安全文件名：将 registry/path/image:tag 转换为 registry_path_image_tag
image_safe_name() {
    local image="$1"
    echo "$image" | sed 's|[/:]|_|g'
}

# 从 manifest.yaml 提取所有组件的所有镜像列表
# 输出格式: 每行一个 "component image_url"
image_list_all() {
    local manifest="$1"
    local components
    components=$(yq '.components | keys | .[]' "$manifest")

    for comp in $components; do
        local images
        images=$(yq ".components.${comp}.images[]" "$manifest" 2>/dev/null || true)
        [ -z "$images" ] && continue
        while IFS= read -r img; do
            echo "${comp} ${img}"
        done <<< "$images"
    done
}

# 下载单个镜像为 docker-archive + zstd 压缩
image_pull_and_compress() {
    local image="$1"
    local output_dir="$2"
    local component="$3"

    local safe_name
    safe_name=$(image_safe_name "$image")
    local tar_file="${output_dir}/${component}/${safe_name}.tar"
    local zst_file="${tar_file}.zst"

    if [ -f "$zst_file" ]; then
        echo "  [SKIP] ${image} (已存在)"
        return 0
    fi

    mkdir -p "${output_dir}/${component}"

    echo "  [PULL] ${image}"
    if ! skopeo copy --override-os linux --override-arch amd64 \
        "docker://${image}" "docker-archive:${tar_file}" 2>&1; then
        echo "  [FAIL] ${image}" >&2
        rm -f "$tar_file"
        return 1
    fi

    echo "  [COMPRESS] ${safe_name}.tar -> ${safe_name}.tar.zst"
    zstd -19 "$tar_file" -o "$zst_file" --rm -q

    echo "  [OK] ${image}"
    return 0
}

# 解压并导入单个镜像到 containerd
image_decompress_and_import() {
    local zst_file="$1"
    local tar_file="${zst_file%.zst}"

    if [ ! -f "$zst_file" ]; then
        echo "[FAIL] 文件不存在: ${zst_file}" >&2
        return 1
    fi

    echo "  [DECOMPRESS] $(basename "$zst_file")"
    zstd -d "$zst_file" -o "$tar_file" -f -q

    echo "  [IMPORT] ${tar_file}"
    if ctr -n k8s.io images import "$tar_file" 2>/dev/null; then
        rm -f "$tar_file"
        return 0
    else
        rm -f "$tar_file"
        echo "  [FAIL] ctr import 失败" >&2
        return 1
    fi
}
