#!/usr/bin/env bash
# Kube-OVN CNI 部署脚本
# 用法: bash deploy/kube-ovn/deploy.sh
#
# 前置条件:
#   - K8s 集群已就绪（节点 NotReady 状态，等待 CNI）
#   - helm 命令可用
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 离线优先：使用 OFFLINE_CHARTS 中的 chart，否则使用本地 chart 目录
if [ -n "${OFFLINE_CHARTS:-}" ] && [ -d "${OFFLINE_CHARTS}/kube-ovn" ]; then
  CHART_DIR="${OFFLINE_CHARTS}/kube-ovn"
  echo "[离线] 使用本地 Helm chart: ${CHART_DIR}"
else
  CHART_DIR="${SCRIPT_DIR}/chart"
fi
VALUES_FILE="${SCRIPT_DIR}/values.yaml"

echo "=== Kube-OVN CNI 部署 ==="

# 1. 标记 master 节点
echo "[1/3] 标记 master 节点..."
kubectl label node --overwrite \
  -l node-role.kubernetes.io/control-plane \
  kube-ovn/role=master

# 2. 部署 Kube-OVN
echo "[2/3] 执行 helm install..."
helm install kubeovn "${CHART_DIR}" \
  --wait \
  --timeout 10m \
  -f "${VALUES_FILE}"

# 3. 验证
echo "[3/3] 验证部署状态..."
echo ""
echo "--- OVN Central ---"
kubectl get pod -n kube-system -l app=ovn-central -o wide
echo ""
echo "--- OVS ---"
kubectl get pod -n kube-system -l app=ovs -o wide
echo ""
echo "--- kube-ovn-controller ---"
kubectl get pod -n kube-system -l app=kube-ovn-controller -o wide
echo ""
echo "--- kube-ovn-cni ---"
kubectl get pod -n kube-system -l app=kube-ovn-cni -o wide
echo ""
echo "--- 节点状态 ---"
kubectl get nodes -o wide
echo ""
echo "=== 部署完成 ==="
