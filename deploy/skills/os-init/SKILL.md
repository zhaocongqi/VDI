---
name: os-init
description: 初始化操作系统环境，为 K8s 集群部署做准备。当用户提到"初始化节点"、"OS 初始化"、"节点准备"、"环境准备"、"prepare nodes"、"init os"、"部署前准备"时触发。包括关闭 swap、配置内核参数、安装依赖、配置 SSH、时间同步等。
---

# 操作系统初始化（K8s 部署前置）

在目标服务器上执行操作系统级别的初始化配置，满足 Kubernetes 部署的最低要求。

## 前置条件

- 所有目标节点已安装 Linux 操作系统（Ubuntu 20.04/22.04/24.04 或兼容发行版）
- 控制节点可通过 SSH 访问所有目标节点
- 具有 sudo 权限的用户（免密 sudo 推荐）
- Ansible 已安装（可选，用于批量执行）

## 执行流程

### Step 0: 收集节点信息

向用户确认以下信息：

1. **节点 IP 列表**：所有目标节点的 IP 地址
2. **SSH 用户名**：用于连接节点的用户名（默认从 `deploy/env-config.sh` 读取）
3. **磁盘设备名**：Longhorn 专用磁盘（如 `/dev/sdb`，可选）
4. **NTP 服务器**：时间同步服务器（默认 `ntp.aliyun.com`）

如果 `deploy/hosts` 文件已配置，直接使用。

### Step 1: 创建/更新 Ansible 清单

确保 `deploy/hosts` 文件存在且配置正确。参考 `deploy/hosts.template`：

```ini
[K8s]
192.168.220.128 ansible_connection=local
192.168.220.129
192.168.220.130

[K8s-other]
192.168.220.129
192.168.220.130

[K8s:vars]
ansible_user=<你的用户名>
ansible_become=true
```

### Step 2: 检查 SSH 连通性

```bash
# 加载共享配置
source deploy/env-config.sh

# 检查所有节点 SSH 可达
ansible -i deploy/hosts all -m ping
```

如果失败，需要配置 SSH 免密登录：
```bash
# 生成密钥（如果不存在）
[ ! -f ~/.ssh/id_ed25519 ] && ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519

# 分发公钥到所有节点
for ip in $(ansible -i deploy/hosts all --list-hosts | tr -d ' '); do
  ssh-copy-id -i ~/.ssh/id_ed25519.pub "${ANSIBLE_USER}@${ip}" 2>/dev/null || true
done
```

### Step 3: 系统基础配置

在所有节点上执行以下配置：

```bash
# 加载共享配置
source deploy/env-config.sh

# ── 3a. 关闭 swap ──
ansible -i deploy/hosts all -m shell -a "
  swapoff -a &&
  sed -i '/swap/d' /etc/fstab &&
  echo 'swap 已关闭'
" --become

# ── 3b. 配置内核参数 ──
ansible -i deploy/hosts all -m shell -a "
  cat > /etc/sysctl.d/99-k8s.conf <<EOF
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-arptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
net.ipv4.ip_nonlocal_bind           = 1
vm.overcommit_memory                = 1
vm.panic_on_oom                     = 0
fs.inotify.max_user_watches         = 1048576
fs.inotify.max_user_instances       = 8192
EOF
  modprobe br_netfilter &&
  sysctl --system &&
  echo '内核参数已配置'
" --become

# ── 3c. 加载内核模块（持久化） ──
ansible -i deploy/hosts all -m shell -a "
  cat > /etc/modules-load.d/k8s.conf <<EOF
br_netfilter
overlay
nf_conntrack
EOF
  modprobe overlay &&
  modprobe br_netfilter &&
  modprobe nf_conntrack &&
  echo '内核模块已加载'
" --become

# ── 3d. 配置时间同步 ──
ansible -i deploy/hosts all -m shell -a "
  apt-get install -y chrony &&
  sed -i 's/^pool.*/# &/' /etc/chrony/chrony.conf &&
  echo 'server ntp.aliyun.com iburst' >> /etc/chrony/chrony.conf &&
  systemctl enable --now chronyd &&
  chronyc sourceinfo &&
  timedatectl set-ntp true &&
  echo '时间同步已配置'
" --become
```

### Step 4: 安全配置

