FROM golang:1.26-bookworm

ARG DAPPER_HOST_ARCH
ENV ARCH $DAPPER_HOST_ARCH

# 系统工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl gzip tar wget ca-certificates zstd squashfs-tools xorriso isolinux syslinux-common \
    gawk jq mtools dosfstools unzip rsync patch \
    && rm -rf /var/lib/apt/lists/*

# helm + yq + skopeo
ARG HELM_VERSION=v3.20.0
ARG YQ_VERSION=v4.52.5
ARG SKOPEO_VERSION=v1.18.0
RUN curl -sSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" | tar -xz -C /tmp linux-${ARCH}/helm && \
    mv /tmp/linux-${ARCH}/helm /usr/bin/helm && chmod +x /usr/bin/helm && \
    curl -sSL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_${ARCH}" -o /usr/bin/yq && \
    chmod +x /usr/bin/yq && \
    curl -sSL "https://github.com/lework/skopeo-build/releases/download/${SKOPEO_VERSION}/skopeo-linux-${ARCH}" -o /usr/bin/skopeo && \
    chmod +x /usr/bin/skopeo

ENV GOPROXY https://goproxy.cn,direct

ENV HOME /work
WORKDIR /work
