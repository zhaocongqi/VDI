---
name: kubeovn-deploy
description: 部署 Kube-OVN CNI 插件到 K8s 集群。当用户提到"部署 kube-ovn"、"安装 kube-ovn"、"CNI 部署"、"网络插件"、"OVN 网络"时触发。支持 OVN Central raft HA 模式、自定义 Pod/Service 网段。
---

# Kube-OVN CNI 部署

为 Kubernetes 集群部署 Kube-OVN CNI 插件，提供 Pod 网络。

## 前置条件

- K8s 集群已部署（节点处于 NotReady 状态）
- kubeconfig 可用（`~/.kube/config`）
- **kube-vip 已部署（推荐）** — 确保 API Server VIP 稳定

## 执行流程

### Step 0: 环境检查

```bash
# 加载共享配置
source deploy/env-config.sh

# 检查 helm
if ! command -v helm &>/dev/null; then
  echo "安装 helm..."
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# 检查集群状态
echo "集群状态:"
kubectl get nodes -o wide
echo ""
echo "CoreDNS 状态:"
kubectl get pods -n kube-system -l k8s-app=kube-dns

# 验证 Service CIDR 一致性
echo ""
echo "网段配置:"
echo "  K8s Service CIDR: ${SVC_CIDR}（来自 env-config.sh）"
echo "  Kube-OVN values:  $(grep SVC_CIDR deploy/kube-ovn/chart/values.yaml | head -1)"
```

**预期状态**：
- 节点：NotReady（正常，等待 CNI）
- CoreDNS：Pending（正常，等待 CNI）

> ⚠️ **网段冲突检查**：确认 Pod CIDR（默认 `10.16.0.0/16`）和 Join CIDR（默认 `100.64.0.0/16`）不与节点物理网络重叠。如有冲突需修改 `deploy/kube-ovn/chart/values.yaml` 中的 `ipv4.POD_CIDR` 和 `ipv4.JOIN_CIDR`。

### Step 1: 确认集群状态

```bash
# 确认节点处于 NotReady 状态（正常，等待 CNI）
kubectl get nodes -o wide

# 确认 CoreDNS 处于 Pending 状态（正常，等待 CNI）
kubectl get pods -n kube-system -l k8s-app=kube-dns
```

### Step 2: 部署 Kube-OVN

```bash
bash deploy/kube-ovn/deploy.sh
```

部署脚本会：
1. 给 master 节点打 `kube-ovn/role=master` 标签
2. 使用本地 Helm chart + values.yaml 安装 Kube-OVN
3. 等待所有组件就绪（约 3-5 分钟）

### Step 3: 验证部署

```bash
# 1. 检查节点状态（应变为 Ready）
kubectl get nodes -o wide

# 2. 检查 Kube-OVN 组件
kubectl get pods -n kube-system -l app=ovn-central
kubectl get pods -n kube-system -l app=ovs-ovn
kubectl get pods -n kube-system -l app=kube-ovn-controller
kubectl get pods -n kube-system -l app=kube-ovn-cni

# 3. 检查 CoreDNS（应变为 Running）
kubectl get pods -n kube-system -l k8s-app=kube-dns

# 4. 检查 OVN Central 状态
kubectl exec -n kube-system -c ovn-central ovn-central-0 -- ovn-nbctl show
```

## 技术细节

### Kube-OVN 架构

- **OVN Central**：控制平面，3 节点 raft HA 模式
- **OVN Controller**：数据平面，每个节点一个 DaemonSet
- **kube-ovn-controller**：K8s 控制器，处理 CRD 和 IP 分配
- **kube-ovn-cni**：CNI 插件，负责 Pod 网络配置

### 网段配置（与 env-config.sh 统一管理）

| 配置项 | 值 | 配置来源 |
|--------|-----|---------|
| Pod CIDR | 10.16.0.0/16 | `deploy/kube-ovn/chart/values.yaml` + `env-config.sh` |
| Service CIDR | 10.96.0.0/12 | `values.yaml` + KubeKey 默认值（须一致） |
| Join CIDR | 100.64.0.0/16 | `values.yaml` + `env-config.sh` |

> ⚠️ Service CIDR 在 KubeKey config.yaml（隐式 K8s 默认值）和 Kube-OVN values.yaml 两处配置。修改时**必须同步更新两处**。建议通过 `deploy/env-config.sh` 统一管理。

### 离线部署

Kube-OVN 的 Helm chart 已本地存在于 `deploy/kube-ovn/chart/`，无需下载。但容器镜像仍需从 `docker.io/kubeovn` 拉取，离线环境需提前导入镜像。

## 部署文件说明

| 文件 | 说明 |
|------|------|
| `deploy/kube-ovn/deploy.sh` | 部署脚本 |
| `deploy/kube-ovn/values.yaml` | Helm values 配置 |
| `deploy/kube-ovn/chart/` | 本地 Helm chart（v1.17.0） |
| `deploy/env-config.sh` | 共享网段配置 |

## 常见问题

### 1. 节点一直处于 NotReady 状态

**原因**：OVN Central 未就绪或 CNI 配置错误。

**解决**：
```bash
kubectl logs -n kube-system -l app=ovn-central
kubectl logs -n kube-system -l app=kube-ovn-controller
```

### 2. Pod 无法获取 IP

**原因**：IP 地址池耗尽或子网配置错误。

**解决**：
```bash
kubectl get subnet
kubectl get ip
```

### 3. Pod 之间无法通信

**原因**：网络策略或路由配置错误。

**解决**：
```bash
kubectl get networkpolicy
kubectl exec -n kube-system -c ovn-central ovn-central-0 -- ovn-nbctl lr-route-list
```

### 4. Service CIDR 不一致导致 DNS 异常

**原因**：kubekey config.yaml 的 Service CIDR 与 Kube-OVN values.yaml 不一致。

**解决**：
```bash
# 检查 K8s apiserver 的 service-cluster-ip-range
ps aux | grep kube-apiserver | grep service-cluster-ip-range
# 与 Kube-OVN values.yaml 中的 SVC_CIDR 比对
grep SVC_CIDR deploy/kube-ovn/chart/values.yaml
```

## 后续步骤

Kube-OVN 部署完成后，继续部署存储（如 Longhorn）和计算（如 KubeVirt）组件。
