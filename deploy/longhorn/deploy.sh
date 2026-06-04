#!/usr/bin/env bash
# Longhorn 分布式存储部署脚本
# 用法: bash deploy/longhorn/deploy.sh
#
# 前置条件:
#   - K8s 集群已就绪（节点 Ready）
#   - open-iscsi 已安装（sudo apt-get install -y open-iscsi）
#   - helm 命令可用
set -euo pipefail

echo "=== Longhorn 分布式存储部署 ==="

# 1. 检查前置依赖
echo "[1/4] 检查前置依赖..."
if ! systemctl is-active --quiet iscsid 2>/dev/null; then
  echo "警告: iscsid 未运行，尝试安装 open-iscsi..."
  sudo apt-get install -y open-iscsi
  sudo systemctl enable --now iscsid
fi

# 2. 添加 Helm 仓库
echo "[2/4] 添加 Longhorn Helm 仓库..."
helm repo add longhorn https://charts.longhorn.io 2>/dev/null || true
helm repo update

# 3. 部署 Longhorn
echo "[3/4] 执行 helm install..."
helm install longhorn longhorn/longhorn \
  -n longhorn-system \
  --create-namespace \
  --wait \
  --timeout 10m

# 4. 验证
echo "[4/4] 验证部署状态..."
echo ""
echo "--- StorageClass ---"
kubectl get sc
echo ""
echo "--- Longhorn Pods ---"
kubectl get pods -n longhorn-system -o wide
echo ""
echo "--- 节点状态 ---"
kubectl get nodes -o wide
echo ""
echo "=== 部署完成 ==="
