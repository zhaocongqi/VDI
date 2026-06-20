# KubeKey 部署 K8s HA 集群实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用 KubeKey v4 在 3 台 Ubuntu 虚拟机上部署 K8s v1.34.3 HA 集群（3 master 兼 worker），不安装 CNI/LB/存储。

**Architecture:** KubeKey 只负责部署裸 K8s 集群（kubelet + containerd + etcd + CoreDNS + NodeLocalDNS）。CNI（Kube-OVN）、LB（kube-vip）、存储（Longhorn）后续独立部署。配置文件和脚本存放在 `deploy/k8s/` 目录。

**Tech Stack:** KubeKey v4, Kubernetes v1.34.3, containerd, etcd v3.6.5, CoreDNS v1.12.1, NodeLocalDNS 1.26.4

---

## 文件结构

```
deploy/k8s/
├── README.md              # 部署说明文档（中文）
├── inventory.yaml         # 节点清单（SSH 连接信息 + 角色分组）
├── config.yaml            # 集群配置（K8s 版本、CNI=none、无存储）
└── download-kk.sh         # kk 二进制下载脚本
```

---

### Task 1: 创建 deploy/k8s/ 目录和下载脚本

**Files:**
- Create: `deploy/k8s/download-kk.sh`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p deploy/k8s
```

- [ ] **Step 2: 创建 download-kk.sh**

创建 `deploy/k8s/download-kk.sh`，内容如下：

```bash
#!/usr/bin/env bash
set -euo pipefail

# KubeKey kk 二进制下载脚本
# 用法: bash download-kk.sh [版本]
# 示例: bash download-kk.sh v4.1.7
#       bash download-kk.sh          # 下载最新版本

VERSION="${1:-latest}"
ARCH="linux-amd64"
INSTALL_DIR="/usr/local/bin"

if [ "$VERSION" = "latest" ]; then
    DOWNLOAD_URL="https://github.com/kubesphere/kubekey/releases/latest/download/kk-${ARCH}"
    echo ">>> 下载 kk 最新版本..."
else
    DOWNLOAD_URL="https://github.com/kubesphere/kubekey/releases/download/${VERSION}/kk-${ARCH}"
    echo ">>> 下载 kk ${VERSION}..."
fi

curl -fLo /tmp/kk "${DOWNLOAD_URL}"
chmod +x /tmp/kk
sudo mv /tmp/kk "${INSTALL_DIR}/kk"

echo ">>> kk 安装完成: ${INSTALL_DIR}/kk"
kk version
```

- [ ] **Step 3: 设置脚本可执行权限**

```bash
chmod +x deploy/k8s/download-kk.sh
```

- [ ] **Step 4: 验证脚本语法**

```bash
bash -n deploy/k8s/download-kk.sh
```

Expected: 无输出（语法正确）

- [ ] **Step 5: 提交**

```bash
git add deploy/k8s/download-kk.sh
git commit -m "feat(k8s): 添加 kk 二进制下载脚本"
```

---

### Task 2: 创建 inventory.yaml 配置文件

**Files:**
- Create: `deploy/k8s/inventory.yaml`

- [ ] **Step 1: 创建 inventory.yaml**

创建 `deploy/k8s/inventory.yaml`，内容如下：

```yaml
apiVersion: kubekey.kubesphere.io/v1
kind: Inventory
metadata:
  name: vdi-cluster
spec:
  hosts:
    # ===== 请替换为实际 IP 和密码 =====
    node1:
      connector:
        type: ssh
        host: 192.168.1.101    # 替换为 node1 实际 IP
        port: 22
        user: root
        password: "your-password"  # 替换为实际密码，或使用 private_key
      internal_ipv4: 192.168.1.101
    node2:
      connector:
        type: ssh
        host: 192.168.1.102    # 替换为 node2 实际 IP
        port: 22
        user: root
        password: "your-password"
      internal_ipv4: 192.168.1.102
    node3:
      connector:
        type: ssh
        host: 192.168.1.103    # 替换为 node3 实际 IP
        port: 22
        user: root
        password: "your-password"
      internal_ipv4: 192.168.1.103
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

