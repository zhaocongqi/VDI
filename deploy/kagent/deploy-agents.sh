#!/usr/bin/env bash
# VDI 专用 Agent 批量部署脚本
# 用法: bash deploy/kagent/deploy-agents.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_DIR="${SCRIPT_DIR}/agents"
NAMESPACE="${KAGENT_NAMESPACE:-kagent}"

echo "=== VDI Agent 部署 ==="
echo "命名空间: ${NAMESPACE}"
echo "Agent 目录: ${AGENTS_DIR}"

# 检查 kagent CRD 是否存在
if ! kubectl get crd agents.kagent.dev &>/dev/null; then
  echo "错误: kagent CRD 未安装，请先执行 kagent-deploy skill" >&2
  exit 1
fi

# 检查命名空间
if ! kubectl get ns "${NAMESPACE}" &>/dev/null; then
  echo "错误: 命名空间 ${NAMESPACE} 不存在" >&2
  exit 1
fi

# 部署所有 Agent CRD
echo ""
echo "--- 部署 Agent ---"
for agent_file in "${AGENTS_DIR}"/*.yaml; do
  if [ ! -f "$agent_file" ]; then
    echo "警告: 未找到 Agent 文件" >&2
    continue
  fi

  agent_name=$(grep -E "^\s*name:" "$agent_file" | head -1 | awk '{print $2}' | tr -d '"')
  echo "  部署 Agent: ${agent_name}"
  kubectl apply -f "$agent_file"
done

# 验证
echo ""
echo "--- 验证 Agent 状态 ---"
kubectl get agents -n "${NAMESPACE}" -o wide

echo ""
echo "--- Agent 详情 ---"
for agent_file in "${AGENTS_DIR}"/*.yaml; do
  agent_name=$(grep -E "^\s*name:" "$agent_file" | head -1 | awk '{print $2}' | tr -d '"')
  echo ""
  echo "Agent: ${agent_name}"
  kubectl get agent "${agent_name}" -n "${NAMESPACE}" -o jsonpath='{.status.conditions[*].message}' 2>/dev/null || echo "  状态: 创建中..."
done

echo ""
echo "=== 部署完成 ==="
echo "使用 'kubectl get agents -n ${NAMESPACE}' 查看 Agent 状态"
echo "使用 'kubectl port-forward -n ${NAMESPACE} svc/kagent-ui 3000:8080' 访问 UI"
