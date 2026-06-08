# VDI 离线 ISO 部署方案设计文档

## 概述

### 目标

构建一个一体化 Live ISO，实现在离线场景下（有局域网、无互联网）通过 TUI 菜单引导部署 VDI 集群。

### 目标用户

交付工程师（非技术人员），需要简单的操作界面完成集群部署。

### 核心特性

- 单一 ISO 介质，包含所有离线资源
- TUI 菜单引导，类似 Ubuntu Server 安装体验
- 支持 PXE 多节点部署
- 基于 Dapper 自动构建，可重复、可移植

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
│   ├── images/                    # 容器镜像 (OCI 格式)
│   │   ├── k8s/                   # K8s 核心镜像
│   │   ├── kube-ovn/              # Kube-OVN 镜像
│   │   ├── longhorn/              # Longhorn 镜像
│   │   ├── kubevirt/              # KubeVirt 镜像
│   │   └── kagent/                # kagent 镜像
│   ├── binaries/                  # 二进制工具
│   │   ├── kk                     # KubeKey
│   │   ├── kubectl
│   │   ├── helm
│   │   └── virtctl
│   ├── packages/                  # 系统依赖包
│   │   ├── deb/                   # Debian/Ubuntu 包
│   │   └── repo/                  # 本地 APT 仓库
│   └── vm/                        # VM 镜像
│       └── windows-*.qcow2
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
ISO 启动
    │
    ▼
TUI 菜单 1：选择模式
├── 1. 全新安装（安装 OS + 部署 VDI 集群）
├── 2. 仅部署 VDI 集群（已有 OS）
├── 3. 添加节点到现有集群
└── 4. PXE 服务
    │
    ▼
TUI 菜单 2：配置参数
├── 网络配置（IP、网关、DNS）
├── 集群配置（VIP、Pod/Service CIDR）
├── 节点角色（Master/Worker）
└── 存储配置（Longhorn 磁盘）
    │
    ▼
自动执行
├── OS 安装（如果选择模式 1）
├── 系统初始化（os-init）
├── 部署 K8s 集群（KubeKey）
├── 部署 Kube-OVN
├── 部署 Longhorn
├── 部署 KubeVirt
└── 部署 kagent
    │
    ▼
部署完成，显示集群信息
```

---

## TUI 安装器

### 技术选型

- **Python** 作为主逻辑语言
- **whiptail/dialog** 提供标准 TUI 组件（菜单、输入框、进度条）

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

1. 自动运行 os-init
2. 从 PXE Server 获取 join 命令
3. 执行 `kk join` 加入集群
4. 报告状态到 PXE Server

---

## 离线资源管理

### 资源清单格式

```yaml
apiVersion: v1
kind: OfflineManifest
metadata:
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
    binaries:
      - name: kubectl
        version: "v1.34.3"
        arch: "amd64"

  kube-ovn:
    version: "v1.17.0"
    images:
      - kubeovn/kube-ovn:v1.17.0

  longhorn:
    version: "v1.8.1"
    images:
      - longhornio/longhorn-manager:v1.8.1
      - longhornio/longhorn-engine:v1.8.1

  kubevirt:
    version: "v1.5.0"
    images:
      - quay.io/kubevirt/virt-operator:v1.5.0
      - quay.io/kubevirt/virt-api:v1.5.0
      - quay.io/kubevirt/virt-controller:v1.5.0
      - quay.io/kubevirt/virt-handler:v1.5.0

  kagent:
    version: "0.9.6"
    images:
      - ghcr.io/kagent-dev/kagent/controller:0.9.6
      - ghcr.io/kagent-dev/kagent/ui:0.9.6

packages:
  deb:
    - open-iscsi
    - nfs-common
    - conntrack
    - socat
    - ipvsadm
```

### 镜像导入机制

```bash
load_offline_images() {
  local component=$1
  local manifest="offline/manifest.yaml"

  # 从 manifest 读取镜像列表
  images=$(yq ".components.${component}.images[]" "$manifest")

  for image in $images; do
    echo "导入镜像: $image"
    skopeo copy "oci:offline/images/${component}/${image##*/}" "docker://${image}"
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
    python3-pip \
    whiptail \
    wget \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# 安装 skopeo
RUN . /etc/os-release && \
    echo "deb https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/unstable/xUbuntu_${VERSION_ID}/ /" > /etc/apt/sources.list.d/devel:kubic:libcontainers:unstable.list && \
    wget -nv https://download.opensuse.org/repositories/devel:/kubic:/libcontainers:/unstable/xUbuntu_${VERSION_ID}/Release.key -O- | apt-key add - && \
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

- **构建时**：从 VDI 仓库复制 `deploy/` 目录到 ISO
- **部署时**：TUI 调用 VDI 仓库的部署脚本，从离线包加载资源

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
| 单元测试 | TUI 组件、配置解析、离线包验证 | pytest |
| 集成测试 | 完整部署流程（3 节点 VM） | Shell 脚本 |
| CI 流水线 | ISO 构建、基础验证 | GitHub Actions |

### 验收测试清单

| 测试项 | 验收标准 |
|--------|----------|
| ISO 启动 | 能从 USB/光盘启动进入 Live 环境 |
| TUI 界面 | 所有菜单可正常操作，参数可输入 |
| OS 安装 | 自动完成 Ubuntu 安装，重启后可登录 |
| 离线资源 | 所有镜像可导入，二进制可执行 |
| K8s 部署 | 集群初始化成功，节点 Ready |
| 网络部署 | Kube-OVN 正常工作，Pod 可通信 |
| 存储部署 | Longhorn 正常工作，PV 可创建 |
| PXE 服务 | Worker 可通过 PXE 安装并加入集群 |

---

## 参考资源

- [Ubuntu Preseed 文档](https://ubuntu.com/server/docs/installing-ubuntu-server)
- [Dapper 项目](https://github.com/rancher/dapper)
- [PXE 网络安装指南](https://ubuntu.com/server/docs/install/netboot-amd64)
- [VDI 仓库部署脚本](../../deploy/)
