# VDI 离线 ISO 部署方案设计文档

## 概述

### 目标

构建一个一体化 Live ISO，实现在离线场景下（有局域网、无互联网）通过 TUI 菜单引导部署 VDI 集群。

### 目标用户

交付工程师（非技术人员），需要简单的操作界面完成集群部署。

### 核心特性

- 单一 ISO 介质，包含所有离线资源
- TUI 菜单引导，类似 Ubuntu Server 安装体验
- 支持 PXE 多节点批量部署
- 基于 Dapper 自动构建，可重复、可移植

### 关键约束

- **目标架构**：仅支持 amd64（x86_64），暂不考虑 arm64
- **目标 OS**：Ubuntu 22.04 LTS 作为 Live 系统基础和安装目标
- **ISO 容量**：不含 Windows VM 镜像时控制在 8GB 以内；Windows VM 镜像作为可选附加包，不打包进主 ISO，而是通过外置 U 盘或网络共享在部署时导入
- **网络环境**：有局域网（千兆以上），完全无互联网
- **最小部署规模**：1 个 Master 节点（单节点可运行全部组件）

---

## 整体架构

### ISO 结构

```
vdi-offline-iso/
├── boot/                          # 启动引导
│   ├── grub/                      # GRUB 配置
│   └── efi/                       # UEFI 启动
├── casper/                        # Live 系统
│   ├── filesystem.squashfs        # 压缩的根文件系统
│   └── vmlinuz / initrd           # 内核和 initramfs
├── offline/                       # 离线资源包
│   ├── images/                    # 容器镜像 (OCI 目录格式)
│   │   ├── k8s/                   # K8s 核心镜像
│   │   ├── kube-ovn/              # Kube-OVN 镜像
│   │   ├── longhorn/              # Longhorn 镜像
│   │   ├── kubevirt/              # KubeVirt 镜像
│   │   └── kagent/                # kagent 镜像
│   ├── charts/                    # Helm Chart 包
│   │   ├── kube-ovn/              # Kube-OVN 本地 chart（来自 deploy/kube-ovn/chart/）
│   │   ├── longhorn/              # Longhorn chart（预下载）
│   │   └── kagent/                # kagent chart（预构建）
│   ├── binaries/                  # 二进制工具
│   │   ├── kk                     # KubeKey
│   │   ├── kubectl
│   │   ├── helm
│   │   └── virtctl
│   ├── packages/                  # 系统依赖包
│   │   ├── deb/                   # Debian/Ubuntu 包
│   │   └── repo/                  # 本地 APT 仓库元数据
│   └── k8s-manifests/             # KubeVirt/CDI 等 K8s 原生 YAML
│       ├── kubevirt-cr.yaml
│       └── cdi-cr.yaml
├── scripts/                       # 部署脚本
│   ├── tui-installer              # TUI 安装器主程序
│   ├── preseed/                   # 自动化安装配置
│   └── deploy/                    # VDI 部署脚本（来自 VDI 仓库）
└── metadata/                      # 元数据
    ├── manifest.yaml              # 清单（版本、校验和）
    └── release-notes.md
```

### 部署流程

```
ISO 启动进入 Live 环境
    │
    ▼
TUI 菜单 1：选择部署模式
├── 1. 全新安装（在本机安装 Ubuntu OS + 部署 VDI 集群为 Master）
├── 2. 追加部署（本机已有 OS，仅部署 VDI 集群组件）
├── 3. 添加节点（本机作为 Worker 加入已有集群）
└── 4. PXE 服务（将本机配置为 PXE Server，供其他节点网络安装）
    │
    ▼
TUI 菜单 2：配置参数（根据模式动态显示）
├── 网络配置（IP、网关、DNS、主机名）
├── 集群配置（VIP、Pod/Service CIDR）          ← 模式 1/2
├── Join 配置（Master IP、Join Token）          ← 模式 3
├── PXE 配置（DHCP 网段、Worker 数量）          ← 模式 4
└── 存储配置（Longhorn 磁盘路径）               ← 模式 1/2
    │
    ▼
确认配置 → 自动执行部署
├── OS 安装到本地磁盘（模式 1，使用 preseed 自动化）
├── 系统初始化（os-init：swap/内核/防火墙/依赖）
├── 离线资源加载（导入镜像到 containerd、配置本地 APT 源）
├── 部署 K8s 集群（KubeKey）
├── 部署 kube-vip（API Server HA）
├── 部署 Kube-OVN（本地 Helm chart）
├── 部署 Longhorn（离线 Helm chart）
├── 部署 KubeVirt + CDI（离线 manifest）
└── 部署 kagent（离线 Helm chart + VDI Agent CRD）
    │
    ▼
部署完成 → 显示集群信息和下一步操作
（Master 节点：显示 VIP、kubectl 命令、Worker join 命令）
（Worker 节点：显示加入成功信息）
```

