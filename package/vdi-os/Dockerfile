ARG BASE_OS_IMAGE=bclinux:21.10U5
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64

# 安装 dracut + VDI 依赖
# 注意：BCLinux 仓库无 dracut-live 包，dmsquash-live 模块通过 files/ 注入（见 COPY）
# 本地 BCLinux 仓库通过 buildx bind mount 挂载到 /iso
# 构建命令：
#   docker buildx build \
#     --build-context bclinux-repo=/path/to/bclinux-repo \
#     -t rancher/vdi-os:test --load .
RUN --mount=type=bind,from=bclinux-repo,source=.,target=/iso,rw \
    printf "[bclinux]\nname=BCLinux\nbaseurl=file:///iso\nenabled=1\ngpgcheck=0\n" \
        > /etc/yum.repos.d/bclinux.repo && \
    dnf install -y \
    dracut \
    squashfs-tools \
    NetworkManager \
    openssh-server \
    iproute iputils net-tools \
    conntrack-tools \
    iscsi-initiator-utils nfs-utils \
    ebtables ipvsadm \
    && dnf clean all && \
    rm -f /etc/yum.repos.d/bclinux.repo

# 注入 VDI 文件（含 systemd service、脚本、manifests 等）
COPY files/ /
COPY vdi-release.yaml /etc/

# elemental / wharfie 二进制（COPY files/ 已包含，此处显式 chmod）
RUN chmod +x /usr/bin/elemental /usr/bin/wharfie

# 配置 systemd：禁用 Anaconda 残留，启用 VDI 服务
RUN systemctl set-default multi-user.target && \
    systemctl disable anaconda.service anaconda-direct.service 2>/dev/null || true && \
    systemctl enable vdi-setup-installer.service vdi-network-setup.service 2>/dev/null || true && \
    systemctl enable NetworkManager sshd 2>/dev/null || true

# 禁用 systemd-networkd，改用 NetworkManager 管理所有网络接口
RUN systemctl disable systemd-networkd systemd-networkd-wait-online systemd-resolved 2>/dev/null || true && \
    systemctl enable NetworkManager

# 配置 NetworkManager 管理所有接口
RUN mkdir -p /etc/NetworkManager/conf.d && \
    printf "[keyfile]\nunmanaged-devices=none\n" > /etc/NetworkManager/conf.d/10-manage-all.conf

# 配置 SSH：允许 root 密码登录
RUN mkdir -p /etc/ssh/sshd_config.d && \
    printf "PermitRootLogin yes\nPasswordAuthentication yes\n" > /etc/ssh/sshd_config.d/allow-root.conf

# 创建安装器 drop-in 覆盖（在构建时完成，而非运行时）
# 覆盖 VGA console (tty1) 和 serial console (ttyS0)
RUN mkdir -p /etc/systemd/system/getty@tty1.service.d && \
    cat > /etc/systemd/system/getty@tty1.service.d/override.conf <<"EOF"
[Service]
ExecStartPre=/usr/bin/setterm --msg off
ExecStartPre=/usr/bin/kill -s 55 1
ExecStopPost=/usr/bin/kill -s 54 1
ExecStart=
ExecStart=-/sbin/agetty -n -l /usr/bin/start-installer.sh %I $TERM
EOF
RUN mkdir -p /etc/systemd/system/serial-getty@ttyS0.service.d && \
    cat > /etc/systemd/system/serial-getty@ttyS0.service.d/override.conf <<"EOF"
[Service]
ExecStartPre=/usr/bin/kill -s 55 1
ExecStopPost=/usr/bin/kill -s 54 1
ExecStart=
ExecStart=-/sbin/agetty -n -l /usr/bin/start-installer.sh %I $TERM
EOF
# 启用串口 getty（用于 serial console 安装）
RUN systemctl enable serial-getty@ttyS0.service

# 关键：用 dracut 重建 initrd（包含 dmsquash-live 模块）
# --no-hostonly: 避免 dracut 读宿主机内核（容器内 /proc/sys/kernel/osrelease 是宿主内核）
# --kver: 明确指定容器内的 BCLinux 内核版本
RUN KERNEL_VERSION=$(ls /lib/modules/ | head -1) && \
    echo "重建 initrd for kernel ${KERNEL_VERSION}" && \
    dracut -f --no-hostonly --kver "${KERNEL_VERSION}" --add dmsquash-live \
        "/boot/initrd-${KERNEL_VERSION}" && \
    ls -la /boot/initrd-${KERNEL_VERSION}

# 设置默认密码（root/vdi123）方便调试
RUN echo 'root:vdi123' | chpasswd

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"${VDI_PRETTY_NAME}\"/g" /etc/os-release
