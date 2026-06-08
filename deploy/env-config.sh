#!/usr/bin/env bash
# ============================================================
# VDI 集群部署 — 共享环境配置
# ============================================================
# 用法: source deploy/env-config.sh
#
# 所有部署脚本和 skill 通过此文件读取共享参数。
# 修改此文件即可全局生效，无需逐个脚本修改。
# ============================================================

# ── SSH / Ansible 用户 ──
# 用于 Ansible 命令的 -u 参数和 SSH 连接
ANSIBLE_USER="${ANSIBLE_USER:-zcq}"

# ── K8s 集群版本 ──
K8S_VERSION="${K8S_VERSION:-v1.34.3}"
KUBEKEY_VERSION="${KUBEKEY_VERSION:-v4.0.4}"

# ── 网络配置 ──
# Service CIDR — kubekey config.yaml 和 kube-ovn values.yaml 必须保持一致
SVC_CIDR="${SVC_CIDR:-10.96.0.0/12}"
# Pod CIDR
POD_CIDR="${POD_CIDR:-10.16.0.0/16}"
# Join CIDR（Kube-OVN 隧道网段）
JOIN_CIDR="${JOIN_CIDR:-100.64.0.0/16}"

# ── kube-vip 配置 ──
VIP="${VIP:-192.168.220.100}"
VIP_INTERFACE="${VIP_INTERFACE:-ens160}"

# ── Longhorn 配置 ──
# 专用存储磁盘设备名（所有节点应一致，如不一致需逐节点配置）
LONGHORN_DISK="${LONGHORN_DISK:-/dev/sdb}"
LONGHORN_DATA_DIR="${LONGHORN_DATA_DIR:-/var/lib/longhorn}"

# ── KubeVirt 配置 ──
KUBEVIRT_VERSION="${KUBEVIRT_VERSION:-v1.5.0}"
CDI_VERSION="${CDI_VERSION:-v1.61.0}"

# ── NTP 服务器 ──
NTP_SERVER="${NTP_SERVER:-ntp.aliyun.com}"

# ── Ansible 清单文件 ──
ANSIBLE_HOSTS_FILE="${ANSIBLE_HOSTS_FILE:-deploy/hosts}"

echo "[env-config] 配置已加载"
echo "  ANSIBLE_USER    = ${ANSIBLE_USER}"
echo "  K8S_VERSION     = ${K8S_VERSION}"
echo "  SVC_CIDR        = ${SVC_CIDR}"
echo "  POD_CIDR        = ${POD_CIDR}"
echo "  VIP             = ${VIP}"
echo "  LONGHORN_DISK   = ${LONGHORN_DISK}"
echo "  KUBEVIRT_VERSION= ${KUBEVIRT_VERSION}"
