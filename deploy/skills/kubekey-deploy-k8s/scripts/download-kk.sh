#!/usr/bin/env bash
set -euo pipefail

# KubeKey kk 二进制下载脚本（v4.x）
# 用法: bash download-kk.sh [版本]
# 示例: bash download-kk.sh v4.0.4
#       bash download-kk.sh          # 下载 v4.0.4

VERSION="${1:-v4.0.4}"
ARCH="linux-amd64"
INSTALL_DIR="/usr/local/bin"
TMP_DIR=$(mktemp -d)

DOWNLOAD_URL="https://github.com/kubesphere/kubekey/releases/download/${VERSION}/kubekey-${VERSION}-${ARCH}.tar.gz"
echo ">>> 下载 KubeKey ${VERSION}..."

curl -fLo "${TMP_DIR}/kubekey.tar.gz" "${DOWNLOAD_URL}"
tar -xzf "${TMP_DIR}/kubekey.tar.gz" -C "${TMP_DIR}/"
chmod +x "${TMP_DIR}/kk"
sudo mv "${TMP_DIR}/kk" "${INSTALL_DIR}/kk"
rm -rf "${TMP_DIR}"

echo ">>> kk 安装完成: ${INSTALL_DIR}/kk"
kk version