- [ ] **Step 2: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('deploy/k8s/inventory.yaml'))"
```

Expected: 无输出（语法正确）

- [ ] **Step 3: 提交**

```bash
git add deploy/k8s/inventory.yaml
git commit -m "feat(k8s): 添加 inventory.yaml 节点清单配置"
```

---

### Task 3: 创建 config.yaml 集群配置

**Files:**
- Create: `deploy/k8s/config.yaml`

- [ ] **Step 1: 创建 config.yaml**

创建 `deploy/k8s/config.yaml`，内容如下：

```yaml
apiVersion: kubekey.kubesphere.io/v1
kind: Config
spec:
  kubernetes:
    # K8s 版本
    kube_version: v1.34.3
    # Helm 版本
    helm_version: v3.18.5
    # API Server 端点配置
    control_plane_endpoint:
      # local 模式：control plane 节点解析为 127.0.0.1
      # 后续部署 kube-vip 时需更新此配置
      type: local
      host: lb.kubesphere.local
      port: 6443
  etcd:
    # etcd 版本
    etcd_version: v3.6.5
  cri:
    # 容器运行时（K8s >= 1.24 自动使用 containerd）
    container_manager: containerd
  cni:
    # 不安装 CNI，后续手动部署 Kube-OVN
    type: none
  storage_class:
    local:
      # 不安装默认存储，后续手动部署 Longhorn
      enabled: false
  dns:
    coredns:
      image:
        tag: v1.12.1
    nodelocaldns:
      # 启用 NodeLocalDNS 缓存
      enabled: true
      image:
        tag: 1.26.4
  image_registry:
    # 不安装私有镜像仓库
    type: ""
```

- [ ] **Step 2: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('deploy/k8s/config.yaml'))"
```

Expected: 无输出（语法正确）

- [ ] **Step 3: 提交**

```bash
git add deploy/k8s/config.yaml
git commit -m "feat(k8s): 添加 config.yaml 集群配置（CNI=none，无存储）"
```

---

### Task 4: 创建 README.md 部署说明

**Files:**
- Create: `deploy/k8s/README.md`

- [ ] **Step 1: 创建 README.md**

创建 `deploy/k8s/README.md`，内容如下：

```markdown
# K8s HA 集群部署指南

## 概述

使用 KubeKey v4 部署 K8s v1.34.3 HA 集群（3 master 兼 worker）。
不安装 CNI、负载均衡器和存储，这些组件后续独立部署。

## 前置条件

- 3 台 Ubuntu 22.04/24.04 虚拟机，每台 4C8G 100GB 磁盘
- 所有节点间网络互通（同一子网）
- root 用户可 SSH 登录（密码或密钥认证）
- 所有节点可访问互联网

## 快速开始

### 1. 下载 kk 二进制

```bash
bash download-kk.sh
```

### 2. 编辑配置文件

编辑 `inventory.yaml`，填入 3 个节点的实际 IP 和密码：

```bash
vim inventory.yaml
```

`config.yaml` 通常无需修改。

### 3. 部署集群

```bash
kk create cluster -i inventory.yaml -c config.yaml
```

部署过程约 10-20 分钟。

### 4. 验证集群

```bash
# 节点状态（预期：NotReady，因为没有 CNI）
kubectl get nodes

# 组件状态
kubectl get cs

# Pod 状态（coredns/nodelocaldns 预期 Pending）
kubectl get pods -A

# etcd 健康检查
kubectl -n kube-system exec etcd-$(hostname) -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  endpoint health
```

## 预期状态

| 组件 | 状态 | 说明 |
|------|------|------|
| 节点 | NotReady | 正常，等待 CNI |
| CoreDNS | Pending | 正常，等待 CNI |
| NodeLocalDNS | Pending | 正常，等待 CNI |
| etcd | Healthy | 正常 |
| kube-apiserver | Running | 正常 |
| kube-controller-manager | Running | 正常 |
| kube-scheduler | Running | 正常 |

## 后续步骤

1. 部署 kube-vip — 为 API Server 提供 VIP
2. 部署 Kube-OVN — 提供 Pod 网络
3. 部署 Longhorn — 提供持久化存储

## 组件版本

| 组件 | 版本 |
|------|------|
| KubeKey | v4.x |
| Kubernetes | v1.34.3 |
| etcd | v3.6.5 |
| containerd | KubeKey 自动选择 |
| Helm | v3.18.5 |
| CoreDNS | v1.12.1 |
| NodeLocalDNS | 1.26.4 |
```

