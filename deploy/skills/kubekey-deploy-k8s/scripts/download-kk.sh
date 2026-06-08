#!/usr/bin/env bash
set -euo pipefail

# KubeKey kk 二进制下载脚本（v4.x）
# 用法: bash download-kk.sh [版本]
# 示例: bash download-kk.sh v4.0.4
#       bash download-kk.sh          # 从 env-config.sh 读取默认版本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

# 尝试从 env-config.sh 读取默认版本
DEFAULT_VERSION="v4.0.4"
if [ -f "${PROJECT_DIR}/deploy/env-config.sh" ]; then
  source "${PROJECT_DIR}/deploy/env-config.sh"
  DEFAULT_VERSION="${KUBEKEY_VERSION:-v4.0.4}"
fi

VERSION="${1:-${DEFAULT_VERSION}}"
ARCH="linux-amd64"
INSTALL_DIR="/usr/local/bin"
TMP_DIR=$(mktemp -d)

DOWNLOAD_URL="https://github.com/kubesphere/kubekey/releases/download/${VERSION}/kubekey-${VERSION}-${ARCH}.tar.gz"
echo ">>> 下载 KubeKey ${VERSION}..."

if ! curl -fLo "${TMP_DIR}/kubekey.tar.gz" "${DOWNLOAD_URL}"; then
  echo "错误: 下载失败，请确认版本号 ${VERSION} 是否正确" >&2
  echo "可用版本列表: https://github.com/kubesphere/kubekey/releases" >&2
  rm -rf "${TMP_DIR}"
  exit 1
fi

tar -xzf "${TMP_DIR}/kubekey.tar.gz" -C "${TMP_DIR}/"
chmod +x "${TMP_DIR}/kk"
sudo mv "${TMP_DIR}/kk" "${INSTALL_DIR}/kk"
rm -rf "${TMP_DIR}"

echo ">>> kk 安装完成: ${INSTALL_DIR}/kk"
kk version
