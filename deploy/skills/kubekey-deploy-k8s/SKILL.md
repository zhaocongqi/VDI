---
name: kubekey-deploy-k8s
description: 使用 KubeKey v4 部署 Kubernetes HA 集群。当用户提到"部署 k8s"、"安装 kubernetes"、"kubekey"、"kk 部署"、"创建 k8s 集群"、"k8s 集群安装"时触发。支持自定义节点数量、hostname、CNI、存储等配置。
---

# KubeKey 部署 K8s 集群

使用 KubeKey v4 在目标服务器上部署 Kubernetes HA 集群。

## 前置条件

> ⚠️ **执行本 skill 前请先完成 `os-init` skill**，确保操作系统已初始化（swap 关闭、内核参数、时间同步等）。

## 执行流程

按以下步骤顺序执行，每步完成后再进入下一步。

### Step 0: 环境检查

检查本地工具和目标节点状态：

```bash
# 加载共享配置
source deploy/env-config.sh

# ── 检查本地工具 ──
for cmd in curl python3 sudo ssh; do
  command -v $cmd &>/dev/null && echo "$cmd: OK" || echo "$cmd: MISSING"
done

# 检查/安装 kubectl
if ! command -v kubectl &>/dev/null; then
  echo "安装 kubectl..."
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x kubectl && sudo mv kubectl /usr/local/bin/
fi

# 检查/安装 helm
if ! command -v helm &>/dev/null; then
  echo "安装 helm..."
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# ── 检查节点 OS 状态 ──
echo ""
echo "=== 节点 OS 状态检查 ==="

# swap 状态（应为空）
ansible -i deploy/hosts all -m shell -a "swapon --show || echo 'swap: OK (已关闭)'" --become

# 内核参数
ansible -i deploy/hosts all -m shell -a "sysctl net.bridge.bridge-nf-call-iptables net.ipv4.ip_forward" --become

# 时间同步
ansible -i deploy/hosts all -m shell -a "timedatectl | grep -E 'Sync|NTP'" --become

# 关键端口检查（必须可用）
ansible -i deploy/hosts all -m shell -a "
  for port in 6443 2379 2380 10250 10259 10257; do
    ss -tlnp | grep -q ':${port} ' && echo '端口 ${port}: 已占用 ⚠' || echo '端口 ${port}: 可用 ✓'
  done
" --become

# 硬件资源（最低: 2CPU / 4GB 内存）
ansible -i deploy/hosts all -m shell -a "
  CPU=\$(nproc)
  MEM=\$(free -m | awk '/Mem:/{print \$2}')
  echo \"CPU: \${CPU} 核, 内存: \${MEM} MB\"
  [ \${CPU} -lt 2 ] && echo '⚠ CPU 不足 2 核' || true
  [ \${MEM} -lt 3600 ] && echo '⚠ 内存不足 4 GB' || true
" --become
```

**通过标准**：
- ✅ 所有工具可用
- ✅ swap 已关闭
- ✅ `bridge-nf-call-iptables = 1`，`ip_forward = 1`
- ✅ 时间同步已启用
- ✅ 关键端口全部可用
- ✅ 每个节点 ≥ 2 CPU / 4 GB 内存

### Step 1: 收集节点信息

向用户收集以下信息（逐个提问）：

1. **节点列表**：每个节点的 IP、SSH 用户、SSH 密码（或密钥路径）、SSH 端口（默认 22）
2. **节点 hostname**：每个节点的目标 hostname（必须全小写字母、数字、`-`，K8s 规范要求）
3. **角色分配**：哪些节点是 control_plane，哪些是 worker，哪些跑 etcd（测试环境通常全部兼任）
4. **K8s 版本**：默认从 `deploy/env-config.sh` 读取（`v1.34.3`）
5. **CNI 类型**：留空（后续手动安装 Kube-OVN）
6. **是否安装 NodeLocalDNS**：默认是
7. **HA 负载均衡**：local / kube-vip / haproxy（测试环境默认 local）
8. **kube-vip VIP**：虚拟 IP 地址（从 `deploy/env-config.sh` 读取）
9. **kube-vip 网络接口**：节点的网络接口名（从 `deploy/env-config.sh` 读取）

### Step 2: 创建部署目录和配置文件

在项目根目录下创建 `deploy/k8s/` 目录，生成以下文件：

#### inventory.yaml

> ⚠️ `inventory.yaml` 包含 SSH 密码，已在 `.gitignore` 中排除。仅 `inventory.yaml.template` 会提交到 Git。

