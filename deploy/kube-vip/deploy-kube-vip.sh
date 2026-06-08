#!/usr/bin/env bash
set -euo pipefail

# kube-vip HA 部署脚本
# 将 static Pod manifest 分发到每个控制平面节点，实现真正的 HA
# 用法: bash deploy-kube-vip.sh [VIP] [INTERFACE]
# 示例: bash deploy-kube-vip.sh 192.168.220.100 ens160

VIP="${1:-192.168.220.100}"
INTERFACE="${2:-ens160}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST_TEMPLATE="${SCRIPT_DIR}/kube-vip.yaml"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
MANIFEST_DIR="/etc/kubernetes/manifests"
MANIFEST_NAME="kube-vip.yaml"
GENERATED_MANIFEST="/tmp/${MANIFEST_NAME}"

echo ">>> 部署 kube-vip（HA 模式）"
echo "    VIP: ${VIP}"
echo "    接口: ${INTERFACE}"

# ──────────────────────────────────────────────
# 1. 前置检查
# ──────────────────────────────────────────────
if ! command -v kubectl &>/dev/null; then
    echo "错误: kubectl 未安装" >&2
    exit 1
fi

if ! kubectl --kubeconfig "$KUBECONFIG" get nodes &>/dev/null; then
    echo "错误: 无法连接集群，请检查 KUBECONFIG" >&2
    exit 1
fi

if [ ! -f "$MANIFEST_TEMPLATE" ]; then
    echo "错误: 找不到 manifest 模板: ${MANIFEST_TEMPLATE}" >&2
    exit 1
fi

# ──────────────────────────────────────────────
# 2. 自动检测网络接口（如果指定 auto）
# ──────────────────────────────────────────────
if [ "$INTERFACE" = "auto" ]; then
    # 优先从默认路由获取主接口
    INTERFACE=$(ip -json route list default 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['dev'])" 2>/dev/null || true)
    if [ -z "$INTERFACE" ]; then
        echo "错误: 无法自动检测网络接口，请手动指定" >&2
        exit 1
    fi
    echo "    自动检测接口: ${INTERFACE}"
fi

# 验证接口在本机存在（参考接口名）
if ! ip link show "$INTERFACE" &>/dev/null; then
    echo "警告: 本机不存在接口 ${INTERFACE}，请确认所有节点使用相同接口名" >&2
fi

# ──────────────────────────────────────────────
# 3. 生成 manifest（替换 VIP 和接口）
# ──────────────────────────────────────────────
sed -e "s|value: ens160|value: ${INTERFACE}|g" \
    -e "s|value: 192.168.220.100|value: ${VIP}|g" \
    "$MANIFEST_TEMPLATE" > "$GENERATED_MANIFEST"

echo ">>> 已生成 manifest: ${GENERATED_MANIFEST}"

# ──────────────────────────────────────────────
# 4. 获取所有控制平面节点
# ──────────────────────────────────────────────
CP_NODES=$(kubectl --kubeconfig "$KUBECONFIG" get nodes -l node-role.kubernetes.io/control-plane -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}')
if [ -z "$CP_NODES" ]; then
    echo "错误: 未找到控制平面节点" >&2
    exit 1
fi

echo ">>> 控制平面节点: ${CP_NODES}"

# ──────────────────────────────────────────────
# 5. 将 manifest 分发到每个控制平面节点
# ──────────────────────────────────────────────
# 检查是否使用 Ansible hosts 文件
ANSIBLE_HOSTS="${SCRIPT_DIR}/../hosts"
USE_ANSIBLE=false
if command -v ansible &>/dev/null && [ -f "$ANSIBLE_HOSTS" ]; then
    USE_ANSIBLE=true
fi

if [ "$USE_ANSIBLE" = true ]; then
    echo ">>> 使用 Ansible 分发 manifest 到控制平面节点..."
    # 读取 ansible_user 从 hosts 模板或环境变量
    ANSIBLE_USER="${ANSIBLE_USER:-zcq}"

    for node_ip in $CP_NODES; do
        echo "    -> 分发到 ${node_ip}..."
        # 使用 ssh 直接分发（比 Ansible 单条命令更可靠）
        ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "${ANSIBLE_USER}@${node_ip}" \
            "sudo mkdir -p ${MANIFEST_DIR}" 2>/dev/null || true
        scp -o StrictHostKeyChecking=no "$GENERATED_MANIFEST" \
            "${ANSIBLE_USER}@${node_ip}:/tmp/${MANIFEST_NAME}" 2>/dev/null
        ssh -o StrictHostKeyChecking=no "${ANSIBLE_USER}@${node_ip}" \
            "sudo cp /tmp/${MANIFEST_NAME} ${MANIFEST_DIR}/${MANIFEST_NAME} && sudo rm -f /tmp/${MANIFEST_NAME}"
    done