```bash
source deploy/env-config.sh

# ── 4a. 关闭防火墙 ──
# Ubuntu UFW
ansible -i deploy/hosts all -m shell -a "
  ufw disable 2>/dev/null || true &&
  iptables -F &&
  echo '防火墙已关闭'
" --become

# ── 4b. 配置免密 sudo（如果使用非 root 用户） ──
ansible -i deploy/hosts all -m shell -a "
  echo '${ANSIBLE_USER:-zcq} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/${ANSIBLE_USER:-zcq} &&
  chmod 440 /etc/sudoers.d/${ANSIBLE_USER:-zcq} &&
  echo '免密 sudo 已配置'
" --become

# ── 4c. 配置 SSH（可选优化） ──
ansible -i deploy/hosts all -m shell -a "
  sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config &&
  sed -i 's/^#*MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config &&
  systemctl reload sshd 2>/dev/null || systemctl reload ssh &&
  echo 'SSH 已加固'
" --become
```

### Step 5: 安装基础依赖

```bash
source deploy/env-config.sh

ansible -i deploy/hosts all -m shell -a "
  apt-get update &&
  apt-get install -y \
    curl wget git jq socat conntrack \
    ebtables ethtool ipvsadm nfs-common \
    open-iscsi &&

  systemctl enable --now iscsid &&
  systemctl enable --now open-iscsi &&
  echo '基础依赖已安装'
" --become
```

### Step 6: 验证初始化

在所有节点上验证配置是否生效：

```bash
source deploy/env-config.sh

echo "=== 验证结果 ==="

# swap 状态
echo "--- swap 状态（应为空）---"
ansible -i deploy/hosts all -m shell -a "swapon --show || echo 'swap 已关闭'" --become

# 内核参数
echo "--- 内核参数 ---"
ansible -i deploy/hosts all -m shell -a "sysctl net.bridge.bridge-nf-call-iptables net.ipv4.ip_forward" --become

# 时间同步
echo "--- 时间同步 ---"
ansible -i deploy/hosts all -m shell -a "timedatectl | grep -E 'Sync|NTP'" --become

# 防火墙
echo "--- 防火墙状态 ---"
ansible -i deploy/hosts all -m shell -a "ufw status 2>/dev/null || echo 'ufw 未安装'" --become

# 端口占用检查
echo "--- 关键端口检查 ---"
ansible -i deploy/hosts all -m shell -a "
  for port in 6443 2379 2380 10250 10259 10257 30000; do
    ss -tlnp | grep -q ':${port} ' && echo '端口 ${port}: 已占用 ⚠' || echo '端口 ${port}: 可用 ✓'
  done
" --become

# 硬件资源
echo "--- 硬件资源 ---"
ansible -i deploy/hosts all -m shell -a "
  echo \"CPU: \$(nproc) 核\"
  echo \"内存: \$(free -h | awk '/Mem:/{print \$2}')\"
  echo \"磁盘: \$(df -h / | tail -1 | awk '{print \$2 \" 总计, \" \$4 \" 可用\"}')\"
" --become

# KVM 支持（虚拟化部署需要）
echo "--- KVM 虚拟化支持 ---"
ansible -i deploy/hosts all -m shell -a "
  if [ -e /dev/kvm ]; then
    echo 'KVM: 可用 ✓'
    ls -la /dev/kvm
  else
    echo 'KVM: 不可用 ⚠（如需部署 VM 请启用硬件虚拟化）'
  fi
" --become
```

**验证通过标准**：
- ✅ swap 已关闭
- ✅ `bridge-nf-call-iptables = 1`，`ip_forward = 1`
- ✅ 时间同步已启用
- ✅ 防火墙已关闭
- ✅ 关键端口全部可用
- ✅ 每个节点至少 2 CPU / 4GB 内存（最低要求）

## 最低硬件要求

| 角色 | CPU | 内存 | 系统盘 | 数据盘（推荐） |
|------|-----|------|--------|--------------|
| 控制平面 + etcd | ≥ 4 核 | ≥ 8 GB | ≥ 40 GB | 可选 |
| 工作节点（容器） | ≥ 2 核 | ≥ 4 GB | ≥ 40 GB | 可选 |
| 工作节点（VM/KubeVirt） | ≥ 4 核 | ≥ 16 GB | ≥ 40 GB | ≥ 100 GB（Longhorn） |

## 注意事项

- 执行顺序很重要：先完成本 skill 再执行 kubekey-deploy-k8s
- 如果节点已执行过初始化，重复执行是安全的（幂等设计）
- SELinux 在 Ubuntu 上默认不启用，如在 CentOS/RHEL 上需额外 `setenforce 0`
- `nf_conntrack` 模块在某些内核版本中可能名为 `nf_conntrack_ipv4`，脚本已做兼容

## 后续步骤

操作系统初始化完成后，按以下顺序继续：

1. **部署 K8s 集群**：详见 `kubekey-deploy-k8s` skill
2. **部署 kube-vip**：详见 `kubevip-deploy` skill
3. **部署 CNI**：详见 `kubeovn-deploy` skill
