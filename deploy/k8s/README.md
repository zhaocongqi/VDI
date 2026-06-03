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