```yaml
apiVersion: kubekey.kubesphere.io/v1
kind: Inventory
metadata:
  name: <集群名称>
spec:
  hosts:
    <hostname-1>:
      connector:
        type: ssh
        host: <ip-1>
        port: <ssh-port>
        user: <ssh-user>
        password: "<ssh-password>"
      internal_ipv4: <ip-1>
    <hostname-2>:
      connector:
        type: ssh
        host: <ip-2>
        port: <ssh-port>
        user: <ssh-user>
        password: "<ssh-password>"
      internal_ipv4: <ip-2>
    # ... 更多节点
  groups:
    k8s_cluster:
      groups:
        - kube_control_plane
        - kube_worker
    kube_control_plane:
      hosts:
        - <hostname-1>
        - <hostname-2>
        # ...
    kube_worker:
      hosts:
        - <hostname-1>
        - <hostname-2>
        # ...
    etcd:
      hosts:
        - <hostname-1>
        - <hostname-2>
        # ...
```

#### config.yaml

```yaml
apiVersion: kubekey.kubesphere.io/v1
kind: Config
spec:
  kubernetes:
    kube_version: <k8s版本>
    helm_version: v3.18.5
    control_plane_endpoint:
      type: <lb类型>
      host: lb.kubesphere.local
      port: 6443
  etcd:
    etcd_version: v3.6.5
  cri:
    container_manager: containerd
  cni:
    type: <cni类型>  # 留空 "" 跳过 CNI 安装
  storage_class:
    local:
      enabled: <true/false>
  dns:
    coredns:
      image:
        tag: v1.12.1
    nodelocaldns:
      enabled: <true/false>
      image:
        tag: 1.26.4
  image_registry:
    type: ""
  native:
    set_hostname: true  # 根据 inventory 自动设置节点 hostname
```

**配置说明**：
- `cni.type: ""` — 空字符串跳过 CNI 安装，KubeKey 预检会跳过 CNI 验证
- `cni.type` 只支持：calico、cilium、flannel、hybridnet、kube-ovn（不能用 none 或 other）
- `native.set_hostname: true` — 自动将节点 hostname 设置为 inventory 中的 key 名
- `storage_class.local.enabled: false` — 跳过 OpenEBS 安装
- Service CIDR 默认使用 K8s 默认值 `10.96.0.0/12`，须与 `deploy/kube-ovn/chart/values.yaml` 中的 `SVC_CIDR` 一致

### Step 3: 下载 kk 二进制

```bash
bash deploy/skills/kubekey-deploy-k8s/scripts/download-kk.sh [版本]
# 默认版本从 deploy/env-config.sh 读取
```

如果下载失败（网络问题），通过 GitHub API 查找正确的资源文件名：
```bash
curl -s https://api.github.com/repos/kubesphere/kubekey/releases/tags/<VERSION> | python3 -c "import sys,json; [print(a['name']) for a in json.load(sys.stdin).get('assets',[])]"
```

### Step 4: 运行预检

```bash
kk precheck -i deploy/k8s/inventory.yaml -c deploy/k8s/config.yaml
```

预检通过标准：`failed: 0`。如果失败，分析错误原因并修复配置后重试。

### Step 5: 部署集群

```bash
kk create cluster -i deploy/k8s/inventory.yaml -c deploy/k8s/config.yaml
```

部署约 10-20 分钟。成功标准：`failed: 0`。

### Step 6: 验证集群

```bash
# 通过 kubeconfig 检查（KubeKey 会自动将 kubeconfig 复制到 ~/.kube/config）
kubectl get nodes -o wide
kubectl get cs
kubectl get pods -A
```

**预期状态**（无 CNI 时）：
- 节点：NotReady（正常，等待 CNI）
- CoreDNS：Pending（正常，等待 CNI）
- NodeLocalDNS：Running
- kube-apiserver/controller-manager/scheduler：Running
- etcd：Healthy

### Step 7: 保存配置文件

- `config.yaml`：提交到 Git
- `inventory.yaml`：已在 `.gitignore` 中排除（含密码），仅保留 `.template` 模板

## 注意事项

- K8s hostname 必须**全小写**，只能包含字母、数字、`-`、`.`
- `cni.type` 不支持 `none` 或 `other`，留空字符串 `""` 跳过 CNI
- v4.x 下载链接格式：`kubekey-v4.x.x-linux-amd64.tar.gz`（不是 `kk-linux-amd64`）
- 非 root 用户需要有免密 sudo 权限，KubeKey 会自动用 `sudo -E` 执行命令
- `native.set_hostname: true` 会将节点 hostname 改为 inventory 中的 key 名
- 删除集群后旧节点可能残留，需要手动 `kubectl delete node` 清理

## 后续步骤

K8s 集群部署完成后，按以下顺序部署其他组件：

1. **kube-vip**：API Server VIP（详见 `kubevip-deploy` skill）
2. **Kube-OVN**：CNI 网络插件（详见 `kubeovn-deploy` skill）
3. **Longhorn**：分布式存储（详见 `longhorn-deploy` skill）

所有部署文件位于 `deploy/` 目录。
