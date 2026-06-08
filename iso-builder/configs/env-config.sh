#!/bin/bash
# VDI 离线部署环境配置模板
# 此文件由 TUI 安装器根据用户输入动态生成
# 格式与 deploy/env-config.sh 完全一致，确保部署脚本无需修改

# ========== 用户/SSH 配置 ==========
ANSIBLE_USER="${ANSIBLE_USER:-root}"

# ========== K8s 集群配置 ==========
K8S_VERSION="${K8S_VERSION:-v1.34.3}"
KUBEKEY_VERSION="${KUBEKEY_VERSION:-v4.0.4}"

# ========== 网络配置 ==========
SVC_CIDR="${SVC_CIDR:-10.96.0.0/12}"
POD_CIDR="${POD_CIDR:-10.16.0.0/16}"
JOIN_CIDR="${JOIN_CIDR:-100.64.0.0/16}"

# ========== kube-vip 配置 ==========
VIP="${VIP:-192.168.220.100}"
VIP_INTERFACE="${VIP_INTERFACE:-ens160}"

# ========== Longhorn 存储配置 ==========
LONGHORN_DISK="${LONGHORN_DISK:-/dev/sdb}"
LONGHORN_DATA_DIR="${LONGHORN_DATA_DIR:-/var/lib/longhorn}"

# ========== KubeVirt 配置 ==========
KUBEVIRT_VERSION="${KUBEVIRT_VERSION:-v1.5.0}"
CDI_VERSION="${CDI_VERSION:-v1.61.0}"

# ========== 时间同步 ==========
NTP_SERVER="${NTP_SERVER:-ntp.aliyun.com}"

# ========== 离线环境变量（ISO 挂载后自动设置）==========
# 检测 ISO 挂载点
if [ -d /cdrom/offline ]; then
    OFFLINE_BASE="/cdrom/offline"
elif [ -d /mnt/iso/offline ]; then
    OFFLINE_BASE="/mnt/iso/offline"
fi

if [ -n "${OFFLINE_BASE:-}" ]; then
    export OFFLINE_BASE
    export OFFLINE_BINARIES="${OFFLINE_BASE}/binaries"
    export OFFLINE_IMAGES="${OFFLINE_BASE}/images"
    export OFFLINE_CHARTS="${OFFLINE_BASE}/charts"
    export OFFLINE_MANIFESTS="${OFFLINE_BASE}/k8s-manifests"
    export OFFLINE_PACKAGES="${OFFLINE_BASE}/packages/deb"

    # 将离线工具加入 PATH
    export PATH="${OFFLINE_BINARIES}:${PATH}"

    echo "[离线模式] 资源路径: ${OFFLINE_BASE}"
fi

# ========== Ansible 清单 ==========
ANSIBLE_HOSTS_FILE="${ANSIBLE_HOSTS_FILE:-/etc/ansible/hosts}"
