#!/bin/bash
set -euo pipefail

# KubeKey 部署 K8s 集群
# 被 TUI installer 的 DeployEngine 调用（step_id: kubekey-deploy-k8s）

LOG_TAG="[kk-deploy]"

echo "$LOG_TAG 开始部署 K8s 集群..."

# 加载环境配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${DEPLOY_DIR}/env-config.sh" 2>/dev/null || true

# 确保 kk 可用
KK="${OFFLINE_BINARIES:-}/kk"
if [ ! -x "$KK" ]; then
    KK="$(command -v kk 2>/dev/null || echo /usr/local/bin/kk)"
fi

if [ ! -x "$KK" ]; then
    echo "$LOG_TAG kk 未找到，尝试下载..."
    bash "${SCRIPT_DIR}/download-kk.sh" "${KUBEKEY_VERSION:-v4.0.4}" 2>/dev/null || true
    KK="$(command -v kk 2>/dev/null || echo /usr/local/bin/kk)"
fi

if [ ! -x "$KK" ]; then
    echo "$LOG_TAG 错误: kk 不可用"
    exit 1
fi

echo "$LOG_TAG 使用 kk: $KK"
"$KK" version

# 生成 inventory 配置（如果不存在）
INVENTORY="${DEPLOY_DIR}/k8s/inventory.yaml"
if [ ! -f "$INVENTORY" ]; then
    echo "$LOG_TAG inventory.yaml 不存在，使用本地单节点模式"
    INVENTORY=""
fi

# 执行集群创建
echo "$LOG_TAG 创建 K8s 集群..."
if [ -n "$INVENTORY" ]; then
    "$KK" create cluster -f "$INVENTORY" --skip-check-os 2>&1 || {
        echo "$LOG_TAG 集群创建失败"
        exit 1
    }
else
    # 单节点本地部署
    "$KK" create cluster --skip-check-os 2>&1 || {
        echo "$LOG_TAG 集群创建失败"
        exit 1
    }
fi

# 验证集群状态
echo "$LOG_TAG 验证集群状态..."
export KUBECONFIG=/etc/kubernetes/admin.conf
for i in $(seq 1 30); do
    if kubectl get nodes 2>/dev/null | grep -q " Ready"; then
        echo "$LOG_TAG K8s 集群就绪 ✓"
        kubectl get nodes
        exit 0
    fi
    echo "$LOG_TAG 等待节点就绪... ($i/30)"
    sleep 10
done

echo "$LOG_TAG 警告: 节点未在 5 分钟内就绪，但集群创建已执行"
exit 0
