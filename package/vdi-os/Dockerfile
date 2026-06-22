ARG BASE_OS_IMAGE=ubuntu:22.04
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64

# 安装基础工具、内核和 casper（live 启动必需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget jq \
    systemd systemd-sysv \
    linux-image-5.15.0-134-generic \
    initramfs-tools \
    casper \
    iproute2 iputils-ping net-tools network-manager \
    openssh-server \
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

# 禁用 systemd-networkd，改用 NetworkManager 管理所有网络接口
RUN systemctl disable systemd-networkd systemd-networkd-wait-online systemd-resolved 2>/dev/null || true && \
    systemctl enable NetworkManager

# 配置 NetworkManager 管理所有接口
# 1. 移除 ifupdown 插件
RUN sed -i 's/plugins=ifupdown,keyfile/plugins=keyfile/' /etc/NetworkManager/NetworkManager.conf && \
    sed -i '/^\[ifupdown\]/,/^\[/{s/managed=false/managed=true/}' /etc/NetworkManager/NetworkManager.conf

# 2. 覆盖 Ubuntu 默认的 "只管 WiFi" 策略（10-globally-managed-devices.conf）
RUN mkdir -p /etc/NetworkManager/conf.d && \
    printf "[keyfile]\nunmanaged-devices=none\n" > /etc/NetworkManager/conf.d/10-manage-all.conf

# 3. 配置 Netplan 使用 NetworkManager
RUN mkdir -p /etc/netplan && \
    printf "network:\n  version: 2\n  renderer: NetworkManager\n" > /etc/netplan/01-network-manager.yaml

# 设置默认密码（root/vdi123）方便调试
RUN echo 'root:vdi123' | chpasswd

# 启用 SSH 服务，允许 root 密码登录
RUN systemctl enable ssh && \
    mkdir -p /etc/ssh/sshd_config.d && \
    printf "PermitRootLogin yes\nPasswordAuthentication yes\n" > /etc/ssh/sshd_config.d/allow-root.conf

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"$VDI_PRETTY_NAME\"/g" /etc/os-release
