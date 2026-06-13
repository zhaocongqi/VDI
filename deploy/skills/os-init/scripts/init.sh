#!/bin/bash
set -euo pipefail

# OS 初始化脚本 — 为 K8s 集群部署准备操作系统环境
# 被 TUI installer 的 DeployEngine 调用（step_id: os-init）
# 幂等设计：重复执行安全

LOG_TAG="[os-init]"

echo "$LOG_TAG 开始操作系统初始化..."

# ── 1. 关闭 swap ──
echo "$LOG_TAG 关闭 swap..."
swapoff -a 2>/dev/null || true
sed -i '/swap/d' /etc/fstab 2>/dev/null || true
echo "$LOG_TAG swap 已关闭"

# ── 2. 加载内核模块 ──
echo "$LOG_TAG 配置内核模块..."
cat > /etc/modules-load.d/k8s.conf <<EOF
br_netfilter
overlay
nf_conntrack
EOF
modprobe overlay 2>/dev/null || true
modprobe br_netfilter 2>/dev/null || true
modprobe nf_conntrack 2>/dev/null || true
echo "$LOG_TAG 内核模块已加载"

# ── 3. 配置内核参数 ──
echo "$LOG_TAG 配置 sysctl 参数..."
cat > /etc/sysctl.d/99-k8s.conf <<EOF
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-arptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
net.ipv4.ip_nonlocal_bind           = 1
vm.overcommit_memory                = 1
vm.panic_on_oom                     = 0
fs.inotify.max_user_watches         = 1048576
fs.inotify.max_user_instances       = 8192
EOF
sysctl --system > /dev/null 2>&1 || true
echo "$LOG_TAG sysctl 参数已生效"

# ── 4. 关闭防火墙 ──
echo "$LOG_TAG 关闭防火墙..."
ufw disable 2>/dev/null || true
iptables -F 2>/dev/null || true
echo "$LOG_TAG 防火墙已关闭"

# ── 5. 配置时间同步 ──
echo "$LOG_TAG 配置时间同步..."
if command -v chronyd &>/dev/null; then
    chronyd -q 2>/dev/null || true
fi
timedatectl set-ntp true 2>/dev/null || true
echo "$LOG_TAG 时间同步已配置"

# ── 6. 安装基础依赖 ──
echo "$LOG_TAG 安装基础依赖..."
if [ -n "${OFFLINE_PACKAGES:-}" ] && [ -d "${OFFLINE_PACKAGES}" ]; then
    # 离线模式：从本地 deb 包安装
    dpkg -i "${OFFLINE_PACKAGES}"/*.deb 2>/dev/null || true
    apt-get install -y -f 2>/dev/null || true
else
    # 在线模式
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq \
        curl wget git jq socat conntrack \
        ebtables ethtool ipvsadm nfs-common \
        open-iscsi chrony 2>/dev/null || true
fi

systemctl enable --now iscsid 2>/dev/null || true
systemctl enable --now open-iscsi 2>/dev/null || true
echo "$LOG_TAG 基础依赖已安装"

# ── 7. 免密 sudo（如果当前非 root）──
CURRENT_USER="${SUDO_USER:-$(whoami)}"
if [ "$CURRENT_USER" != "root" ]; then
    echo "$CURRENT_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${CURRENT_USER}"
    chmod 440 "/etc/sudoers.d/${CURRENT_USER}"
    echo "$LOG_TAG 已为 ${CURRENT_USER} 配置免密 sudo"
fi

# ── 8. 验证 ──
echo "$LOG_TAG 验证初始化结果..."
SWAP_STATUS=$(swapon --show 2>/dev/null || true)
IP_FORWARD=$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo "0")
BRIDGE_NF=$(cat /proc/sys/net/bridge/bridge-nf-call-iptables 2>/dev/null || echo "0")

if [ -z "$SWAP_STATUS" ] && [ "$IP_FORWARD" = "1" ]; then
    echo "$LOG_TAG 初始化验证通过 ✓"
else
    echo "$LOG_TAG 初始化验证警告: swap=${SWAP_STATUS:-无} ip_forward=${IP_FORWARD} bridge-nf=${BRIDGE_NF}"
fi

echo "$LOG_TAG 操作系统初始化完成"
