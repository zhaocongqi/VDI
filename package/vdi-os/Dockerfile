ARG BASE_OS_IMAGE=ubuntu:22.04
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64
ARG http_proxy
ARG https_proxy

ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}

# 安装基础工具、内核和 casper（live 启动必需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget jq \
    systemd systemd-sysv \
    linux-image-5.15.0-134-generic \
    initramfs-tools \
    casper \
    open-iscsi nfs-common \
    conntrack ipvsadm ebtables \
    && rm -rf /var/lib/apt/lists/*

# 生成 initrd（包含 casper 脚本）
RUN update-initramfs -u

# elemental (pre-downloaded)
COPY files/usr/bin/elemental /usr/bin/elemental
RUN chmod +x /usr/bin/elemental

# wharfie (pre-downloaded)
COPY files/usr/bin/wharfie /usr/bin/wharfie
RUN chmod +x /usr/bin/wharfie

# 清理代理环境变量（运行时不需要）
ENV http_proxy=
ENV https_proxy=

COPY files/ /
COPY vdi-release.yaml /etc/

# 启用 VDI 安装器服务，禁用默认 getty
RUN systemctl enable vdi-installer.service && \
    systemctl mask getty@tty1.service

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"$VDI_PRETTY_NAME\"/g" /etc/os-release
