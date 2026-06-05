---
name: kubevirt-deploy
description: 部署 KubeVirt 到 K8s 集群，支持运行 Windows/Linux 虚拟机。当用户提到"部署 kubevirt"、"安装 kubevirt"、"虚拟机"、"VM"、"Windows VM"、"KubeVirt"时触发。支持 KVM 硬件加速、CDI 数据导入、virtctl 工具安装。
---

# KubeVirt 部署

在 Kubernetes 集群上部署 KubeVirt，支持运行 Windows/Linux 虚拟机。

## 前置条件

- K8s 集群已就绪（节点 Ready）
- CNI 已部署（如 Kube-OVN）
- 存储已部署（如 Longhorn）
- 节点支持 KVM 虚拟化（`/dev/kvm` 存在）

## 执行流程

### Step 0: 环境检查

检查 KVM 支持和集群状态：

```bash
# 检查 KVM 支持（在每个节点执行）
ansible -i deploy/hosts all -m shell -a "ls -la /dev/kvm && lsmod | grep kvm" -u zcq

# 检查集群状态
kubectl get nodes -o wide

# 检查存储
kubectl get sc
```

**预期状态**：
- 所有节点 Ready
- `/dev/kvm` 存在且权限正确
- StorageClass 可用（如 longhorn）

### Step 1: 部署 KubeVirt

```bash
bash deploy/kubevirt/deploy.sh [版本]
# 示例: bash deploy/kubevirt/deploy.sh v1.5.0
```

部署脚本会：
1. 检查 KVM 支持
2. 创建命名空间
3. 部署 KubeVirt Operator
4. 部署 KubeVirt CR
5. 验证部署状态

### Step 2: 安装 virtctl 工具

```bash
# 下载 virtctl
VERSION="v1.5.0"
curl -Lo /tmp/virtctl "https://github.com/kubevirt/kubevirt/releases/download/${VERSION}/virtctl-${VERSION}-linux-amd64"
chmod +x /tmp/virtctl
sudo mv /tmp/virtctl /usr/local/bin/virtctl

# 验证安装
virtctl version
```

### Step 3: 验证部署

```bash
# 1. 检查 KubeVirt 组件
kubectl get pods -n kubevirt

# 2. 检查 KubeVirt 版本
kubectl get kubevirt.kubevirt.io -n kubevirt

# 3. 检查节点 KVM 设备
kubectl get nodes -o jsonpath='{.items[*].status.allocatable.devices\.kubevirt\.io/kvm}' 2>/dev/null || echo "KVM 设备信息暂不可用"
```

### Step 4: 部署 CDI（容器化数据导入器）

CDI 用于将 VM 镜像导入 PVC：

```bash
# 部署 CDI
CDI_VERSION="v1.61.0"
kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml"
kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml"

# 验证 CDI
kubectl get pods -n cdi
```

### Step 5: 测试部署

创建一个简单的测试 VM：

```bash
cat <<EOF | kubectl apply -f -
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: test-vm
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/vm: test-vm
    spec:
      domain:
        devices:
          disks:
          - name: containerdisk
            disk:
              bus: virtio
        resources:
          requests:
            memory: 128Mi
      volumes:
      - name: containerdisk
        containerDisk:
          image: quay.io/kubevirt/cirros-container-disk-demo
EOF

# 启动 VM
virtctl start test-vm

# 检查 VM 状态
kubectl get vmi test-vm

# 连接到 VM 控制台
virtctl console test-vm

# 停止 VM
virtctl stop test-vm

# 删除测试 VM
kubectl delete vm test-vm
```

## 技术细节

### KubeVirt 架构

- **virt-operator**: 管理 KubeVirt 组件的生命周期
- **virt-api**: KubeVirt API 服务器
- **virt-controller**: 管理 VM 生命周期
- **virt-handler**: 每个节点上的 DaemonSet，管理 VM 运行时
- **virt-launcher**: 每个 VM 的 Pod，运行 QEMU 进程

### KVM 设备插件

KubeVirt 使用设备插件将 `/dev/kvm` 暴露给 VM：

```yaml
# 检查 KVM 设备分配
kubectl get nodes -o jsonpath='{.items[*].status.allocatable.devices\.kubevirt\.io/kvm}'
```

### VM 存储选项

| 存储类型 | 用途 | 推荐 |
|----------|------|------|
| PVC | VM 系统盘 | ✅ 生产环境 |
| ContainerDisk | 临时测试盘 | ✅ 测试环境 |
| DataVolume | 自动导入镜像 | ✅ 生产环境 |

## 部署文件说明

| 文件 | 说明 |
|------|------|
| `deploy/kubevirt/deploy.sh` | KubeVirt 部署脚本 |

## 常见问题

### 1. VM 无法启动，提示 KVM 不可用

**原因**：节点不支持 KVM 或 `/dev/kvm` 权限错误。

**解决**：
```bash
# 检查 KVM 支持
ls -la /dev/kvm
lsmod | grep kvm

# 修复权限
sudo chmod 666 /dev/kvm
```

### 2. VM 启动后无法获取 IP

**原因**：CNI 配置错误或 Pod 网络不通。

**解决**：
```bash
# 检查 VM Pod 网络
kubectl get pod -l kubevirt.io/vm=test-vm -o wide
kubectl exec <pod-name> -- ip addr show
```

### 3. CDI 导入镜像失败

**原因**：存储空间不足或网络问题。

**解决**：
```bash
# 检查 PVC 状态
kubectl get pvc

# 检查 CDI 日志
kubectl logs -n cdi -l app=cdi
```

## 后续步骤

KubeVirt 部署完成后，可继续：
- 创建 Windows VM 模板
- 配置 GPU 直通
- 部署 WebRTC 媒体网关
- 配置 VM 自动化管理
