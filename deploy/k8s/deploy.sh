#!/bin/bash
set -euo pipefail

# KubeKey 部署 K8s 集群
# 被 TUI installer 的 DeployEngine 调用（step_id: kubekey-deploy-k8s）

LOG_TAG="[kk-deploy]"

echo "$LOG_TAG 开始部署 K8s 集群..."

# 加载环境配置（DeployEngine 已 source /etc/vdi/env-config.sh，此处兜底）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${DEPLOY_DIR}/env-config.sh" 2>/dev/null || true

# 确保 kk 可用（离线 bundle 优先）
KK=""
for _kk in "${OFFLINE_BINARIES:-}/kk" "/cdrom/bundle/binaries/kk" "$(command -v kk 2>/dev/null)" "/usr/local/bin/kk"; do
    if [ -n "$_kk" ] && [ -x "$_kk" ]; then
        KK="$_kk"
        break
    fi
done

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

# 定位 KubeKey 配置文件（TUI 生成的 config.yaml 优先）
CONFIG_FILE=""
for _cfg in "${VDI_CONFIG_DIR:-}/config.yaml" "${DEPLOY_DIR}/k8s/config.yaml" "/etc/vdi/config.yaml"; do
    if [ -f "$_cfg" ]; then
        CONFIG_FILE="$_cfg"
        break
    fi
done

if [ -z "$CONFIG_FILE" ]; then
    echo "$LOG_TAG 错误: KubeKey config.yaml 未找到（TUI 应生成到 /etc/vdi/config.yaml）"
    exit 1
fi

echo "$LOG_TAG 使用配置: $CONFIG_FILE"
cat "$CONFIG_FILE"

# 执行集群创建
echo "$LOG_TAG 创建 K8s 集群..."
"$KK" create cluster -f "$CONFIG_FILE" --skip-check-os 2>&1 || {
    echo "$LOG_TAG 集群创建失败"
    exit 1
}

# 验证集群状态
echo "$LOG_TAG 验证集群状态..."
export KUBECONFIG=/etc/kubernetes/admin.conf
for i in $(seq 1 30); do
    if kubectl get nodes 2>/dev/null | grep -q " Ready"; then
        echo "$LOG_TAG K8s 集群就绪"
        kubectl get nodes
        exit 0
    fi
    echo "$LOG_TAG 等待节点就绪... ($i/30)"
    sleep 10
done

echo "$LOG_TAG 警告: 节点未在 5 分钟内就绪，但集群创建已执行"
exit 0