---

## TUI 安装器

### 技术选型

- **Python 3** 作为主逻辑语言（Ubuntu 22.04 自带，无额外依赖）
- **whiptail** 提供 TUI 组件（通过 subprocess 调用，Ubuntu 预装）
- 选择 whiptail 而非 Python TUI 框架（如 curses/urwid）的理由：
  - 无需额外 pip 依赖，Live 环境零安装
  - 外观与 Ubuntu Server 安装器一致
  - Shell 调试方便（可独立运行 whiptail 命令测试界面）

### 主界面

```
┌─────────────────────────────────────────────────────────────┐
│  VDI 集群离线部署工具 v1.0                                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  请选择部署模式：                                             │
│                                                              │
│  1. 全新安装 - 安装 Ubuntu OS 并部署 VDI 集群                 │
│  2. 追加部署 - 在已有 OS 上部署 VDI 集群                      │
│  3. 添加节点 - 向现有集群添加 Worker 节点                     │
│  4. PXE 服务 - 启动 PXE 服务器供其他节点网络安装              │
│                                                              │
│                    [ 确定 ]  [ 取消 ]                        │
└─────────────────────────────────────────────────────────────┘
```

### 参数配置界面

**网络配置**：
- 本机 IP 地址
- 子网掩码
- 网关地址
- DNS 服务器
- 主机名

**集群配置**：
- 节点角色（Master/Worker）
- VIP 地址
- Pod CIDR
- Service CIDR
- K8s 版本

### 进度显示

```
┌─────────────────────────────────────────────────────────────┐
│  部署进度                                                    │
├─────────────────────────────────────────────────────────────┤
│  [████████████████████░░░░░░░░░░] 65%  正在部署 KubeVirt     │
│                                                              │
│  ✓ 系统初始化完成                                            │
│  ✓ K8s 集群部署完成                                          │
│  ✓ Kube-OVN 部署完成                                         │
│  ✓ Longhorn 部署完成                                         │
│  ● KubeVirt 部署中...                                        │
│  ○ kagent 部署                                               │
│                                                              │
│  日志: /var/log/vdi-deploy.log                               │
└─────────────────────────────────────────────────────────────┘
```

---

## PXE 服务

### 架构

当选择"PXE 服务"模式时，当前节点自动配置为：

```
PXE Server 节点
├── DHCP Server (dnsmasq) - 分发 IP + TFTP 地址
├── TFTP Server - 提供引导文件（pxelinux, kernel, initrd）
├── HTTP Server (nginx/python) - 提供 ISO 内容（preseed, 离线包）
└── 配置生成器 - 根据 TUI 输入生成 preseed/cloud-init
```

### PXE 引导流程

```
Worker 节点                     PXE Server
    │                               │
    │  1. DHCP Discover             │
    │──────────────────────────────▶│
    │  2. DHCP Offer (IP + TFTP)    │
    │◀──────────────────────────────│
    │  3. TFTP: pxelinux.0          │
    │──────────────────────────────▶│
    │  4. TFTP: kernel + initrd     │
    │──────────────────────────────▶│
    │  5. HTTP: preseed.cfg          │
    │──────────────────────────────▶│
    │  6. 自动安装 OS               │
    │  7. 部署 VDI 组件             │
```

### Worker 自动加入集群

1. 自动运行 os-init（内核参数、swap、依赖安装）
2. 从 PXE Server HTTP 接口获取：`env-config.sh` + `join-command.sh`
3. 执行 `kk join` 加入集群（join token 由 PXE Server 从 Master 芀预取）
4. 导入离线镜像到 containerd
5. 部署 Kube-OVN CNI、Longhorn 等组件（仅 Worker 角色需要的 DaemonSet 自动调度）
6. 通过 HTTP 回报状态到 PXE Server

