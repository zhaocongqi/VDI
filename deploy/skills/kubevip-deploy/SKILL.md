---
name: kubevip-deploy
description: 部署 kube-vip 提供 Kubernetes API Server VIP。当用户提到"部署 kube-vip"、"安装 kube-vip"、"API Server VIP"、"kubevip"、"集群高可用"时触发。支持 ARP 模式、自定义 VIP 和网络接口。
---

# kube-vip 部署（API Server VIP）

为 Kubernetes 集群部署 kube-vip，提供 API Server 的虚拟 IP（VIP），使集群可通过统一入口访问。

## 前置条件

- K8s 集群已部署（节点可处于 NotReady 状态）
- kubeconfig 可用（`~/.kube/config`）
- 节点间网络互通

## 执行流程

### Step 0: 环境检查

检查 kubectl 和集群连通性：

```bash
# 检查 kubectl
if ! command -v kubectl &>/dev/null; then
  echo "错误: kubectl 未安装" >&2
  exit 1
fi

# 检查集群连通性
if ! kubectl get nodes &>/dev/null; then
  echo "错误: 无法连接集群，请检查 KUBECONFIG" >&2
  exit 1
fi

echo "集群状态:"
kubectl get nodes -o wide
```

### Step 1: 收集配置信息

向用户收集以下信息：

1. **VIP 地址**：虚拟 IP 地址（如 `192.168.220.100`）
2. **网络接口**：节点的网络接口名（如 `ens160`，可通过 `ip addr` 查看）

### Step 2: 部署 kube-vip

```bash
bash deploy/kube-vip/deploy-kube-vip.sh <VIP> <INTERFACE>
# 示例: bash deploy/kube-vip/deploy-kube-vip.sh 192.168.220.100 ens160
```

部署脚本会：
1. 生成 kube-vip static Pod manifest
2. 将 manifest 复制到每个控制平面节点的 `/etc/kubernetes/manifests/`
3. 等待 kube-vip Pod 启动

### Step 3: 验证部署

```bash
# 1. 检查 kube-vip Pod 状态
kubectl get pods -n kube-system -l name=kube-vip

# 2. 检查 VIP 是否生效
ping <VIP>

# 3. 通过 VIP 访问集群
kubectl --server=https://<VIP>:6443 get nodes
```

## 技术细节

### kube-vip 工作原理

- kube-vip 以 static Pod 形式运行在每个控制平面节点
- 使用 ARP 模式广播 VIP 地址
- 当主节点故障时，其他节点自动接管 VIP

### 关键配置

- `kubernetes_addr=lb.kubesphere.local:6443`：覆盖默认的 `kubernetes:<port>` 地址
- `lb.kubesphere.local` 由 KubeKey 部署时自动写入每个节点的 `/etc/hosts`
- 无需 `hostAliases` 或手动修改 `/etc/hosts`

## 部署文件说明

| 文件 | 说明 |
|------|------|
| `deploy/kube-vip/deploy-kube-vip.sh` | 部署脚本 |
| `deploy/kube-vip/kube-vip.yaml` | kube-vip static Pod manifest 模板 |

## 常见问题

### 1. kube-vip Pod 未启动

**原因**：manifest 路径错误或 kubeconfig 不可用。

**解决**：
```bash
# 检查 manifest 是否存在
ls -la /etc/kubernetes/manifests/kube-vip.yaml

# 检查 kubelet 日志
journalctl -u kubelet -f
```

### 2. VIP 无法访问

**原因**：网络接口配置错误或 ARP 被禁用。

**解决**：
```bash
# 检查网络接口
ip addr show <INTERFACE>

# 检查 ARP 配置
cat /proc/sys/net/ipv4/conf/*/arp_ignore
```

## 后续步骤

kube-vip 部署完成后，继续部署 CNI（如 Kube-OVN）使节点变为 Ready 状态。
