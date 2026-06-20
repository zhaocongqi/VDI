# KubeKey 部署 K8s HA 集群设计文档

## 目标

使用 KubeKey v4 在 3 台 Ubuntu 虚拟机上部署 Kubernetes v1.34.3 HA 集群（3 master 兼 worker），不安装 CNI、负载均衡器和存储。这些组件后续独立部署。

## 需求摘要

| 维度 | 选择 |
|------|------|
| 环境 | 本地虚拟机，可上网，测试学习 |
| 规模 | 3 节点 HA（master 兼 worker） |
| OS | Ubuntu 22.04/24.04 |
| K8s | v1.34.3 |
| CNI | none（后续手动部署 Kube-OVN） |
| HA LB | 无（后续手动部署 kube-vip） |
| 存储 | 无（后续手动部署 Longhorn） |
| 镜像源 | 公共仓库，官方源 |
| 规格 | 4C8G × 3 |
| DNS | CoreDNS + NodeLocalDNS |

## 前置条件

- 3 台 Ubuntu 22.04/24.04 虚拟机，每台 4C8G 100GB 磁盘
- 所有节点间网络互通（同一子网）
- root 用户可 SSH 登录（密码或密钥认证）
- 所有节点可访问互联网（下载镜像和二进制）
- 执行部署的机器（可以是其中一台节点或独立的管理机）有 SSH 客户端

## 目录结构

```
deploy/k8s/
├── README.md              # 部署说明文档
├── inventory.yaml         # 节点清单（SSH 连接信息 + 角色分组）
├── config.yaml            # 集群配置（K8s 版本、CNI、存储等）
└── download-kk.sh         # kk 二进制下载脚本
```

## 组件版本

| 组件 | 版本 |
|------|------|
| KubeKey (kk) | v4.x（从 GitHub Release 下载最新） |
| Kubernetes | v1.34.3 |
| etcd | v3.6.5 |
| containerd | KubeKey 自动选择 |
| Helm | v3.18.5 |
| CoreDNS | v1.12.1 |
| NodeLocalDNS | 1.26.4 |

## 配置详情

### inventory.yaml

定义 3 个节点的 SSH 连接信息和角色分组。所有节点同时担任 control_plane、worker 和 etcd 角色。

```yaml
apiVersion: kubekey.kubesphere.io/v1
kind: Inventory
metadata:
  name: vdi-cluster
spec:
  hosts:
    node1:
      connector:
        type: ssh
        host: <node1-ip>
        port: 22
        user: root
        password: <password>
      internal_ipv4: <node1-ip>
    node2:
      connector:
        type: ssh
        host: <node2-ip>
        port: 22
        user: root
        password: <password>
      internal_ipv4: <node2-ip>
    node3:
      connector:
        type: ssh
        host: <node3-ip>
        port: 22
        user: root
        password: <password>
      internal_ipv4: <node3-ip>
  groups:
    k8s_cluster:
      groups:
        - kube_control_plane
        - kube_worker
    kube_control_plane:
      hosts:
        - node1
        - node2
        - node3
    kube_worker:
      hosts:
        - node1
        - node2
        - node3
    etcd:
      hosts:
        - node1
        - node2
        - node3
```

### config.yaml

精简配置，只安装 K8s 核心组件。

```yaml
apiVersion: kubekey.kubesphere.io/v1
kind: Config
spec:
  kubernetes:
    kube_version: v1.34.3
    helm_version: v3.18.5
    control_plane_endpoint:
      type: local
      host: lb.kubesphere.local
      port: 6443
  etcd:
    etcd_version: v3.6.5
  cri:
    container_manager: containerd
  cni:
    type: none
  storage_class:
    local:
      enabled: false
  dns:
    coredns:
      image:
        tag: v1.12.1
    nodelocaldns:
      enabled: true
      image:
        tag: 1.26.4
  image_registry:
    type: ""
```

**配置说明**：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `control_plane_endpoint.type` | `local` | 不安装 LB，API Server 端点由本地 DNS 解析 |
| `cni.type` | `none` | 跳过 CNI 安装，节点将处于 NotReady 状态 |
| `storage_class.local.enabled` | `false` | 跳过 OpenEBS LocalPV 安装 |
| `image_registry.type` | `""` | 跳过私有镜像仓库安装 |
| `dns.nodelocaldns.enabled` | `true` | 安装 NodeLocalDNS 缓存 |

## 部署步骤

### Step 1: 下载 kk 二进制

从 KubeKey GitHub Release 下载最新版本的 kk 二进制文件。

```bash
# 下载 kk（Linux amd64）
curl -Lo kk https://github.com/kubesphere/kubekey/releases/latest/download/kk-linux-amd64
chmod +x kk
sudo mv kk /usr/local/bin/kk

# 验证
kk version
```

### Step 2: 准备配置文件

```bash
# 生成 inventory 和 config 模板
kk create inventory -o deploy/k8s/
kk create config --with-kubernetes v1.34.3 -o deploy/k8s/

# 编辑 inventory.yaml：填入 3 个节点的实际 IP 和密码
# 编辑 config.yaml：按上述配置修改
```

### Step 3: 部署集群

```bash
kk create cluster -i deploy/k8s/inventory.yaml -c deploy/k8s/config.yaml
```

部署过程约 10-20 分钟，KubeKey 会自动：
1. SSH 到所有节点，检查前置条件
2. 安装 containerd 容器运行时
3. 安装 kubeadm/kubelet/kubectl
4. 初始化 etcd 集群
5. 初始化第一个 control plane 节点
6. 加入其余 control plane 节点
7. 安装 CoreDNS 和 NodeLocalDNS
8. 安装 Helm

### Step 4: 验证集群

```bash
# 检查节点状态（预期：NotReady，因为没有 CNI）
kubectl get nodes

# 检查组件状态
kubectl get cs

# 检查 Pod 状态（预期：coredns 和 nodelocaldns 的 Pod 处于 Pending）
kubectl get pods -A

# 检查 etcd 集群健康
kubectl -n kube-system exec etcd-node1 -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  endpoint health
```

**预期状态**：
- 3 个节点显示 `NotReady`（正常，因为没有 CNI）
- kube-system Pod 中 CoreDNS 和 NodeLocalDNS 处于 `Pending`（等待 CNI）
- etcd 集群健康
- kube-apiserver、kube-controller-manager、kube-scheduler 正常运行

## 后续步骤（不在本次设计范围内）

1. **部署 kube-vip** — 为 API Server 提供 VIP，节点变为 Ready
2. **部署 Kube-OVN** — 提供 Pod 网络和 VPC 能力
3. **部署 Longhorn** — 提供分布式块存储

## 风险与注意事项

1. **节点 NotReady 是正常的** — 没有 CNI 时节点必然 NotReady，这是预期行为
2. **control_plane_endpoint.type=local 的含义** — control plane 节点将 endpoint 解析为 127.0.0.1，worker 节点解析为第一个 control plane 节点。后续部署 kube-vip 时需要更新此配置
3. **SSH 连接稳定性** — 部署过程需要持续 SSH 连接，确保网络稳定
4. **磁盘空间** — 每个节点需要约 30GB 用于镜像和组件，100GB 磁盘空间充足