### PXE 仅用于 Worker 节点

- **Master 节点**必须通过模式 1（全新安装）或模式 2（追加部署）手动部署，确保对集群初始化的完全控制
- PXE Server 自动从已部署的 Master 获取 `kubeadm token create --print-join-command` 生成 join 脚本
- PXE 流程中 Worker 不参与 etcd 和控制平面选举，简化自动化风险

---

## 离线资源管理

### 资源清单格式

```yaml
# 非标准 K8s 资源，仅为离线包清单的结构化格式
name: vdi-offline-pack
version: "1.0.0"
buildDate: "2026-06-08"

components:
  kubernetes:
    version: "v1.34.3"
    images:
      - registry.k8s.io/kube-apiserver:v1.34.3
      - registry.k8s.io/kube-controller-manager:v1.34.3
      - registry.k8s.io/kube-scheduler:v1.34.3
      - registry.k8s.io/kube-proxy:v1.34.3
      - registry.k8s.io/etcd:3.5.21-0
      - registry.k8s.io/coredns/coredns:v1.12.1
      - registry.k8s.io/pause:3.10
    binaries:
      - name: kk
        version: "v4.0.4"
        url: "https://github.com/kubesphere/kubekey/releases/download/v4.0.4/kubekey-v4.0.4-linux-amd64.tar.gz"
      - name: kubectl
        version: "v1.34.3"
        url: "https://dl.k8s.io/release/v1.34.3/bin/linux/amd64/kubectl"
      - name: helm
        version: "v3.18.5"
        url: "https://get.helm.sh/helm-v3.18.5-linux-amd64.tar.gz"
      - name: virtctl
        version: "v1.5.0"
        url: "https://github.com/kubevirt/kubevirt/releases/download/v1.5.0/virtctl-v1.5.0-linux-amd64"

  kube-vip:
    version: "v0.7.2"
    images:
      - ghcr.io/kube-vip/kube-vip:v0.7.2

  kube-ovn:
    version: "v1.17.0"
    images:
      - docker.io/kubeovn/kube-ovn:v1.17.0
      - docker.io/kubeovn/vpc-nat-gateway:v1.17.0
    charts:
      - name: kube-ovn
        path: charts/kube-ovn/

  longhorn:
    version: "v1.8.1"
    images:
      - longhornio/longhorn-manager:v1.8.1
      - longhornio/longhorn-engine:v1.8.1
      - longhornio/longhorn-ui:v1.8.1
      - longhornio/longhorn-instance-manager:v1.8.1
      - longhornio/support-bundle-kit:v0.0.52
      - longhornio/csi-attacher:v4.8.0
      - longhornio/csi-provisioner:v5.2.0
      - longhornio/csi-resizer:v1.13.1
      - longhornio/csi-snapshotter:v8.2.0
      - longhornio/livenessprobe:v2.15.0
      - longhornio/csi-node-driver-registrar:v2.13.0
    charts:
      - name: longhorn
        path: charts/longhorn/

  kubevirt:
    version: "v1.5.0"
    images:
      - quay.io/kubevirt/virt-operator:v1.5.0
      - quay.io/kubevirt/virt-api:v1.5.0
      - quay.io/kubevirt/virt-controller:v1.5.0
      - quay.io/kubevirt/virt-handler:v1.5.0
      - quay.io/kubevirt/virt-launcher:v1.5.0
    manifests:
      - name: kubevirt-operator
        path: k8s-manifests/kubevirt-operator.yaml
      - name: kubevirt-cr
        path: k8s-manifests/kubevirt-cr.yaml

  cdi:
    version: "v1.61.0"
    images:
      - quay.io/cdi/cdi-operator:v1.61.0
      - quay.io/cdi/cdi-controller:v1.61.0
      - quay.io/cdi/cdi-importer:v1.61.0
      - quay.io/cdi/cdi-cloner:v1.61.0
      - quay.io/cdi/cdi-apiserver:v1.61.0
      - quay.io/cdi/cdi-uploadproxy:v1.61.0
      - quay.io/cdi/cdi-uploadserver:v1.61.0
    manifests:
      - name: cdi-operator
        path: k8s-manifests/cdi-operator.yaml
      - name: cdi-cr
        path: k8s-manifests/cdi-cr.yaml

  kagent:
    version: "0.9.6"
    images:
      - ghcr.io/kagent-dev/kagent/controller:0.9.6
      - ghcr.io/kagent-dev/kagent/ui:0.9.6
      - docker.io/library/postgres:18.3-alpine
    charts:
      - name: kagent
        path: charts/kagent/

packages:
  deb:
    - open-iscsi
    - nfs-common
    - conntrack
    - socat
    - ipvsadm
    - ebtables
    - ethtool
    - iptables
    - jq
    - curl
    - skopeo
    - yq
```

