#!/usr/bin/env bash
# Longhorn 分布式存储部署脚本
# 用法: bash deploy/longhorn/deploy.sh
#
# 前置条件:
#   - K8s 集群已就绪（节点 Ready）
#   - open-iscsi 已安装（sudo apt-get install -y open-iscsi）
#   - helm 命令可用
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== Longhorn 分布式存储部署 ==="

# 加载共享配置
if [ -f "${PROJECT_DIR}/deploy/env-config.sh" ]; then
  source "${PROJECT_DIR}/deploy/env-config.sh"
fi

# 1. 检查前置依赖
echo "[1/4] 检查前置依赖..."
if ! systemctl is-active --quiet iscsid 2>/dev/null; then
  echo "警告: iscsid 未运行，尝试安装 open-iscsi..."
  sudo apt-get install -y open-iscsi
  sudo systemctl enable --now iscsid
fi

# 2. 确定 Helm Chart 来源（离线优先）
VALUES_FILE="${SCRIPT_DIR}/values.yaml"

if [ -n "${OFFLINE_CHARTS:-}" ] && [ -d "${OFFLINE_CHARTS}/longhorn" ]; then
  # 离线模式：使用本地 chart 目录
  CHART_REF="${OFFLINE_CHARTS}/longhorn"
  echo "[2/4] [离线] 使用本地 Helm chart: ${CHART_REF}"
else
  # 在线模式：添加远程 Helm 仓库
  echo "[2/4] 添加 Longhorn Helm 仓库..."
  helm repo add longhorn https://charts.longhorn.io 2>/dev/null || true
  helm repo update
  CHART_REF="longhorn/longhorn"
fi

# 3. 部署 Longhorn（使用自定义 values）
echo "[3/4] 执行 helm install..."
HELM_ARGS=(-n longhorn-system --create-namespace --wait --timeout 10m)
if [ -f "$VALUES_FILE" ]; then
  echo "    使用自定义 values: ${VALUES_FILE}"
  HELM_ARGS+=(-f "$VALUES_FILE")
fi
helm install longhorn "$CHART_REF" "${HELM_ARGS[@]}"

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
kubectl get nodes.longhorn.io -n longhorn-system 2>/dev/null || true
echo ""
echo "=== 部署完成 ==="
