#!/bin/bash -ex
# 安装构建工具（yq、helm、docker CLI）
# 在 Docker 构建中调用

ARCH=$(uname -m)
YQ_VERSION="${1:-v4.52.5}"
HELM_VERSION="${2:-v3.20.0}"
DOCKER_VERSION="${3:-29.6.0}"

# yq
curl -sSL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_${ARCH}" \
    -o /usr/bin/yq && chmod +x /usr/bin/yq

# helm
curl -sSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" \
    -o /tmp/helm.tar.gz
tar -xzf /tmp/helm.tar.gz -C /tmp
mv /tmp/linux-${ARCH}/helm /usr/bin/helm
chmod +x /usr/bin/helm
rm -rf /tmp/helm.tar.gz /tmp/linux-*

# docker CLI
curl -fsSL "https://download.docker.com/linux/static/stable/${ARCH}/docker-${DOCKER_VERSION}.tgz" \
    -o /tmp/docker.tgz
tar -xzf /tmp/docker.tgz -C /tmp
mv /tmp/docker/docker /usr/bin/docker
rm -rf /tmp/docker.tgz /tmp/docker

echo "=== Installed versions ==="
yq --version
helm version
docker --version
