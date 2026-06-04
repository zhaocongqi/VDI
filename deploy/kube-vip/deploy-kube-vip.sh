#!/usr/bin/env bash
set -euo pipefail

# kube-vip 部署脚本
# 用法: bash deploy-kube-vip.sh [VIP] [INTERFACE]
# 示例: bash deploy-kube-vip.sh 192.168.220.100 ens160

VIP="${1:-192.168.220.100}"
INTERFACE="${2:-ens160}"
MANIFEST="$(dirname "$0")/manifests/kube-vip.yaml"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

echo ">>> 部署 kube-vip"
echo "    VIP: ${VIP}"
echo "    接口: ${INTERFACE}"

# 检查 kubectl 可用
if ! command -v kubectl &>/dev/null; then
    echo "错误: kubectl 未安装" >&2
    exit 1
fi

# 检查集群可达
if ! kubectl --kubeconfig "$KUBECONFIG" get nodes &>/dev/null; then
    echo "错误: 无法连接集群，请检查 KUBECONFIG" >&2
    exit 1
fi

# 自动检测网络接口（如果未指定或为 auto）
if [ "$INTERFACE" = "auto" ]; then
    INTERFACE=$(kubectl --kubeconfig "$KUBECONFIG" debug node/"$(kubectl --kubeconfig "$KUBECONFIG" get nodes -o jsonpath='{.items[0].metadata.name}')" -it --image=busybox -- ip -o addr show 2>/dev/null | grep "$(kubectl --kubeconfig "$KUBECONFIG" get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')" | awk '{print $2}')
    echo "    自动检测接口: ${INTERFACE}"
fi

# 替换 manifest 中的 VIP 和接口
sed -e "s|value: ens160|value: ${INTERFACE}|g" \
    -e "s|value: 192.168.220.100|value: ${VIP}|g" \
    "$MANIFEST" | kubectl --kubeconfig "$KUBECONFIG" apply -f -

echo ">>> 等待 kube-vip 启动..."
sleep 10

# 验证
STATUS=$(kubectl --kubeconfig "$KUBECONFIG" get pod -n kube-system kube-vip -o jsonpath='{.status.phase}' 2>/dev/null || echo "NotFound")
if [ "$STATUS" = "Running" ]; then
    echo ">>> kube-vip 部署成功！"
    echo "    VIP ${VIP} 已激活"
    echo ""
    echo ">>> 更新 kubeconfig 指向 VIP..."
    kubectl --kubeconfig "$KUBECONFIG" config set-cluster kubernetes --server="https://${VIP}:6443"
    echo "    kubeconfig 已更新: https://${VIP}:6443"
else
    echo ">>> kube-vip 状态异常: ${STATUS}" >&2
    echo "    查看日志: kubectl logs -n kube-system kube-vip" >&2
    exit 1
fi
