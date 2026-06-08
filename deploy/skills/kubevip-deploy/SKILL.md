---
name: kubevip-deploy
description: 部署 kube-vip 提供 Kubernetes API Server VIP。当用户提到"部署 kube-vip"、"安装 kube-vip"、"API Server VIP"、"kubevip"、"集群高可用"时触发。支持 ARP 模式 static Pod 多节点 HA、自定义 VIP 和网络接口。
---

# kube-vip 部署（API Server VIP）

为 Kubernetes 集群部署 kube-vip，提供 API Server 的虚拟 IP（VIP），使集群可通过统一入口访问。

## 前置条件

- K8s 集群已部署（节点可处于 NotReady 状态）
- kubeconfig 可用（`~/.kube/config`）
- 节点间网络互通
- 所有控制平面节点的 `/etc/kubernetes/admin.conf` 可访问
- SSH 可达所有控制平面节点（用于分发 static Pod manifest）

## 执行流程

### Step 0: 环境检查

检查 kubectl、集群连通性，以及控制平面节点 SSH 可达性：

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

# 列出控制平面节点
echo "控制平面节点:"
kubectl get nodes -l node-role.kubernetes.io/control-plane -o wide

# 检查 SSH 可达性
ANSIBLE_USER="${ANSIBLE_USER:-zcq}"
for ip in $(kubectl get nodes -l node-role.kubernetes.io/control-plane -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'); do
  if ssh -o ConnectTimeout=3 "${ANSIBLE_USER}@${ip}" echo "OK" &>/dev/null; then
    echo "  ${ip}: SSH 可达"
  else
    echo "  ${ip}: SSH 不可达（需配置免密登录）"
  fi
done
```

### Step 1: 收集配置信息

向用户收集以下信息：

1. **VIP 地址**：虚拟 IP 地址（如 `192.168.220.100`），必须与节点在同一网段且未被占用
2. **网络接口**：节点网卡名（如 `ens160`），所有节点应使用相同接口名。可通过 `ip -json route list default` 查看，也可传 `auto` 自动检测

**注意事项**：
- VIP 不能与任何节点 IP 冲突
- 所有控制平面节点的网络接口名应一致
- 如果接口名不一致，需要分别在各节点手动部署

### Step 2: 部署 kube-vip

```bash
bash deploy/kube-vip/deploy-kube-vip.sh <VIP> <INTERFACE>
# 示例: bash deploy/kube-vip/deploy-kube-vip.sh 192.168.220.100 ens160
# 自动检测接口: bash deploy/kube-vip/deploy-kube-vip.sh 192.168.220.100 auto
```

部署脚本会：
1. 检查 kubectl 和集群连通性
2. 自动检测网络接口（如果指定 `auto`）
3. 生成 kube-vip static Pod manifest（替换 VIP 和接口参数）
4. **通过 SSH 将 manifest 分发到每个控制平面节点的 `/etc/kubernetes/manifests/`**
5. 等待 kubelet 自动拉起 static Pod
6. 验证 VIP ARP 广播生效
7. 验证通过 VIP 可访问 API Server 后再更新 kubeconfig

### Step 3: 验证部署

```bash
# 1. 检查 kube-vip Pod 状态（应为每个控制平面节点一个 Pod）
kubectl get pods -n kube-system -l name=kube-vip -o wide

# 2. 检查 VIP 可达性
ping <VIP>

# 3. 通过 VIP 访问集群
kubectl --server=https://<VIP>:6443 --insecure-skip-tls-verify=true get nodes

# 4. 检查 ARP 邻居表
ip neigh show | grep <VIP>
```

### Step 4: 验证 HA 故障切换（可选）

```bash
# 查看当前持有 VIP 的节点
ip neigh show | grep <VIP>

# 停止该节点的 kubelet（模拟故障）
# 注意：这会导致该节点上所有 Pod 停止，仅用于测试
ssh <user>@<node> sudo systemctl stop kubelet

# 等待 10-30 秒，验证 VIP 是否漂移到其他节点
ping <VIP>
kubectl get nodes

# 恢复节点
ssh <user>@<node> sudo systemctl start kubelet
```

## 技术细节

### kube-vip HA 工作原理

- kube-vip 以 **static Pod** 形式运行在**每个**控制平面节点
- manifest 放置于 `/etc/kubernetes/manifests/`，由 kubelet 自动拉起和管理
- 使用 ARP 模式广播 VIP 地址
- 仅有一个节点持有 VIP（leader election），其他节点 standby
- 当主节点故障时，其他节点自动通过 ARP 抢占 VIP

### 为什么不能用 kubectl apply

`kubectl apply` 只创建一个普通 Pod，不具备故障切换能力。static Pod 由 kubelet 直接管理，即使 API Server 不可达也能正常运行，这才是 kube-vip 作为 API Server 负载均衡器的正确部署方式。

### 关键配置

- `kubernetes_addr=lb.kubesphere.local:6443`：覆盖默认的 `kubernetes:<port>` 地址
- `lb.kubesphere.local` 由 KubeKey 部署时自动写入每个节点的 `/etc/hosts`
- 无需 `hostAliases` 或手动修改 `/etc/hosts`

## 部署文件说明

| 文件 | 说明 |
|------|------|
| `deploy/kube-vip/deploy-kube-vip.sh` | HA 部署脚本（自动分发到所有 CP 节点） |
| `deploy/kube-vip/kube-vip.yaml` | kube-vip static Pod manifest 模板 |

## 常见问题

### 1. kube-vip Pod 未启动

**原因**：manifest 未正确分发或 kubeconfig 不可用。

**解决**：
```bash
# 检查 manifest 是否存在于所有 CP 节点
ansible -i deploy/hosts all -m shell -a "ls -la /etc/kubernetes/manifests/kube-vip.yaml"

# 检查 kubelet 日志
ssh <node> sudo journalctl -u kubelet -f | grep kube-vip
```

### 2. VIP 无法访问

**原因**：网络接口配置错误或 ARP 未广播。

**解决**：
```bash
# 检查网络接口
ip addr show <INTERFACE>

# 检查 ARP 配置
cat /proc/sys/net/ipv4/conf/*/arp_ignore

# 手动触发 ARP（在持有 VIP 的节点上）
arping -c 3 -I <INTERFACE> <VIP>
```

### 3. kubeconfig 更新后无法连接

**原因**：VIP 尚未生效就更新了 kubeconfig。

**解决**：
```bash
# 临时恢复 kubeconfig 指向原节点 IP
kubectl config set-cluster kubernetes --server=https://<原节点IP>:6443

# 验证 VIP 生效后再更新
ping <VIP>
kubectl --server=https://<VIP>:6443 --insecure-skip-tls-verify=true get nodes
```

## 后续步骤

kube-vip 部署完成后，继续部署 CNI（如 Kube-OVN）使节点变为 Ready 状态。