### 镜像导入机制

离线镜像以 OCI 目录格式存储在 ISO 中，部署时通过 `ctr` 导入到 containerd：

```bash
load_offline_images() {
  local component=$1
  local manifest="/cdrom/offline/manifest.yaml"

  # 从 manifest 读取该组件的镜像列表
  images=$(yq ".components.${component}.images[]" "$manifest")

  for image in $images; do
    local image_dir="/cdrom/offline/images/${component}"
    echo "导入镜像: $image"
    # OCI 目录 → containerd image store
    ctr -n k8s.io images import "${image_dir}/$(echo "$image" | sed 's|[/:]|_|g').tar" || \
    skopeo copy "oci:${image_dir}" "docker://${image}"
  done
}
```

### Helm Chart 离线安装

```bash
install_offline_chart() {
  local component=$1
  local release_name=$2
  local namespace=$3
  local values_file=$4

  helm upgrade --install "$release_name" "/cdrom/offline/charts/${component}/" \
    --namespace "$namespace" \
    --create-namespace \
    -f "$values_file"
}
```

### K8s Manifest 离线应用

```bash
apply_offline_manifest() {
  local component=$1
  local manifest_dir="/cdrom/offline/k8s-manifests"

  for manifest in $(yq ".components.${component}.manifests[].path" "/cdrom/offline/manifest.yaml"); do
    kubectl apply -f "${manifest_dir}/${manifest}"
  done
}
```

### 本地 APT 仓库

```bash
setup_local_repo() {
  cd offline/packages/deb
  dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz
  echo "deb [trusted=yes] file:///cdrom/offline/packages/deb ./" > /etc/apt/sources.list.d/offline.list
  apt-get update
}
```

### 校验和验证

```bash
# 构建时生成
find offline/ -type f -exec sha256sum {} \; > offline/checksums.sha256

# 部署时验证
verify_offline_pack() {
  if sha256sum -c offline/checksums.sha256 --quiet; then
    echo "✓ 离线包验证通过"
  else
    echo "✗ 离线包损坏，请重新获取 ISO" >&2
    exit 1
  fi
}
```

---

## 构建系统

### Dapper 构建架构

```
vdi-iso-builder/
├── Dockerfile.dapper              # Dapper 构建环境
│   ├── 基础镜像: ubuntu:22.04
│   ├── 构建工具: xorriso, squashfs-tools, debootstrap
│   ├── Python 环境: python3, whiptail
│   └── 离线工具: skopeo, yq, wget
│
├── scripts/
│   ├── build-iso                  # 主构建脚本
│   ├── download-images            # 下载容器镜像
│   ├── download-packages          # 下载系统包
│   ├── setup-pxe                  # 配置 PXE 环境
│   └── create-live                # 创建 Live 系统
│
└── configs/
    ├── grub.cfg                   # GRUB 配置
    ├── preseed.cfg                # Ubuntu 预配置
    └── tui/                       # TUI 界面配置
```

