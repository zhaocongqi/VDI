ARG BASE_OS_IMAGE=ubuntu:22.04
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64

# elemental
ARG ELEMENTAL_VERSION=v0.10.0
RUN curl -sfL "https://github.com/rancher/elemental/releases/download/${ELEMENTAL_VERSION}/elemental-${ARCH}" \
    -o /usr/bin/elemental && chmod +x /usr/bin/elemental

# wharfie
ARG WHARFIE_VERSION=v0.6.8
RUN curl -sfL "https://github.com/rancher/wharfie/releases/download/${WHARFIE_VERSION}/wharfie-${ARCH}" \
    -o /usr/bin/wharfie && chmod +x /usr/bin/wharfie

# 系统组件
RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd systemd-sysv \
    open-iscsi nfs-common \
    conntrack ipvsadm ebtables \
    jq curl wget \
    && rm -rf /var/lib/apt/lists/*

COPY files/ /
COPY vdi-release.yaml /etc/

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"$VDI_PRETTY_NAME\"/g" /etc/os-release