else
    echo ">>> Ansible 未安装或 hosts 文件不存在，手动分发模式"
    echo "    请在每个控制平面节点上执行以下命令:"
    echo ""
    echo "    sudo mkdir -p ${MANIFEST_DIR}"
    echo "    sudo cp ${GENERATED_MANIFEST} ${MANIFEST_DIR}/${MANIFEST_NAME}"
    echo ""
    read -rp "    按 Enter 继续分发到本机节点，或 Ctrl+C 取消后手动分发..."
    # 至少分发到本机
    sudo mkdir -p "${MANIFEST_DIR}"
    sudo cp "$GENERATED_MANIFEST" "${MANIFEST_DIR}/${MANIFEST_NAME}"
fi

echo ">>> manifest 已分发到所有控制平面节点"

# ──────────────────────────────────────────────
# 6. 等待 kube-vip Pod 启动并验证
# ──────────────────────────────────────────────
echo ">>> 等待 kube-vip Pod 启动（static Pod 由 kubelet 自动拉起）..."
for i in $(seq 1 30); do
    PODS=$(kubectl --kubeconfig "$KUBECONFIG" get pods -n kube-system -l name=kube-vip --no-headers 2>/dev/null || true)
    if [ -n "$PODS" ]; then
        break
    fi
    sleep 2
    echo "    等待中... (${i}/30)"
done

echo ""
echo ">>> kube-vip Pod 状态:"
kubectl --kubeconfig "$KUBECONFIG" get pods -n kube-system -l name=kube-vip -o wide 2>/dev/null || \
    kubectl --kubeconfig "$KUBECONFIG" get pods -n kube-system -o wide | grep kube-vip || true

# ──────────────────────────────────────────────
# 7. 验证 VIP ARP 生效
# ──────────────────────────────────────────────
echo ""
echo ">>> 验证 VIP ARP 生效..."
sleep 3

# 尝试 ping VIP
if ping -c 3 -W 2 "$VIP" &>/dev/null; then
    echo "    ✓ VIP ${VIP} 可达 (ping)"
else
    echo "    ⚠ VIP ${VIP} 暂不可达，ARP 可能尚未广播完成"
    echo "      可稍后手动验证: ping ${VIP}"
fi

# 尝试通过 VIP 访问 API Server
if [ "$(command -v arping 2>/dev/null)" ]; then
    echo "    ARP 邻居:"
    ip neigh show | grep "$VIP" || true
fi

# ──────────────────────────────────────────────
# 8. 验证通过 VIP 可访问集群后再更新 kubeconfig
# ──────────────────────────────────────────────
echo ""
echo ">>> 验证通过 VIP 访问 API Server..."
if kubectl --server="https://${VIP}:6443" --insecure-skip-tls-verify=true get nodes &>/dev/null; then
    echo "    ✓ 通过 VIP 可以访问 API Server"

    read -rp "    是否更新 kubeconfig 指向 VIP? [y/N] " UPDATE_KUBECONFIG
    if [[ "$UPDATE_KUBECONFIG" =~ ^[Yy]$ ]]; then
        kubectl --kubeconfig "$KUBECONFIG" config set-cluster kubernetes --server="https://${VIP}:6443"
        echo "    ✓ kubeconfig 已更新: https://${VIP}:6443"
    else
        echo "    跳过 kubeconfig 更新"
        echo "    手动更新命令: kubectl config set-cluster kubernetes --server=https://${VIP}:6443"
    fi
else
    echo "    ⚠ 通过 VIP 无法访问 API Server"
    echo "      可能原因："
    echo "      1. VIP 尚未完成 ARP 广播，等待 30 秒后重试"
    echo "      2. kube-vip Pod 未正常启动，检查: kubectl get pods -n kube-system | grep kube-vip"
    echo "      3. 网络接口名不匹配，确认所有节点使用 ${INTERFACE}"
    echo ""
    echo "    手动验证命令:"
    echo "      ping ${VIP}"
    echo "      kubectl --server=https://${VIP}:6443 --insecure-skip-tls-verify=true get nodes"
    echo ""
    echo "    kubeconfig 暂不更新，请验证 VIP 可达后手动执行:"
    echo "      kubectl config set-cluster kubernetes --server=https://${VIP}:6443"
fi

# 清理临时文件
rm -f "$GENERATED_MANIFEST"

echo ""
echo ">>> kube-vip 部署完成"
echo "    VIP: ${VIP}"
echo "    模式: static Pod（每个控制平面节点一个）"
echo "    验证: kubectl get pods -n kube-system -l name=kube-vip -o wide"