### Dockerfile.dapper

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    xorriso \
    squashfs-tools \
    debootstrap \
    grub-pc-bin \
    grub-efi-amd64-bin \
    mtools \
    dosfstools \
    python3 \
    whiptail \
    wget \
    curl \
    jq \
    gpg \
    && rm -rf /var/lib/apt/lists/*

# 安装 skopeo（使用 signed-by 替代废弃的 apt-key）
RUN . /etc/os-release && \
    wget -nv https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/unstable/xUbuntu_${VERSION_ID}/Release.key -O /usr/share/keyrings/kubic.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/kubic.gpg] https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/unstable/xUbuntu_${VERSION_ID}/ /" > /etc/apt/sources.list.d/kubic.list && \
    apt-get update && apt-get install -y skopeo

# 安装 yq
RUN wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && \
    chmod +x /usr/local/bin/yq

ENV DAPPER_SOURCE /workspace
ENV DAPPER_OUTPUT dist
WORKDIR ${DAPPER_SOURCE}

ENTRYPOINT ["./scripts/entry"]
```

### 构建流程

```bash
# 构建 Dapper 镜像
docker build -f Dockerfile.dapper -t vdi-iso-builder .

# 使用 Dapper 执行构建
dapper ./scripts/build-iso

# 构建产物
dist/
├── vdi-offline-v1.0.0.iso
├── vdi-offline-v1.0.0.iso.sha256
└── vdi-offline-v1.0.0.iso.manifest
```

---

## 项目结构

```
vdi-iso-builder/
├── CLAUDE.md                      # AI 开发指南
├── README.md                      # 项目说明
├── Makefile                       # 构建入口
├── Dockerfile.dapper              # Dapper 构建环境
│
├── scripts/                       # 构建和部署脚本
│   ├── build-iso
│   ├── download-resources
│   ├── create-live
│   ├── integrate-offline
│   └── generate-manifest
│
├── tui/                           # TUI 安装器
│   ├── installer.py               # 主程序
│   ├── screens/                   # 各界面
│   ├── backend/                   # 后端逻辑
│   └── utils/                     # 工具函数
│
├── pxe/                           # PXE 服务
│   ├── dnsmasq.conf
│   ├── pxelinux.cfg/
│   └── start-pxe.sh
│
├── configs/                       # 配置文件模板
│   ├── grub.cfg
│   ├── preseed.cfg
│   ├── cloud-init.yaml
│   └── env-config.sh
│
├── offline/                       # 离线资源（构建时生成）
│   ├── manifest.yaml
│   ├── images/
│   ├── binaries/
│   └── packages/
│
└── tests/                         # 测试
    ├── test-tui.sh
    └── test-pxe.sh
```

### 与 VDI 仓库的关系

- **构建时**：从 VDI 仓库复制 `deploy/` 目录到 ISO（排除 gitignore 文件：hosts、inventory.yaml）
- **部署时**：TUI 调用 `deploy/skills/` 中的部署脚本，从 ISO 离线包加载资源
- **vdi-iso-builder 仓库位置**：独立仓库（`github.com/<org>/vdi-iso-builder`），通过 Makefile 引用 VDI 仓库作为子目录或 git submodule

### TUI 参数到 env-config.sh 的映射

TUI 收集的用户输入直接写入 `env-config.sh`，替代手动编辑：

| TUI 配置项 | env-config.sh 变量 | 默认值 |
|------------|-------------------|--------|
| 本机 IP | — （用于生成 hosts/inventory） | DHCP 自动获取 |
| 主机名 | — （写入 /etc/hostname） | vdi-node-01 |
| VIP 地址 | `VIP` | 192.168.220.100 |
| VIP 网卡 | `VIP_INTERFACE` | ens160 |
| Pod CIDR | `POD_CIDR` | 10.16.0.0/16 |
| Service CIDR | `SVC_CIDR` | 10.96.0.0/12 |
| K8s 版本 | `K8S_VERSION` | v1.34.3 |
| Longhorn 磁盘 | `LONGHORN_DISK` | /dev/sdb |
| Windows VM 镜像路径 | — （可选，外置导入） | 无 |

**关键约定**：TUI 生成的 `env-config.sh` 遵循与 VDI 仓库完全相同的变量名和格式，确保 `deploy/skills/` 中的脚本无需修改即可在离线环境中运行。

### 离线环境适配

现有部署脚本依赖在线下载的位置需要改为本地路径：

| 脚本 | 原始行为 | 离线适配 |
|------|---------|---------|
| `download-kk.sh` | 从 GitHub release 下载 kk | 使用 `/cdrom/offline/binaries/kk` |
| `longhorn/deploy.sh` | `helm repo add` 在线添加仓库 | `helm install` 使用本地 chart `/cdrom/offline/charts/longhorn/` |
| `kubevirt/deploy.sh` | `kubectl apply -f https://...` 在线拉取 | `kubectl apply -f /cdrom/offline/k8s-manifests/` |
| `kube-ovn/deploy.sh` | Helm 安装（chart 已本地化） | chart 路径改为 `/cdrom/offline/charts/kube-ovn/` |
| 各 Skill Step 0 | `curl -LO` 下载 kubectl/helm | 直接使用 `/cdrom/offline/binaries/` 中的二进制 |

**实现方式**：在 `env-config.sh` 中增加离线路径变量：

```bash
# 离线环境变量（ISO 挂载后自动设置）
OFFLINE_BASE="/cdrom/offline"
OFFLINE_BINARIES="${OFFLINE_BASE}/binaries"
OFFLINE_IMAGES="${OFFLINE_BASE}/images"
OFFLINE_CHARTS="${OFFLINE_BASE}/charts"
OFFLINE_MANIFESTS="${OFFLINE_BASE}/k8s-manifests"
OFFLINE_PACKAGES="${OFFLINE_BASE}/packages/deb"
```

---

## 错误处理

### 分层错误处理

```python
class DeployError(Exception):
    def __init__(self, message, solution=None, log_file=None):
        self.message = message
        self.solution = solution
        self.log_file = log_file
```

### TUI 错误界面

```
┌─────────────────────────────────────────────────────────────┐
│  ✗ 部署失败                                                  │
├─────────────────────────────────────────────────────────────┤
│  错误信息: 无法连接到节点 192.168.220.129                     │
│                                                              │
│  可能原因:                                                    │
│  1. 节点未开机或网络不通                                      │
│  2. SSH 服务未启动                                            │
│  3. 防火墙阻止连接                                            │
│                                                              │
│  建议操作:                                                    │
│  1. ping 192.168.220.129 检查网络                            │
│  2. 检查 SSH 配置和密钥                                       │
│  3. 查看详细日志: /var/log/vdi-deploy/k8s.log                │
│                                                              │
│            [ 重试 ]  [ 跳过 ]  [ 查看日志 ]  [ 退出 ]        │
└─────────────────────────────────────────────────────────────┘
```

### 日志系统

```
/var/log/vdi-deploy/
├── installer.log          # TUI 安装器日志
├── os-install.log         # OS 安装日志
├── k8s-deploy.log         # K8s 部署日志
├── network-deploy.log     # 网络部署日志
├── storage-deploy.log     # 存储部署日志
└── kubevirt-deploy.log    # KubeVirt 部署日志
```

---

## 测试策略

### 测试层次

| 层次 | 测试内容 | 工具 |
|------|----------|------|
| 单元测试 | TUI 组件、配置生成、env-config.sh 映射、离线包校验 | pytest |
| 集成测试 | 完整部署流程（VM 环境：1 Master + 2 Worker） | Shell 脚本 + libvirt |
| CI 流水线 | ISO 构建、manifest 校验、squashfs 完整性 | GitHub Actions |
| 冒烟测试 | ISO 启动 → TUI → 单节点全链路部署 | 手动 |

### 验收测试清单

| 测试项 | 验收标准 |
|--------|----------|
| ISO 启动 | 能从 USB/光盘启动进入 Live 环境，TUI 自动启动 |
| TUI 界面 | 所有 4 种模式的菜单可正常操作，参数可输入和校验 |
| OS 安装 | 模式 1 自动完成 Ubuntu 安装到本地磁盘，重启后可登录 |
| 离线资源 | 所有镜像可导入 containerd，二进制可执行，APT 源可用 |
| 单节点部署 | 模式 2 在已有 OS 上完成全部 6 步部署链路 |
| K8s 集群 | 集群初始化成功，节点 Ready，kube-vip VIP 可访问 |
| Kube-OVN | Pod 可跨节点通信，DNS 解析正常 |
| Longhorn | PV 可动态创建，副本调度正常 |
| KubeVirt | VM 可启动并获取 IP，virtctl console 可连接 |
| kagent | Agent CRD 创建成功，controller 运行正常 |
| PXE 服务 | Worker 通过 PXE 完成网络安装并自动加入集群 |
| 错误恢复 | 部署失败时 TUI 显示可操作的错误信息和重试选项 |
| ISO 大小 | 主 ISO（不含 Windows VM 镜像）< 8GB |

---

## 参考资源

- [Ubuntu Preseed 文档](https://ubuntu.com/server/docs/installing-ubuntu-server)
- [Dapper 项目](https://github.com/rancher/dapper)
- [PXE 网络安装指南](https://ubuntu.com/server/docs/install/netboot-amd64)
- [VDI 仓库部署脚本](../../deploy/)
