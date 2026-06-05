---
name: longhorn-deploy
description: 部署 Longhorn 分布式存储到 K8s 集群。当用户提到"部署 longhorn"、"安装 longhorn"、"longhorn 存储"、"分布式存储"、"持久化存储"时触发。支持专用磁盘配置、open-iscsi 安装、Helm 部署和验证。
---

# Longhorn 分布式存储部署

在已有的 Kubernetes 集群上部署 Longhorn 分布式块存储。

## 前置条件

- K8s 集群已就绪（节点 Ready）
- CNI 已部署（如 Kube-OVN）
- `kubectl` 和 `helm` 命令可用
- Ansible 可选（用于批量节点配置）

## 执行流程

### Step 0: 环境检查

检查 helm、kubectl 和集群状态：

```bash
# 检查 helm
if ! command -v helm &>/dev/null; then
  echo "安装 helm..."
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# 检查 kubectl
if ! command -v kubectl &>/dev/null; then
  echo "错误: kubectl 未安装" >&2
  exit 1
fi

# 检查集群状态
echo "集群状态:"
kubectl get nodes -o wide
```

**预期状态**：所有节点 Ready

### Step 1: 检查节点前置依赖

Longhorn 依赖 `open-iscsi`，在每个节点上检查并安装：

```bash
# 方式一：Ansible 批量安装（推荐，需要 deploy/hosts 文件）
ansible -i deploy/hosts all -m shell -a "apt-get install -y open-iscsi && systemctl enable --now iscsid" -u zcq --become

# 方式二：手动在每个节点执行
sudo apt-get install -y open-iscsi
sudo systemctl enable --now iscsid
```

验证安装：
```bash
ansible -i deploy/hosts all -m shell -a "dpkg -l | grep open-iscsi && systemctl is-active iscsid && lsmod | grep iscsi_tcp" -u zcq
```

### Step 2: 配置专用存储盘（推荐）

Longhorn 默认使用根分区 `/var/lib/longhorn/`。生产环境建议添加专用磁盘：

```bash
# 1. 扫描新磁盘（热添加后需要）
ansible -i deploy/hosts all -m shell -a "for host in /sys/class/scsi_host/host*/scan; do echo '- - -' > \$host; done" -u zcq --become

# 2. 检查磁盘
ansible -i deploy/hosts all -m shell -a "lsblk -d -o NAME,SIZE,TYPE,MOUNTPOINT" -u zcq

# 3. 格式化磁盘（以 /dev/sdb 为例）
ansible -i deploy/hosts all -m shell -a "mkfs.ext4 /dev/sdb" -u zcq --become

# 4. 挂载到 Longhorn 目录
ansible -i deploy/hosts all -m shell -a "mkdir -p /var/lib/longhorn && mount /dev/sdb /var/lib/longhorn" -u zcq --become

# 5. 持久化挂载（写入 /etc/fstab）
ansible -i deploy/hosts all -m shell -a "echo '/dev/sdb /var/lib/longhorn ext4 defaults,noatime 0 2' >> /etc/fstab" -u zcq --become
```

### Step 3: 部署 Longhorn

```bash
bash deploy/longhorn/deploy.sh
```

部署脚本会：
1. 检查 iscsid 服务状态
2. 添加 Longhorn Helm 仓库
3. 执行 `helm install`（约 2-5 分钟）
4. 验证部署状态

### Step 4: 验证部署

```bash
# 1. 检查 Pod 状态（所有 Pod 应为 Running）
kubectl get pods -n longhorn-system -o wide

# 2. 检查 Longhorn 节点（所有节点应为 Ready, Schedulable）
kubectl get nodes.longhorn.io -n longhorn-system

# 3. 检查 StorageClass
kubectl get sc

# 4. 验证存储盘挂载
ansible -i deploy/hosts all -m shell -a "df -Th /var/lib/longhorn" -u zcq

# 5. 检查存储容量
kubectl get nodes.longhorn.io -n longhorn-system -o yaml | grep -E "storageAvailable:|storageMaximum:"
```

### Step 5: 存储功能测试

```bash
# 创建测试 PVC
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-longhorn-pvc
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: longhorn
  resources:
    requests:
      storage: 1Gi
EOF

# 检查 PVC 状态（应为 Bound）
kubectl get pvc test-longhorn-pvc

# 创建测试 Pod 使用该 PVC
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: test-longhorn-pod
spec:
  containers:
  - name: test
    image: busybox
    command: ["sleep", "3600"]
    volumeMounts:
    - mountPath: /data
      name: test-volume
  volumes:
  - name: test-volume
    persistentVolumeClaim:
      claimName: test-longhorn-pvc
EOF

# 验证 Pod 运行和卷挂载
kubectl get pod test-longhorn-pod
kubectl exec test-longhorn-pod -- df -h /data

# 清理测试资源
kubectl delete pod test-longhorn-pod
kubectl delete pvc test-longhorn-pvc
```

## 常见问题

### 1. Pod 卡在 ContainerCreating

**原因**：通常是镜像拉取慢或 iscsi 组件未就绪。

**解决**：
```bash
# 检查事件
kubectl describe pod <pod-name> -n longhorn-system

# 检查 iscsi
ansible -i deploy/hosts all -m shell -a "systemctl status iscsid" -u zcq
```

### 2. 存储容量显示为 0

**原因**：Longhorn 未检测到磁盘变更。

**解决**：
```bash
# 重启 Longhorn Manager
kubectl delete pod -n longhorn-system -l app=longhorn-manager

# 等待 30 秒后重新检查
sleep 30
kubectl get nodes.longhorn.io -n longhorn-system -o yaml | grep storageAvailable
```

### 3. 卸载 Longhorn 失败

**原因**：需要设置删除确认标志。

**解决**：
```bash
kubectl patch settings.longhorn.io -n longhorn-system deleting-confirmation-flag --type=merge -p '{"value": "true"}'
helm uninstall longhorn -n longhorn-system
```

## 部署文件说明

| 文件 | 说明 |
|------|------|
| `deploy/longhorn/deploy.sh` | Longhorn 部署脚本 |
| `deploy/hosts` | Ansible 节点清单（批量配置用） |

## 后续步骤

Longhorn 部署完成后，可继续：
- 部署 KubeVirt（运行 Windows VM）
- 部署监控（Prometheus Operator）
- 配置 Longhorn 备份目标（S3/NFS）
