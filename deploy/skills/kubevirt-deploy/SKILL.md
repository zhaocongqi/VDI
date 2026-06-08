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
- 所有工作节点支持 KVM 虚拟化（`/dev/kvm` 存在）

## 执行流程

### Step 0: 环境检查

检查 KVM 支持（所有节点）和集群状态：

```bash
# 加载共享配置
source deploy/env-config.sh

# 检查 KVM 支持（Ansible 批量检查所有节点）
ansible -i deploy/hosts all -m shell -a "
  if [ -e /dev/kvm ]; then
    echo 'KVM: OK (\$(stat -c \"%a\" /dev/kvm 2>/dev/null))'
  else
    echo 'KVM: MISSING'
  fi
  lsmod | grep kvm || true
" --become

# 检查集群状态
kubectl get nodes -o wide

# 检查存储
kubectl get sc
```

**预期状态**：
- 所有节点 Ready
- 所有节点 `/dev/kvm` 存在
- StorageClass 可用（如 longhorn）

**如果 KVM 不可用**：
```bash
# 加载 KVM 模块
ansible -i deploy/hosts all -m shell -a "
  modprobe kvm_intel 2>/dev/null || modprobe kvm_amd 2>/dev/null || true
  echo 'options kvm_intel nested=1' > /etc/modprobe.d/kvm.conf 2>/dev/null || true
" --become

# 修复权限（使用 kvm 组，而非 chmod 666）
ansible -i deploy/hosts all -m shell -a "
  groupadd --system kvm 2>/dev/null || true
  chmod 660 /dev/kvm 2>/dev/null || true
  chown root:kvm /dev/kvm 2>/dev/null || true
  echo 'KERNEL==\"kvm\", GROUP=\"kvm\", MODE=\"0660\"' > /etc/udev/rules.d/99-kvm.rules
" --become
```

### Step 1: 部署 KubeVirt

```bash
bash deploy/kubevirt/deploy.sh [版本]
# 示例: bash deploy/kubevirt/deploy.sh v1.5.0
# 版本默认从 deploy/env-config.sh 读取
```

部署脚本会：
1. 通过 Ansible 或 kubectl 检查**所有节点**的 KVM 支持
2. 创建命名空间
3. 部署 KubeVirt Operator
4. 等待 Operator 就绪
5. 部署 KubeVirt CR
6. 验证部署状态

### Step 2: 安装 virtctl 工具

```bash
# 版本从 env-config.sh 读取，或手动指定
source deploy/env-config.sh
VERSION="${KUBEVIRT_VERSION:-v1.5.0}"

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

# 3. 检查所有节点 KVM 设备
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.devices\.kubevirt\.io/kvm}{"\n"}{end}' 2>/dev/null || echo "KVM 设备信息暂不可用（KubeVirt 安装后自动注册）"
```

### Step 4: 部署 CDI（容器化数据导入器）

CDI 用于将 VM 镜像导入 PVC。**CDI 版本应与 KubeVirt 版本匹配**，版本从 `deploy/env-config.sh` 读取：

```bash
source deploy/env-config.sh
CDI_VERSION="${CDI_VERSION:-v1.61.0}"

echo "部署 CDI ${CDI_VERSION}（匹配 KubeVirt ${KUBEVIRT_VERSION}）..."
kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-operator.yaml"
kubectl apply -f "https://github.com/kubevirt/containerized-data-importer/releases/download/${CDI_VERSION}/cdi-cr.yaml"

# 等待 CDI 就绪
echo "等待 CDI 组件就绪..."
kubectl wait --for=condition=Available deployment/cdi-apiserver -n cdi --timeout=300s
kubectl wait --for=condition=Available deployment/cdi-deployment -n cdi --timeout=300s

# 验证 CDI
kubectl get pods -n cdi
```

**版本兼容性参考**：CDI 和 KubeVirt 版本号独立发布，建议使用同一发布周期内的版本。详见 [CDI 兼容性矩阵](https://github.com/kubevirt/containerized-data-importer#compatibility)。

### Step 5: 测试部署

#### 5a: ContainerDisk 测试（快速，无需 PVC）

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

virtctl start test-vm
kubectl get vmi test-vm
virtctl console test-vm
virtctl stop test-vm
kubectl delete vm test-vm
```

#### 5b: PVC 测试（验证 Longhorn 存储，推荐）

```bash
cat <<EOF | kubectl apply -f -
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: test-vm-pvc
spec:
  running: false
  template:
    metadata:
      labels:
        kubevirt.io/vm: test-vm-pvc
    spec:
      domain:
        devices:
          disks:
          - name: rootdisk
            disk:
              bus: virtio
        resources:
          requests:
            memory: 256Mi
      volumes:
      - name: rootdisk
        persistentVolumeClaim:
          claimName: test-vm-pvc-disk
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-vm-pvc-disk
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF

virtctl start test-vm-pvc
kubectl get vmi test-vm-pvc -w
# 等待 Running 后验证
virtctl stop test-vm-pvc
kubectl delete vm test-vm-pvc
```

## 技术细节

### KubeVirt 架构

- **virt-operator**: 管理 KubeVirt 组件的生命周期
- **virt-api**: KubeVirt API 服务器
- **virt-controller**: 管理 VM 生命周期
- **virt-handler**: 每个节点上的 DaemonSet，管理 VM 运行时
- **virt-launcher**: 每个 VM 的 Pod，运行 QEMU 进程

### KVM 安全权限

推荐使用 kvm 组权限（`660`）而非宽松的 `666`：
```bash
# /dev/kvm 权限应如下：
# crw-rw---- 1 root kvm 10, 232 ... /dev/kvm
sudo groupadd --system kvm
sudo chmod 660 /dev/kvm
sudo chown root:kvm /dev/kvm

# 持久化规则（udev）
echo 'KERNEL=="kvm", GROUP="kvm", MODE="0660"' | sudo tee /etc/udev/rules.d/99-kvm.rules
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
| `deploy/kubevirt/deploy.sh` | KubeVirt 部署脚本（多节点 KVM 检查） |
| `deploy/env-config.sh` | 共享环境配置（版本号、用户名等） |

## 常见问题

### 1. VM 无法启动，提示 KVM 不可用

**原因**：节点不支持 KVM 或 `/dev/kvm` 权限错误。

**解决**：
```bash
source deploy/env-config.sh
# 检查所有节点 KVM
ansible -i deploy/hosts all -m shell -a "ls -la /dev/kvm && lsmod | grep kvm" --become

# 修复权限（使用 kvm 组）
ansible -i deploy/hosts all -m shell -a "
  chmod 660 /dev/kvm && chown root:kvm /dev/kvm
" --become
```

### 2. VM 启动后无法获取 IP

**原因**：CNI 配置错误或 Pod 网络不通。

**解决**：
```bash
kubectl get pod -l kubevirt.io/vm=test-vm -o wide
kubectl exec <pod-name> -- ip addr show
```

### 3. CDI 导入镜像失败

**原因**：存储空间不足或网络问题。

**解决**：
```bash
kubectl get pvc
kubectl logs -n cdi -l app=cdi
```

## 后续步骤

KubeVirt 部署完成后，可继续：
- 创建 Windows VM 模板
- 配置 GPU 直通
- 部署 WebRTC 媒体网关
- 配置 VM 自动化管理
