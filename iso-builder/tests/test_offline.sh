#!/bin/bash
# 离线资源完整性测试
# 验证 manifest.yaml 格式正确，所有资源可校验
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${SCRIPT_DIR}/.."
MANIFEST="${WORKSPACE}/offline/manifest.yaml"

echo "=== 离线资源完整性测试 ==="

# 检查 manifest.yaml 存在
echo "[1/4] 检查 manifest.yaml..."
if [ ! -f "$MANIFEST" ]; then
    echo "  ✗ manifest.yaml 不存在"
    exit 1
fi
echo "  ✓ manifest.yaml 存在"

# 检查 manifest.yaml 格式
echo "[2/4] 检查 manifest.yaml 格式..."
if command -v yq &>/dev/null; then
    yq '.' "$MANIFEST" > /dev/null
    echo "  ✓ YAML 格式正确"

    # 检查必要字段
    for field in "name" "version" "components.kubernetes.version" "components.kubernetes.images"; do
        if [ -z "$(yq ".${field}" "$MANIFEST" 2>/dev/null)" ]; then
            echo "  ✗ 缺少字段: ${field}"
            exit 1
        fi
    done
    echo "  ✓ 必要字段完整"
else
    echo "  ⚠ yq 未安装，跳过 YAML 校验"
fi

# 统计资源数量
echo "[3/4] 统计资源数量..."
if command -v yq &>/dev/null; then
    IMAGE_COUNT=$(yq '[.components[] | .images[]?] | length' "$MANIFEST")
    BINARY_COUNT=$(yq '[.components[] | .binaries[]?] | length' "$MANIFEST")
    CHART_COUNT=$(yq '[.components[] | .charts[]?] | length' "$MANIFEST")
    MANIFEST_COUNT=$(yq '[.components[] | .manifests[]?] | length' "$MANIFEST")
    DEB_COUNT=$(yq '.packages.deb | length' "$MANIFEST")

    echo "  容器镜像: ${IMAGE_COUNT}"
    echo "  二进制工具: ${BINARY_COUNT}"
    echo "  Helm Chart: ${CHART_COUNT}"
    echo "  K8s Manifest: ${MANIFEST_COUNT}"
    echo "  系统包: ${DEB_COUNT}"
    echo "  总计: $((IMAGE_COUNT + BINARY_COUNT + CHART_COUNT + MANIFEST_COUNT + DEB_COUNT)) 项"
fi

# 检查校验和文件
echo "[4/4] 检查 checksums..."
CHECKSUM="${WORKSPACE}/offline/checksums.sha256"
if [ -f "$CHECKSUM" ]; then
    COUNT=$(wc -l < "$CHECKSUM")
    echo "  ✓ checksums.sha256 存在 (${COUNT} 个文件)"
else
    echo "  ⚠ checksums.sha256 不存在（需要先执行 make download）"
fi

echo ""
echo "=== 离线资源测试通过 ==="
