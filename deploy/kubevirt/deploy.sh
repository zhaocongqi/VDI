#!/usr/bin/env bash
# KubeVirt 部署脚本
# 用法: bash deploy/kubevirt/deploy.sh [版本]
# 示例: bash deploy/kubevirt/deploy.sh v1.5.0
set -euo pipefail

VERSION="${1:-v1.5.0}"
NAMESPACE="kubevirt"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== KubeVirt 部署 ==="
echo "版本: ${VERSION}"

# 加载共享配置
if [ -f "${PROJECT_DIR}/deploy/env-config.sh" ]; then
  source "${PROJECT_DIR}/deploy/env-config.sh"
fi

# 1. 检查 KVM 支持（通过 kubectl 检查所有节点）
echo "[1/5] 检查 KVM 支持（所有节点）..."
KVM_OK=true

# 优先使用 Ansible 检查所有节点
if command -v ansible &>/dev/null && [ -f "${ANSIBLE_HOSTS_FILE:-deploy/hosts}" ]; then
  echo "    使用 Ansible 检查所有节点..."
  KVM_CHECK=$(ansible -i "${ANSIBLE_HOSTS_FILE:-deploy/hosts}" all -m shell -a \
    "if [ -e /dev/kvm ]; then echo 'KVM: OK'; else echo 'KVM: MISSING'; fi" \
    -u "${ANSIBLE_USER:-zcq}" --become 2>/dev/null || true)

  if echo "$KVM_CHECK" | grep -q "MISSING"; then
    echo "错误: 以下节点不支持 KVM:" >&2
    echo "$KVM_CHECK" | grep "MISSING" >&2
    KVM_OK=false
  else
    echo "    所有节点 KVM 支持: OK"
  fi
else
  # 回退到本地检查 + kubectl
  echo "    Ansible 不可用，使用 kubectl 检查..."
  NODES=$(kubectl get nodes -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
  if [ -n "$NODES" ]; then
    for node in $NODES; do
      KVM_AVAIL=$(kubectl get node "$node" -o jsonpath='{.status.allocatable.devices\.kubevirt\.io/kvm}' 2>/dev/null || echo "")
      if [ -z "$KVM_AVAIL" ]; then
        # 设备插件尚未注册，通过 debug pod 检查
        echo "    节点 ${node}: KVM 设备未注册（KubeVirt 安装后会自动检测）"
      else
        echo "    节点 ${node}: KVM 可用 (${KVM_AVAIL})"
      fi
    done
  else
    # 最终回退：仅检查本地
    if [ ! -e /dev/kvm ]; then
      echo "警告: 本地 /dev/kvm 不存在" >&2
      echo "  如果节点支持 KVM 但未加载模块，请执行:" >&2
      echo "  sudo modprobe kvm_intel  # Intel CPU" >&2
      echo "  sudo modprobe kvm_amd    # AMD CPU" >&2
    else
      echo "    本地 KVM 支持: OK"
    fi
  fi
fi

# 修复 /dev/kvm 权限（使用 kvm 组而非 666）
if [ -e /dev/kvm ]; then
  KVM_PERM=$(stat -c "%a" /dev/kvm 2>/dev/null || echo "660")
  if [ "$KVM_PERM" = "666" ]; then
    echo "    修复 /dev/kvm 权限: 666 -> 660 (kvm 组)"
    sudo groupadd --system kvm 2>/dev/null || true
    sudo chmod 660 /dev/kvm
    sudo chown root:kvm /dev/kvm
  fi
fi

# 2. 创建命名空间
echo "[2/5] 创建命名空间 ${NAMESPACE}..."
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# 3. 部署 KubeVirt Operator
echo "[3/5] 部署 KubeVirt Operator..."
if [ -n "${OFFLINE_MANIFESTS:-}" ] && [ -f "${OFFLINE_MANIFESTS}/kubevirt-operator.yaml" ]; then
  echo "    [离线] 使用本地 manifest"
  kubectl apply -f "${OFFLINE_MANIFESTS}/kubevirt-operator.yaml"
else
  kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-operator.yaml"
fi

# 4. 等待 Operator 就绪
echo "[4/5] 等待 Operator 就绪..."
kubectl wait --for=condition=Available deployment/virt-operator -n ${NAMESPACE} --timeout=300s

# 5. 部署 KubeVirt CR
echo "[5/5] 部署 KubeVirt CR..."
if [ -n "${OFFLINE_MANIFESTS:-}" ] && [ -f "${OFFLINE_MANIFESTS}/kubevirt-cr.yaml" ]; then
  echo "    [离线] 使用本地 manifest"
  kubectl apply -f "${OFFLINE_MANIFESTS}/kubevirt-cr.yaml"
else
  kubectl apply -f "https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/kubevirt-cr.yaml"
fi

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