- [ ] **Step 2: 提交**

```bash
git add deploy/k8s/README.md
git commit -m "docs(k8s): 添加 K8s 集群部署说明文档"
```

---

### Task 5: 下载 kk 二进制并预检

**Files:**
- None（操作步骤，不创建文件）

- [ ] **Step 1: 下载 kk 二进制**

在管理机上执行：

```bash
bash deploy/k8s/download-kk.sh
```

Expected 输出：
```
>>> 下载 kk 最新版本...
>>> kk 安装完成: /usr/local/bin/kk
version:
  version: v4.x.x
```

- [ ] **Step 2: 验证 kk 可用**

```bash
kk version
```

Expected: 显示 kk 版本号（v4.x.x）

- [ ] **Step 3: 检查 inventory.yaml 已编辑**

确认 `deploy/k8s/inventory.yaml` 中的 IP 和密码已替换为实际值：

```bash
grep -c "your-password" deploy/k8s/inventory.yaml
```

Expected: `0`（没有未替换的占位符）

- [ ] **Step 4: 检查 config.yaml 无需修改**

```bash
grep "type: none" deploy/k8s/config.yaml
```

Expected: `    type: none`

- [ ] **Step 5: 运行前置检查**

```bash
kk precheck -i deploy/k8s/inventory.yaml -c deploy/k8s/config.yaml
```

Expected: 所有节点通过前置检查（OS 兼容性、SSH 连接、磁盘空间、内核版本等）

---

### Task 6: 部署 K8s 集群

**Files:**
- None（操作步骤，不创建文件）

- [ ] **Step 1: 执行集群部署**

```bash
kk create cluster -i deploy/k8s/inventory.yaml -c deploy/k8s/config.yaml
```

Expected: 部署成功，输出类似：
```
Cluster vdi-cluster created successfully
```

部署过程约 10-20 分钟，KubeKey 自动完成：
1. SSH 到所有节点，检查前置条件
2. 安装 containerd 容器运行时
3. 安装 kubeadm/kubelet/kubectl
4. 初始化 etcd 集群（3 节点）
5. 初始化第一个 control plane 节点
6. 加入其余 control plane 节点
7. 安装 CoreDNS 和 NodeLocalDNS
8. 安装 Helm v3.18.5

- [ ] **Step 2: 验证节点状态**

```bash
kubectl get nodes -o wide
```

Expected 输出（3 个节点，全部 NotReady）：
```
NAME    STATUS     ROLES           AGE   VERSION
node1   NotReady   control-plane   1m    v1.34.3
node2   NotReady   control-plane   1m    v1.34.3
node3   NotReady   control-plane   1m    v1.34.3
```

- [ ] **Step 3: 验证组件状态**

```bash
kubectl get cs
```

Expected: apiserver、controller-manager、scheduler 均为 Healthy

- [ ] **Step 4: 验证 Pod 状态**

```bash
kubectl get pods -A
```

Expected: kube-system 中的 coredns 和 nodelocaldns Pod 处于 Pending 状态（等待 CNI）

- [ ] **Step 5: 验证 etcd 集群**

```bash
kubectl -n kube-system exec etcd-node1 -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  endpoint health
```

Expected: 3 个 etcd endpoint 均为 healthy

- [ ] **Step 6: 验证 Helm 可用**

```bash
helm version
```

Expected: 显示 Helm v3.18.5

---

### Task 7: 集群就绪确认

**Files:**
- None（验证步骤）

- [ ] **Step 1: 运行综合验证脚本**

```bash
echo "=== 节点状态 ==="
kubectl get nodes -o wide

echo ""
echo "=== 组件状态 ==="
kubectl get cs

echo ""
echo "=== 全部 Pod ==="
kubectl get pods -A

echo ""
echo "=== Helm 版本 ==="
helm version --short

echo ""
echo "=== etcd 集群健康 ==="
kubectl -n kube-system exec etcd-node1 -- etcdctl \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  endpoint health
```

- [ ] **Step 2: 确认后续步骤**

集群部署完成。后续独立任务：
1. 部署 kube-vip — 为 API Server 提供 VIP，节点将变为 Ready
2. 部署 Kube-OVN — 提供 Pod 网络，CoreDNS/NodeLocalDNS 将变为 Running
3. 部署 Longhorn — 提供持久化存储
