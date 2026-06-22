ARG BASE_OS_IMAGE=bclinux:21.10U5
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64

# 安装基础工具、内核和 live 启动必需组件
RUN dnf install -y \
    curl wget jq \
    systemd \
    kernel \
    dracut dracut-live \
    iproute iputils net-tools NetworkManager \
    openssh-server \
    iscsi-initiator-utils nfs-utils \
    conntrack-tools ipvsadm ebtables \
    squashfs-tools \
    && dnf clean all

# 获取内核版本并生成 initrd（包含 dmsquash-live 模块用于 live 启动）
RUN KERNEL_VERSION=$(ls /lib/modules/ | head -1) && \
    dracut --force --add "dmsquash-live" "/boot/initrd.img-${KERNEL_VERSION}"

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
# 启用串口 getty
RUN systemctl enable serial-getty@ttyS0.service
# 启用网络接口自动激活
RUN systemctl enable vdi-network-setup.service

# 禁用 systemd-networkd，改用 NetworkManager 管理所有网络接口
RUN systemctl disable systemd-networkd systemd-networkd-wait-online systemd-resolved 2>/dev/null || true && \
    systemctl enable NetworkManager

# 配置 NetworkManager 管理所有接口
RUN mkdir -p /etc/NetworkManager/conf.d && \
    printf "[keyfile]\nunmanaged-devices=none\n" > /etc/NetworkManager/conf.d/10-manage-all.conf

# 设置默认密码（root/vdi123）方便调试
RUN echo 'root:vdi123' | chpasswd

# 启用 SSH 服务，允许 root 密码登录
RUN systemctl enable sshd && \
    mkdir -p /etc/ssh/sshd_config.d && \
    printf "PermitRootLogin yes\nPasswordAuthentication yes\n" > /etc/ssh/sshd_config.d/allow-root.conf

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"$VDI_PRETTY_NAME\"/g" /etc/os-release
