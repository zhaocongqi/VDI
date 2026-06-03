#!/usr/bin/env bash
set -euo pipefail

# KubeKey kk 二进制下载脚本
# 用法: bash download-kk.sh [版本]
# 示例: bash download-kk.sh v4.1.7
#       bash download-kk.sh          # 下载最新版本

VERSION="${1:-latest}"
ARCH="linux-amd64"
INSTALL_DIR="/usr/local/bin"

if [ "$VERSION" = "latest" ]; then
    DOWNLOAD_URL="https://github.com/kubesphere/kubekey/releases/latest/download/kk-${ARCH}"
    echo ">>> 下载 kk 最新版本..."
else
    DOWNLOAD_URL="https://github.com/kubesphere/kubekey/releases/download/${VERSION}/kk-${ARCH}"
    echo ">>> 下载 kk ${VERSION}..."
fi

curl -fLo /tmp/kk "${DOWNLOAD_URL}"
chmod +x /tmp/kk
sudo mv /tmp/kk "${INSTALL_DIR}/kk"

echo ">>> kk 安装完成: ${INSTALL_DIR}/kk"
kk version
