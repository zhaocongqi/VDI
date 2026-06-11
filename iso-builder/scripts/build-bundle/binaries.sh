#!/bin/bash
set -euo pipefail

# 下载二进制工具

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
BINARIES_DIR="${WORKSPACE}/cache/bundle/binaries"

require_cmds wget yq

mkdir -p "$BINARIES_DIR"

COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")

for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.binaries | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue

    step "组件 ${comp}: ${count} 个二进制"

    for i in $(seq 0 $((count - 1))); do
        name=$(yq ".components.${comp}.binaries[${i}].name" "$MANIFEST")
        url=$(yq ".components.${comp}.binaries[${i}].url" "$MANIFEST")
        version=$(yq ".components.${comp}.binaries[${i}].version" "$MANIFEST")

        dest="${BINARIES_DIR}/${name}"

        if [ -f "$dest" ]; then
            info "已存在: ${name} v${version}"
            continue
        fi

        echo -e "  ${YELLOW}[下载]${NC} ${name} v${version}"

        case "$url" in
            *.tar.gz)
                tmpfile="${BINARIES_DIR}/$(basename "$url")"
                download_with_progress "$url" "$tmpfile" "${name}"
                tar -xzf "$tmpfile" -C "$BINARIES_DIR"
                if [ ! -f "$dest" ]; then
                    found=$(find "$BINARIES_DIR" -name "$name" -type f | head -1)
                    [ -n "$found" ] && mv "$found" "$dest"
                fi
                rm -f "$tmpfile"
                ;;
            *)
                download_with_progress "$url" "$dest" "${name}"
                ;;
        esac
        chmod +x "$dest"
    done
done

info "已下载的二进制:"
ls -lh "$BINARIES_DIR"
ok "二进制工具下载完成"
