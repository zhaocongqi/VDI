#!/usr/bin/env bash
# KubeVirt 部署脚本
# 用法: bash deploy/kubevirt/deploy.sh [版本]
# 示例: bash deploy/kubevirt/deploy.sh v1.5.0
set -euo pipefail

VERSION="${1:-v1.5.0}"
NAMESPACE="kubevirt"

echo "=== KubeVirt 部署 ==="
echo "版本: ${VERSION}"

# 1. 检查 KVM 支持
echo "[1/5] 检查 KVM 支持..."
if [ ! -e /dev/kvm ]; then
    echo "错误: /dev/kvm 不存在，节点不支持 KVM" >&2
    exit 1
fi
echo "KVM 支持: OK"

# 2. 创建命名空间
echo "[2/5] 创建命名空间 ${NAMESPACE}..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# 3. 部署 KubeVirt Operator
echo "[3/5] 部署 KubeVirt Operator..."
kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-operator.yaml"

# 4. 等待 Operator 就绪
echo "[4/5] 等待 Operator 就绪..."
kubectl wait --for=condition=Available deployment/virt-operator -n ${NAMESPACE} --timeout=300s

# 5. 部署 KubeVirt CR
echo "[5/5] 部署 KubeVirt CR..."
kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-cr.yaml"

echo ""
echo "=== 等待 KubeVirt 组件就绪 ==="
kubectl wait --for=condition=Available deployment/virt-api -n ${NAMESPACE} --timeout=300s
kubectl wait --for=condition=Available deployment/virt-controller -n ${NAMESPACE} --timeout=300s

echo ""
echo "=== 验证部署状态 ==="
echo "--- KubeVirt 组件 ---"
kubectl get pods -n ${NAMESPACE}
echo ""
echo "--- KubeVirt 版本 ---"
kubectl get kubevirt.kubevirt.io -n ${NAMESPACE} -o jsonpath='{.items[0].status.observedKubeVirtVersion}' 2>/dev/null || echo "版本信息暂不可用"
echo ""
echo "--- 节点状态 ---"
kubectl get nodes -o wide
echo ""
echo "=== 部署完成 ==="
