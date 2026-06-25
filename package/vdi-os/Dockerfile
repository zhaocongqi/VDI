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
# 打破 buildx 缓存：改动依赖列表时强制重新执行 dnf install（否则缓存命中旧层）
ARG DEP_BUST=2026-06-25-disableplugin
RUN --mount=type=bind,from=bclinux-repo,source=.,target=/iso,rw \
    printf "[bclinux]\nname=BCLinux\nbaseurl=file:///iso\nenabled=1\ngpgcheck=0\n" \
        > /etc/yum.repos.d/bclinux.repo && \
    echo "dep-bust=${DEP_BUST}" && \
    dnf --disableplugin=* install -y \
    dracut \
    squashfs-tools \
    dosfstools \
    lvm2 \
    NetworkManager \
    openssh-server \
    iproute iputils net-tools \
    conntrack-tools \
    open-iscsi nfs-utils \
    ebtables ipvsadm \
    && dnf --disableplugin=* clean all && \
    rm -f /etc/yum.repos.d/bclinux.repo

# elemental build-iso 需要 EFI 引导文件在 /usr/share/efi/x86_64/
# BCLinux shim/grub2-efi 包的 dnf 安装可能因许可证问题失败，直接从 RPM 提取
# 注意：elemental 会把 grub.efi 复制到 EFI/BOOT/，但 BCLinux shim 硬编码找 grubx64.efi
# 所以需要同时保留 grub.efi（给 elemental）和 grubx64.efi（给 shim）
RUN --mount=type=bind,from=bclinux-repo,source=.,target=/iso,rw \
    mkdir -p /tmp/efi-extract /usr/share/efi/x86_64 /usr/share/grub2/x86_64-efi && \
    cd /tmp/efi-extract && \
    rpm2cpio /iso/Packages/shim-*.rpm 2>/dev/null | cpio -idm 2>/dev/null && \
    rpm2cpio /iso/Packages/grub2-efi-x64-*.rpm 2>/dev/null | cpio -idm 2>/dev/null && \
    cp ./boot/efi/EFI/bclinux/shimx64.efi /usr/share/efi/x86_64/shim.efi && \
    cp ./boot/efi/EFI/bclinux/mmx64.efi /usr/share/efi/x86_64/MokManager.efi && \
    cp ./boot/efi/EFI/bclinux/grubx64.efi /usr/share/efi/x86_64/grubx64.efi && \
    cp ./boot/efi/EFI/bclinux/grubx64.efi /usr/share/efi/x86_64/grub.efi && \
    cp ./boot/efi/EFI/bclinux/grubx64.efi /usr/share/grub2/x86_64-efi/grubx64.efi && \
    cp ./boot/efi/EFI/bclinux/grubx64.efi /usr/share/grub2/x86_64-efi/grub.efi && \
    cp ./boot/efi/EFI/bclinux/fbx64.efi /usr/share/efi/x86_64/fbx64.efi 2>/dev/null || true && \
    rm -rf /tmp/efi-extract && \
    ls -la /usr/share/efi/x86_64/ && \
    ls -la /usr/share/grub2/x86_64-efi/

# 注入 VDI 文件（含 systemd service、脚本、manifests 等）
COPY files/ /
COPY vdi-release.yaml /etc/

# elemental / wharfie / yip 二进制（COPY files/ 已包含，此处显式 chmod）
RUN chmod +x /usr/bin/elemental /usr/bin/wharfie /usr/bin/yip

# 创建 rancher 用户（applyPassword 通过 yip 配置 rancher 用户密码；BCLinux 基础镜像无此用户）
RUN useradd -m -s /bin/bash rancher || true

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

# 安装器 drop-in 由运行时 setup-installer.sh 创建（对齐 harvester）：
# 根据 /sys/class/tty/console/active 只为第一个 VGA tty 创建 getty override，
# 避免多个 vdi-installer 实例争用键盘导致 TUI 串行/叠加。
# 此前在构建时静态创建 tty1 + ttyS0 override，叠加 console=tty0 会导致
# tty0/tty1/ttyS0 三个 getty 同时跑 vdi-installer。

# 关键：用 dracut 重建 initrd（包含 dmsquash-live 模块）
# --no-hostonly: 避免 dracut 读宿主机内核（容器内 /proc/sys/kernel/osrelease 是宿主内核）
# --kver: 明确指定容器内的 BCLinux 内核版本
# 重建后覆盖所有 initramfs（含 rescue），否则 elemental build-iso 会用 BCLinux 默认的
# initramfs-0-rescue-*.img（无 dmsquash-live），导致 root=live:CDLABEL 引导失败
RUN KERNEL_VERSION=$(ls /lib/modules/ | head -1) && \
    echo "重建 initrd for kernel ${KERNEL_VERSION}" && \
    dracut -f --no-hostonly --kver "${KERNEL_VERSION}" --add dmsquash-live \
        "/boot/initrd-${KERNEL_VERSION}" && \
    cp -f "/boot/initrd-${KERNEL_VERSION}" "/boot/initramfs-${KERNEL_VERSION}.img" && \
    for r in /boot/initramfs-0-rescue-*.img; do \
        [ -e "$r" ] && cp -f "/boot/initrd-${KERNEL_VERSION}" "$r" && echo "覆盖 $r"; \
    done; \
    ls -la /boot/initrd-* /boot/initramfs-*

# 设置默认密码（root/vdi123）方便调试
# 使用 openssl 生成加密密码，避免 chpasswd 的 PAM 问题
RUN echo "root:$(openssl passwd -6 vdi123)" | chpasswd -e

# 配置 SSH 服务
# 1. 确保 sshd_config 存在（BCLinux 可能不生成默认配置）
RUN if [ ! -f /etc/ssh/sshd_config ]; then \
        printf "# VDI sshd configuration\n\
Port 22\n\
ListenAddress 0.0.0.0\n\
ListenAddress ::\n\
HostKey /etc/ssh/ssh_host_rsa_key\n\
HostKey /etc/ssh/ssh_host_ecdsa_key\n\
HostKey /etc/ssh/ssh_host_ed25519_key\n\
PermitRootLogin yes\n\
PasswordAuthentication yes\n\
ChallengeResponseAuthentication no\n\
UsePAM yes\n\
X11Forwarding no\n\
PrintMotd no\n\
AcceptEnv LANG LC_*\n\
Subsystem sftp /usr/libexec/openssh/sftp-server\n" > /etc/ssh/sshd_config; \
    fi

# 2. 生成 SSH 主机密钥
RUN rm -f /etc/ssh/ssh_host_*_key* 2>/dev/null && \
    ssh-keygen -A

# 禁用 kdump（Live 环境不需要）
RUN systemctl disable kdump 2>/dev/null || true

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"${VDI_PRETTY_NAME}\"/g" /etc/os-release
