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

# 创建安装器 drop-in 覆盖（在构建时完成，而非运行时）
# 覆盖 VGA console (tty1) 和 serial console (ttyS0)
RUN mkdir -p /etc/systemd/system/getty@tty1.service.d && \
    cat > /etc/systemd/system/getty@tty1.service.d/override.conf <<"EOF"
[Service]
ExecStartPre=/usr/bin/setterm --msg off
ExecStartPre=/usr/bin/kill -s 55 1
ExecStopPost=/usr/bin/kill -s 54 1
ExecStart=
ExecStart=-/sbin/agetty -n -l /usr/bin/start-installer.sh %I \$TERM
EOF
RUN mkdir -p /etc/systemd/system/serial-getty@ttyS0.service.d && \
    cat > /etc/systemd/system/serial-getty@ttyS0.service.d/override.conf <<"EOF"
[Service]
ExecStartPre=/usr/bin/kill -s 55 1
ExecStopPost=/usr/bin/kill -s 54 1
ExecStart=
ExecStart=-/sbin/agetty -n -l /usr/bin/start-installer.sh %I \$TERM
EOF
# 启用串口 getty（Ubuntu live 环境默认不启用）
RUN systemctl enable serial-getty@ttyS0.service
# 启用网络接口自动激活（参考 Harvester 90_network.yaml）
RUN systemctl enable vdi-network-setup.service

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"$VDI_PRETTY_NAME\"/g" /etc/os-release
