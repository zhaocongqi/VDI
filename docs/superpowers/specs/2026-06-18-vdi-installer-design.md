# VDI 离线 ISO 构建系统架构重设计

> 日期：2026-06-18
> 状态：设计中
> 方案：Fork harvester-installer + 改造为 VDI 组件栈

## 1. 背景与动机

当前 `iso-builder/` 的架构存在根本性问题：

- **构建系统碎片化**：Shell 脚本 + live-build + debootstrap，缺乏统一的构建框架
- **安装器技术债务**：Python Textual TUI 与 Harvester 的 Go + gocui 架构脱节，无法复用
- **离线资源管理粗糙**：per-image tar.zst 平铺，缺乏 metadata 索引和增量更新能力
- **版本管理分散**：版本号硬编码在 manifest.yaml 中，缺乏独立的版本脚本和 ldflags 注入机制
- **ISO 构建工具链落后**：手动拼装 xorriso 参数，不如 elemental 成熟可靠

**决策**：Fork harvester-installer，保留其经过大规模生产验证的架构，替换 OS 基础和组件栈。

## 2. 关键决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| OS 基础 | Ubuntu 22.04 + elemental 工具链 | 保持 Ubuntu 生态兼容性，引入 elemental ISO 构建能力 |
| 安装器语言 | Go + gocui | 与 Harvester 代码复用度最高，单二进制部署 |
| 版本管理 | 独立 version-* 脚本 + ldflags 注入 | 每个组件版本独立管理，构建时注入 Go 二进制 |
| Bundle 架构 | Harvester bundle 模式（metadata.yaml + docker save + zstd） | 支持增量更新、历史版本归档、标准化索引 |
| Docker 镜像 | 三镜像架构（vdi-os、vdi-installer、vdi-cluster-repo） | 支持 ISO 构建、PXE 引导、网络安装 |
| 配置校验 | Go 强类型配置结构体 + mergo 合并 | 类型安全、多源配置合并、深度拷贝 |

## 3. 整体架构

### 3.1 目录结构

```
vdi-installer/
├── main.go                          # CLI 入口（安装器 + generate-network-config）
├── Makefile                         # Dapper 模式
├── Dockerfile.dapper                # Ubuntu 22.04 + elemental + Go + xorriso + helm
│
├── package/
│   ├── vdi-os/
│   │   ├── Dockerfile               # 基于 Ubuntu 22.04 的 OS 镜像
│   │   ├── manifest.yaml            # iso.label = "VDI_LIVE"
│   │   ├── files/                   # OS 定制文件
│   │   └── templates/               # bootstrap YAML 模板
│   ├── vdi-installer/
│   │   └── Dockerfile               # 仅包含 installer 二进制
│   └── vdi-cluster-repo/
│       └── Dockerfile               # Helm Chart 仓库（nginx + charts）
│
├── pkg/
│   ├── config/
│   │   ├── config.go                # VDIConfig 结构体
│   │   ├── constants.go             # 版本常量（ldflags 注入）
│   │   ├── read.go                  # 配置读取（JSON/YAML/kernel cmdline）
│   │   ├── write.go                 # 配置写入
│   │   ├── schemas.go               # JSON Schema 校验
│   │   ├── templates.go             # Go template 渲染
│   │   └── cos.go                   # cOS/elemental OS 配置
│   ├── console/
│   │   ├── console.go               # gocui 主循环
│   │   ├── install_panels.go        # 安装流程面板
│   │   ├── dashboard_panels.go      # 安装完成 dashboard
│   │   ├── validator.go             # 输入校验
│   │   ├── network.go               # 网络接口检测
│   │   ├── vip.go                   # VIP 配置
│   │   └── webhooks.go              # 安装事件 webhook
│   ├── preflight/
│   │   └── checks.go                # 预检（网络/磁盘/CPU/内存）
│   ├── util/
│   │   ├── disk.go                  # 磁盘检测
│   │   ├── crypt.go                 # 密码哈希
│   │   ├── os.go                    # OS 工具函数
│   │   └── cmdline.go               # kernel cmdline 解析
│   ├── widgets/                     # gocui 自定义控件
│   └── version/
│       └── version.go               # 版本信息
│
├── scripts/
│   ├── entry                        # Dapper 入口
│   ├── default                      # 默认目标
│   ├── build                        # 编译 Go 安装器
│   ├── build-bundle                 # 下载离线资源
│   ├── package-vdi-os               # 构建 OS 镜像 + ISO
│   ├── package-vdi-installer        # 构建 installer 镜像
│   ├── package-vdi-repo             # 构建 cluster-repo 镜像
│   ├── validate                     # golangci-lint
│   ├── test                         # go test
│   ├── version                      # installer 版本
│   ├── version-kubernetes           # K8s 版本
│   ├── version-kubevirt             # KubeVirt 版本
│   ├── version-longhorn             # Longhorn 版本
│   ├── version-kubeovn              # Kube-OVN 版本
│   ├── version-kagent               # kagent 版本
│   ├── ci                           # CI 入口
│   └── lib/
│       ├── image                    # 镜像拉取/保存/元数据
│       ├── iso                      # ISO 打包
│       └── http                     # HTTP 下载
│
├── images/
│   ├── allow.yaml                   # 允许的镜像仓库
│   ├── cache.yaml                   # 镜像缓存策略
│   └── *.txt                        # 各组件镜像列表
│
└── ci/
    └── terraform/                   # CI 自动化测试
```

### 3.2 与 Harvester 的对比

| 维度 | Harvester 原版 | VDI 改造后 |
|------|---------------|-----------|
| OS 基础 | SLE Micro (rancher/harvester-os) | Ubuntu 22.04 (rancher/vdi-os) |
| 组件栈 | RKE2 + Rancher + Harvester Chart | KubeKey + Kube-OVN + Longhorn + KubeVirt + kagent |
| 安装模式 | 创建/加入 Harvester 集群 | 首节点/管理节点/工作节点 |
| 配置结构体 | HarvesterConfig | VDIConfig |
| 版本脚本 | version-harvester + version-rancher + version-rke2 | version-kubernetes + version-kubevirt + ... |
| addon 系统 | 外部 addons 仓库 | 暂不需要，组件直接内嵌 |
| initrd 生成 | dracut | update-initramfs |

## 4. 构建系统详细设计

### 4.1 Dapper 构建流程

```
make <target>  →  .dapper <target>  →  docker build Dockerfile.dapper  →  docker run scripts/<target>
```

**Makefile**（从 Harvester 简化）：

```makefile
TARGETS := $(shell ls scripts)

.dapper:
    @curl -sL https://releases.rancher.com/dapper/v0.6.0/dapper-$(uname -s)-$(uname -m) > .dapper
    @chmod +x .dapper

$(TARGETS): .dapper
    ./.dapper $@

.DEFAULT_GOAL := default
.PHONY: $(TARGETS)
```

**Dockerfile.dapper** 关键变化：
- 基础镜像：`registry.suse.com/bci/golang:1.26` → `golang:1.26-bookworm`
- 包管理器：`zypper` → `apt-get`
- 保留：elemental、xorriso、squashfs-tools、mtools、dosfstools、helm、yq、golangci-lint
- 去除：qemu-x86（仅 Harvester QCOW 构建需要）

**DAPPER_ENV**：

```bash
ENV DAPPER_ENV REPO TAG DRONE_TAG DRONE_BRANCH ARCH \
    KUBE_VERSION KUBEVIRT_VERSION LONGHORN_VERSION KUBEOVN_VERSION KAGENT_VERSION \
    USE_LOCAL_IMAGES DISABLE_BUILD_NET_INSTALL_ISO
```

### 4.2 scripts/build（编译安装器）

```
1. source scripts/version-kubernetes
2. source scripts/version-kubevirt
3. source scripts/version-longhorn
4. source scripts/version-kubeovn
5. source scripts/version-kagent
6. source scripts/version
7. 构建 LINKFLAGS（-X 注入版本号）
8. CGO_ENABLED=0 go build -ldflags "$LINKFLAGS" -o bin/vdi-installer .
9. install bin/vdi-installer → package/vdi-os/files/usr/bin/
10. install bin/vdi-installer → package/vdi-installer/
```

LINKFLAGS 注入的版本变量：

```go
// pkg/config/constants.go
var (
    KubernetesVersion string // -X ...config.KubernetesVersion=$KUBE_VERSION
    KubevirtVersion   string // -X ...config.KubevirtVersion=$KUBEVIRT_VERSION
    LonghornVersion   string // -X ...config.LonghornVersion=$LONGHORN_VERSION
    KubeovnVersion    string // -X ...config.KubeovnVersion=$KUBEOVN_VERSION
    KagentVersion     string // -X ...config.KagentVersion=$KAGENT_VERSION
)
```

### 4.3 scripts/build-bundle（离线资源下载）

**组件替换映射**：

| Harvester 原版 | VDI 改造后 |
|----------------|-----------|
| RKE2 images | KubeKey + K8s images |
| Rancher images | 去除 |
| Harvester chart + images | KubeVirt manifests + images |
| Longhorn chart + images | 保留 |
| Monitoring/Logging charts | 去除 |
| KubeOVN operator chart | Kube-OVN chart + images |
| VM-import/PCI-devices/Seeder | kagent chart + images |
| Descheduler | 去除 |

**Bundle 目录结构**：

```
package/vdi-os/iso/bundle/
├── metadata.yaml
├── vdi/
│   ├── images/*.tar.zst
│   └── images-lists/*.txt
└── charts/
    ├── longhorn-v1.8.1.tgz
    ├── kube-ovn-v1.17.0.tgz
    ├── kagent-0.9.6.tgz
    └── index.yaml
```

**metadata.yaml 格式**：

```yaml
images:
  common: []  # 跨组件共享镜像（如 pause、coredns 等由多个组件依赖的基础镜像）
  kubernetes:
    - list: vdi/images-lists/kubernetes-images-v1.34.3.txt
      archive: vdi/images/kubernetes-images-v1.34.3.tar.zst
  kubevirt:
    - list: vdi/images-lists/kubevirt-images-v1.5.0.txt
      archive: vdi/images/kubevirt-images-v1.5.0.tar.zst
  longhorn:
    - list: vdi/images-lists/longhorn-images-v1.8.1.txt
      archive: vdi/images/longhorn-images-v1.8.1.tar.zst
  kubeovn:
    - list: vdi/images-lists/kubeovn-images-v1.17.0.txt
      archive: vdi/images/kubeovn-images-v1.17.0.tar.zst
  kagent:
    - list: vdi/images-lists/kagent-images-0.9.6.txt
      archive: vdi/images/kagent-images-0.9.6.tar.zst
```

镜像管理函数复用 Harvester 的 `scripts/lib/image`：
- `normalize_image()` — 镜像名标准化
- `save_image_list()` — 从 allow.yaml 过滤镜像
- `pull_images()` — 拉取镜像（支持 USE_LOCAL_IMAGES 缓存）
- `save_image()` — docker save → zstd 压缩 → 写入 metadata.yaml
- `add_image_list_to_metadata()` — 追加镜像条目到 bundle metadata

### 4.4 scripts/package-vdi-os（构建 OS 镜像 + ISO）

```
1. source 所有 version-* 脚本
2. 生成 vdi-release.yaml（版本清单）
3. docker build → rancher/vdi-os:$VERSION
4. 从容器提取 kernel/initrd → dist/artifacts/
5. elemental build-iso → dist/artifacts/vdi-$VERSION-$ARCH.iso
6. 解包 ISO → 提取 squashfs → 创建 net-install ISO（可选）
7. 生成 sha512 校验和
8. 生成 version.yaml
```

### 4.5 version-* 脚本

```bash
# scripts/version-kubernetes
KUBE_VERSION="v1.34.3"

# scripts/version-kubevirt
KUBEVIRT_VERSION="v1.5.0"

# scripts/version-longhorn
LONGHORN_VERSION="v1.8.1"

# scripts/version-kubeovn
KUBEOVN_VERSION="v1.17.0"

# scripts/version-kagent
KAGENT_VERSION="0.9.6"

# scripts/version
COMMIT=$(git rev-parse --short HEAD)
VERSION=${DRONE_TAG:-${DRONE_BRANCH:-"master"}}
```

## 5. 安装器 Go 代码设计

### 5.1 VDIConfig 结构体

```go
type VDIConfig struct {
    SchemeVersion uint32   `json:"schemeVersion,omitempty"`
    ServerURL     string   `json:"serverUrl,omitempty"`
    Token         string   `json:"token,omitempty"`
    SANS          []string `json:"sans,omitempty"`

    OS      OSConfig      `json:"os,omitempty"`
    Install InstallConfig `json:"install,omitempty"`

    KubernetesVersion string `json:"kubernetesVersion,omitempty"`
    KubevirtVersion   string `json:"kubevirtVersion,omitempty"`
    LonghornVersion   string `json:"longhornVersion,omitempty"`
    KubeovnVersion    string `json:"kubeovnVersion,omitempty"`
    KagentVersion     string `json:"kagentVersion,omitempty"`
}

type InstallConfig struct {
    Automatic           bool          `json:"automatic,omitempty"`
    Mode                string        `json:"mode,omitempty"`    // "create"（创建集群）| "join"（加入集群）
    Role                string        `json:"role,omitempty"`    // "first"（首节点，仅 Mode=create 时有效）| "master"（管理节点）| "worker"（工作节点）
    ManagementInterface NetworkConfig `json:"managementInterface,omitempty"`
    VIP                 string        `json:"vip,omitempty"`
    VIPMode             string        `json:"vipMode,omitempty"` // "dhcp" | "static"
    Device              string        `json:"device,omitempty"`
    DataDisk            string        `json:"dataDisk,omitempty"`
    ConfigURL           string        `json:"configUrl,omitempty"`
    Silent              bool          `json:"silent,omitempty"`
    PowerOff            bool          `json:"powerOff,omitempty"`
    Debug               bool          `json:"debug,omitempty"`
    Webhooks            []Webhook     `json:"webhooks,omitempty"`
}

type OSConfig struct {
    Hostname          string            `json:"hostname,omitempty"`
    Password          string            `json:"password,omitempty"`
    SSHAuthorizedKeys []string          `json:"sshAuthorizedKeys,omitempty"`
    NTPServers        []string          `json:"ntpServers,omitempty"`
    DNSNameservers    []string          `json:"dnsNameservers,omitempty"`
    Modules           []string          `json:"modules,omitempty"`
    Sysctls           map[string]string `json:"sysctls,omitempty"`
    Labels            map[string]string `json:"labels,omitempty"`
    Environment       map[string]string `json:"environment,omitempty"`
}

type NetworkConfig struct {
    Interfaces  []NetworkInterface   `json:"interfaces,omitempty"`
    Method      string               `json:"method,omitempty"` // "dhcp" | "static"
    IP          string               `json:"ip,omitempty"`
    SubnetMask  string               `json:"subnetMask,omitempty"`
    Gateway     string               `json:"gateway,omitempty"`
    BondOptions map[string]string    `json:"bondOptions,omitempty"`
    MTU         int                  `json:"mtu,omitempty"`
    VlanID      int                  `json:"vlanId,omitempty"`
}
```

**与 HarvesterConfig 的差异**：

| 字段 | Harvester | VDI |
|------|-----------|-----|
| RuntimeVersion | RKE2 版本 | KubernetesVersion |
| RancherVersion | Rancher 版本 | 去除 |
| HarvesterChartVersion | Harvester Chart | 去除 |
| MonitoringChartVersion | Monitoring Chart | 去除 |
| LoggingChartVersion | Logging Chart | 去除 |
| Install.Role | "server" \| "worker" | "first" \| "master" \| "worker" |
| SystemSettings | Harvester 特定设置 | 去除 |
| Addons | Harvester addon 配置 | 去除 |

### 5.2 配置读取链路

```
1. 默认值（NewVDIConfig()）
   ↓ mergo.Merge
2. 内嵌配置（/oem/vdi.config）
   ↓ mergo.Merge
3. 远程配置（ConfigURL）
   ↓ mergo.Merge
4. Kernel cmdline（vdi.install.mode=create ...）
   ↓ mergo.Merge
5. 用户 TUI 输入
   ↓
最终配置 → GenerateBootstrapConfig() → /oem/vdi.config
```

### 5.3 TUI 面板流程

**创建集群（首节点）**：

```
askCreatePanel
  → preflightCheckPanel       # 预检
  → askInstallDevicePanel     # 选择安装磁盘
  → askDataDiskPanel          # 选择数据盘（可选）
  → askNetworkPanel           # 网络配置
  → askVIPPanel               # VIP 配置
  → askPasswordPanel          # root 密码
  → askSSHKeyPanel            # SSH 公钥（可选）
  → askNTPPanel               # NTP 服务器
  → confirmPanel              # 确认配置
  → installPanel              # 执行安装
  → donePanel                 # 安装完成
```

**加入集群**：

```
askJoinPanel
  → askServerURLPanel         # 集群 API 地址
  → askTokenPanel             # 加入 Token
  → askInstallDevicePanel     # 选择安装磁盘
  → askNetworkPanel           # 网络配置
  → askPasswordPanel          # root 密码
  → confirmPanel              # 确认
  → installPanel              # 执行安装
  → donePanel                 # 完成
```

### 5.4 Preflight Checks

- NetworkSpeedCheck：网卡速率 >= 1Gbps
- DiskSizeCheck：安装盘 >= 250GB（单盘）或 >= 180GB（多盘）
- MemoryCheck：内存 >= 16GB（生产）/ >= 8GB（开发）
- CPUCheck：CPU 核心 >= 4
- DataDiskCheck：数据盘 != 安装盘，且 >= 50GB

### 5.5 安装执行逻辑

```
doInstall(config VDIConfig)
  1. 写入 /oem/vdi.config（JSON 格式）
  2. 生成 NetworkManager 连接配置
  3. elemental install（OS 安装到目标磁盘）
  4. 复制 bundle 资源到目标磁盘
  5. 配置 grub/systemd-boot
  6. 首节点：写入 KubeKey bootstrap 配置
  7. 工作节点：写入 join 配置
  8. reboot
```

**与 Harvester 的安装差异**：

| 步骤 | Harvester | VDI |
|------|-----------|-----|
| OS 安装 | elemental install + cOS | elemental install + Ubuntu |
| 集群初始化 | RKE2 server + Rancherd | KubeKey create cluster |
| 节点加入 | RKE2 agent | KubeKey join |
| Chart 部署 | Rancherd → Helm | KubeKey addon 或手动 helm install |

### 5.6 main.go

```go
func main() {
    cmd := &cli.Command{
        Name:  "vdi-installer",
        Usage: "Console application to install VDI platform",
        Action: func(ctx context.Context, cmd *cli.Command) error {
            return console.RunConsole()
        },
        Commands: []*cli.Command{
            {
                Name:  "generate-network-config",
                Usage: "Generate NetworkManager connection profiles",
                Action: generateNetworkConfig,
            },
        },
    }
    cmd.Run(context.Background(), os.Args)
}
```

## 6. ISO 构建流程与 OS 镜像

### 6.1 全链路构建流程

```
make default
  ├─ scripts/build                    # 编译 Go 安装器
  ├─ scripts/build-bundle             # 下载离线资源
  ├─ scripts/package-vdi-repo         # 构建 Helm Chart 仓库镜像
  ├─ scripts/package-vdi-installer    # 构建 installer 镜像
  └─ scripts/package-vdi-os           # 构建 OS 镜像 + ISO
       ├─ rancher/vdi-os:$VERSION
       ├─ dist/artifacts/vdi-$VERSION-$ARCH.iso
       ├─ dist/artifacts/vdi-$VERSION-$ARCH-net-install.iso（可选）
       ├─ dist/artifacts/vdi-vmlinuz-$ARCH
       └─ dist/artifacts/vdi-rootfs-$ARCH.squashfs
```

### 6.2 package/vdi-os/Dockerfile

```dockerfile
ARG BASE_OS_IMAGE=ubuntu:22.04
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64

# elemental 工具链
ARG ELEMENTAL_VERSION=v0.10.0
RUN curl -sfL "https://github.com/rancher/elemental/releases/download/${ELEMENTAL_VERSION}/elemental-${ARCH}" \
    -o /usr/bin/elemental && chmod +x /usr/bin/elemental

# wharfie（容器镜像离线加载）
ARG WHARFIE_VERSION=v0.6.8
RUN curl -sfL "https://github.com/rancher/wharfie/releases/download/${WHARFIE_VERSION}/wharfie-${ARCH}" \
    -o /usr/bin/wharfie && chmod +x /usr/bin/wharfie

# 系统组件
RUN apt-get update && apt-get install -y --no-install-recommends \
    containerd kubelet kubectl \
    open-iscsi nfs-common \
    conntrack ipvsadm ebtables \
    jq curl wget \
    && rm -rf /var/lib/apt/lists/*

COPY files/ /
RUN chmod 0600 /system/oem/*
COPY vdi-release.yaml /etc/

# 生成 initrd（Ubuntu 使用 update-initramfs）
RUN update-initramfs -u

ARG VDI_PRETTY_NAME
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"$VDI_PRETTY_NAME\"/g" /etc/os-release
```

### 6.3 elemental build-iso

```
elemental build-iso docker:rancher/vdi-os:$VERSION \
    --config-dir package/vdi-os/ \
    --local \
    -n "vdi-$VERSION-$ARCH" \
    -o dist/artifacts/ \
    --overlay-iso package/vdi-os/iso/ \
    -x "-comp xz" \
    --platform "linux/amd64"
```

overlay-iso 目录：

```
package/vdi-os/iso/
├── boot/grub2/
│   ├── grub.cfg
│   └── vdi.cfg
├── bundle/                  # 离线资源（从 build-bundle 复制）
└── vdi-release.yaml
```

### 6.4 Net-install ISO

从完整 ISO 裁剪，仅保留 vdi-cluster-repo 镜像，设置 `vdi.install.with_net_images=true`。

### 6.5 PXE 支持

产物：vmlinuz + initrd + rootfs.squashfs，通过 HTTP/TFTP 分发。

### 6.6 vdi-release.yaml

```yaml
vdi: v1.0.0
installer: abc1234
os: VDI v1.0.0
kubernetes: v1.34.3
kubevirt: v1.5.0
longhorn: v1.8.1
kubeovn: v1.17.0
kagent: 0.9.6
minUpgradableVersion: 'v0.9.0'
```

## 7. Fork 改造清单

### 7.1 删除的文件

```
scripts/version-rancher
scripts/version-harvester
scripts/patch-harvester
scripts/bump-rancher
scripts/archive-images-lists.sh
scripts/collect-deps.sh
scripts/check-images
scripts/images/rancherd-bootstrap-images.txt
scripts/images/rancher-images.txt
scripts/images/harvester-additional-images.txt
package/harvester-repo/
pkg/config/rename.go
```

### 7.2 重命名的文件

```
package/harvester-os/          → package/vdi-os/
package/harvester-installer/   → package/vdi-installer/
scripts/package-harvester-os   → scripts/package-vdi-os
scripts/package-harvester-installer → scripts/package-vdi-installer
scripts/package-harvester-repo → scripts/package-vdi-repo
scripts/version-rke2           → scripts/version-kubernetes
```

### 7.3 需要重写核心逻辑的文件

- `pkg/config/config.go` — HarvesterConfig → VDIConfig，字段适配
- `pkg/config/constants.go` — 替换版本常量
- `pkg/config/read.go` — 配置路径和 cmdline 前缀
- `pkg/config/schemas.go` — JSON Schema 更新
- `pkg/config/templates.go` — 模板文件替换
- `pkg/console/install_panels.go` — 安装流程重写
- `pkg/console/dashboard_panels.go` — dashboard 重写
- `main.go` — 二进制名称和子命令

### 7.4 需要小改的文件

- `Dockerfile.dapper` — 换基础镜像，zypper → apt-get
- `scripts/build` — 替换 version source 和 LINKFLAGS
- `scripts/build-bundle` — 替换组件栈
- `scripts/package-vdi-os` — 替换版本 source 和镜像名
- `scripts/version` — 删除 QCOW 逻辑

### 7.5 原样复用的文件

- `Makefile`
- `scripts/entry`
- `scripts/lib/image`（镜像管理函数）
- `scripts/lib/iso`（pack_iso 函数）
- `pkg/console/validator.go`（通用校验）
- `pkg/console/network.go`（网络检测）
- `pkg/console/vip.go`（VIP 配置）
- `pkg/preflight/checks.go`（预检框架）
- `pkg/util/`（工具函数）
- `pkg/widgets/`（gocui 控件）

### 7.6 新增的文件

```
scripts/version-kubernetes
scripts/version-kubevirt
scripts/version-longhorn
scripts/version-kubeovn
scripts/version-kagent
scripts/images/allow.yaml
package/vdi-cluster-repo/Dockerfile
package/vdi-os/files/
package/vdi-os/templates/
pkg/config/templates/
```

## 8. 实施阶段

### Phase 1：构建系统基座

```
Dockerfile.dapper → Makefile → scripts/entry → scripts/version → scripts/build
验证：go build 编译出 vdi-installer 二进制
```

### Phase 2：Bundle 系统

```
scripts/version-* → scripts/build-bundle → scripts/lib/image
验证：make build-bundle 下载所有离线资源
```

### Phase 3：OS 镜像 + ISO

```
package/vdi-os/Dockerfile → scripts/package-vdi-os → scripts/lib/iso
验证：make package-vdi-os 生成 ISO 并 QEMU 启动
```

### Phase 4：安装器 Go 代码

```
pkg/config/ → pkg/console/ → pkg/preflight/ → pkg/widgets/ → main.go
验证：TUI 安装流程走通
```

### Phase 5：镜像 + 测试

```
package/vdi-installer/Dockerfile → package/vdi-cluster-repo/Dockerfile → CI
验证：完整 make default 构建 + QEMU 测试
```

## 9. Harvester 安装机制深度分析

### 9.1 三层执行链

Harvester 的安装过程分为三层，每层职责清晰：

```
Layer 1: Go 安装器 (harvester-installer)
  └─ TUI 收集配置 → 生成配置文件 → 调用 Layer 2

Layer 2: Shell 安装脚本 (harv-install)
  └─ elemental install → 镜像预加载 → 配置保存 → 重启

Layer 3: 首次启动 (Rancherd + RKE2)
  └─ Rancherd 读取配置 → 启动 RKE2 → Helm 部署 Harvester
```

### 9.2 Layer 1：Go 安装器配置生成

`doInstall()` (`pkg/console/util.go:518`) 的核心流程：

```
doInstall(config HarvesterConfig)
  1. updateSystemSettings()      # NTP 写入 SystemSettings
  2. roleSetup()                 # 节点角色标签（Management/Worker/Witness）
  3. generateEnvAndConfig()      # 生成三套配置：
     ├─ ConvertToCOS()          # → yip 配置（rootfs/initramfs/network 阶段）
     ├─ ConvertToElementalConfig() # → elemental 分区布局
     └─ 环境变量                # HARVESTER_CONFIG, ELEMENTAL_CONFIG, etc.
  4. 分区布局决策：
     ├─ 单盘模式：CreateRootPartitioningLayoutSharedDataDisk()
     │   OEM(512MB) + STATE(1536MB) + RECOVERY(8192MB) + PERSISTENT(动态) + LH_DEFAULT(剩余)
     └─ 双盘模式：CreateRootPartitioningLayoutSeparateDataDisk()
         OEM(512MB) + STATE(1536MB) + RECOVERY(8192MB) + PERSISTENT(剩余)
  5. 擦除旧安装标记的磁盘
  6. execute("/usr/sbin/harv-install")  # 调用 Layer 2
  7. execute("/usr/sbin/cos-installer-shutdown")  # 关机/重启
```

**yip 配置三阶段**（`ConvertToCOS()` 生成）：

| 阶段 | 作用 | 内容 |
|------|------|------|
| rootfs | 根文件系统定制 | 写入 overlay 文件、配置文件 |
| initramfs | 早期启动配置 | 用户创建、内核模块加载、sysctl、NetworkManager、Rancherd/RKE2 配置 |
| network | 网络就绪后 | hostname、SSH keys |

### 9.3 Layer 2：harv-install 脚本（OS 安装核心）

`package/harvester-os/files/usr/sbin/harv-install` 是实际执行 OS 安装的脚本：

```bash
# 阶段 1：环境准备
blkdeactivate                          # 卸载 LVM/MD 设备
clear_disk_label                       # 清除旧 COS_OEM/COS_STATE/COS_PERSISTENT 标签

# 阶段 2：OS 安装（elemental）
elemental install --config-dir $ELEMENTAL_CONFIG_DIR --debug
# elemental 做了什么：
#   1. 读取 ElementalConfig（target、firmware、part-table、partitions）
#   2. 在目标磁盘上创建分区（OEM/STATE/RECOVERY/PERSISTENT）
#   3. 将当前运行的 OS（squashfs）写入 STATE 分区的 active.img
#   4. 安装 GRUB 引导

# 阶段 3：数据盘格式化
do_data_disk_format                    # 如果配置了独立数据盘，格式化为 EXT4

# 阶段 4：挂载已安装的 OS
do_detect                              # blkid 查找 COS_OEM/COS_STATE/COS_PERSISTENT
do_mount                               # mount STATE → loopback → active.img → /run/cos/target

# 阶段 5：镜像预加载（离线安装的核心）
do_preload
  ├─ preload_rancherd_images           # Rancherd bootstrap 镜像 → /var/lib/rancher/agent/images
  └─ preload_rke2_images               # RKE2 + Harvester 镜像预加载（见下文详解）

# 阶段 6：配置保存
save_configs                           # HARVESTER_CONFIG → /oem/harvester.config
                                       # ELEMENTAL_CONFIG → /oem/elemental.config
save_nm_state                          # NetworkManager 连接配置 → persistent 分区

# 阶段 7：引导配置
update_grub_settings                   # TTY、crashkernel、debug menu entry
save_installation_log                  # 安装日志 → /oem/install/
```

### 9.4 镜像预加载机制（preload_rke2_images）

这是离线安装的核心，分 ISO 和 PXE 两种模式：

**ISO 模式**：
```bash
# 1. 复制镜像到目标 OS
rsync ${ISOMNT}/bundle/harvester/images/rke2-images.*.tar.zst → TARGET/var/lib/rancher/rke2/agent/images/
rsync ${ISOMNT}/bundle/harvester/images/ → TARGET/var/lib/rancher/tmp/images/
rsync ${ISOMNT}/bundle/harvester/images-lists/ → TARGET/tmp/images-lists/

# 2. chroot 进入目标 OS
mount --bind /dev dev && mount --bind /proc proc && mount --rbind /sys sys
chroot . /bin/bash

# 3. 从 bootstrap 镜像中提取 RKE2 二进制
wharfie --images-dir /var/lib/rancher/agent/images/ $rke2_image $inst_tmp
tar xf $inst_tmp/rke2.linux-amd64.tar.gz -C $rke2_tmp

# 4. 启动临时 RKE2 server（仅用于容器镜像导入）
$rke2_tmp/bin/rke2 server &> /rke2.log &
wait_for_containerd_ready

# 5. 停止 RKE2，启动独立 containerd
pkill rke2
containerd -c /var/lib/rancher/rke2/agent/etc/containerd/config.toml &

# 6. 导入所有离线镜像
for i in $tmp_images_dir/*.tar.zst; do
    zstd -d $i -o /usr/local/images.tar
    ctr -n k8s.io images import --no-unpack /usr/local/images.tar
done

# 7. 验证镜像完整性
for i in $images_lists_dir/*.txt; do
    ctr-check-images.sh $i
done

# 8. 清理
pkill containerd
rm -rf tmp_images_dir images_lists_dir
```

**PXE 模式**：使用 bind-mount 代替 rsync，直接从网络 ISO 挂载镜像目录。

### 9.5 Layer 3：首次启动（Rancherd + RKE2 Bootstrap）

系统重启后，yip 框架读取 `/oem/*.config`，执行 initramfs 阶段：

```
initramfs 阶段（yip 执行）：
  1. 创建用户 rancher（密码哈希）
  2. 加载内核模块（kvm, vhost_net）
  3. 设置 sysctl、环境变量
  4. 写入 Rancherd 配置 → /etc/rancher/rancherd/config.yaml.d/
  5. 写入 RKE2 配置 → /etc/rancher/rke2/config.yaml.d/
  6. 配置 NetworkManager 连接
  7. 启用 NTP 服务

Rancherd 启动：
  1. 读取 /etc/rancher/rancherd/config.yaml.d/ 中的 bootstrap 资源
  2. 启动 RKE2：
     - 创建集群：role: cluster-init（不使用 kubeadm，RKE2 自有引导机制）
     - 加入集群：server: <管理节点 URL> + token
  3. RKE2 内置 HelmChart 控制器自动部署：
     - Harvester Chart（从 cluster-repo 镜像）
     - Harvester CRD Chart
     - Monitoring Chart
     - Logging Chart
     - KubeOVN Operator Chart
```

**Rancherd 配置**（`rancherd-config.yaml` 模板）：

```yaml
# 创建集群时：
role: cluster-init
nodeName: <hostname>
token: "<token>"
kubernetesVersion: v1.35.5+rke2r1
rancherVersion: v2.11.3

# 加入集群时：
server: https://<管理节点VIP>:9345
role: agent
nodeName: <hostname>
token: "<token>"
```

**RKE2 Server 配置**（`rke2-90-harvester-server.yaml`）：

```yaml
cni: multus,canal
cluster-cidr: 10.52.0.0/16
service-cidr: 10.53.0.0/16
cluster-dns: 10.53.0.10
tls-san:
  - <VIP>
kubelet-arg:
  - "max-pods=200"
  - "node-labels=harvesterhci.io/managed=true"
```

### 9.6 Harvester 的 K8s 安装方式

**Harvester 不使用 kubeadm**。它使用 RKE2（Rancher Kubernetes Engine 2），这是 Rancher 的 K8s 发行版：

| 维度 | kubeadm | RKE2 (Harvester) | KubeKey (VDI) |
|------|---------|-------------------|---------------|
| 引导方式 | kubeadm init/join | RKE2 自有引导（cluster-init/agent） | 底层调用 kubeadm |
| 安装方式 | 包管理器 (apt/yum) | 从容器镜像提取二进制 (wharfie) | 下载预编译二进制 |
| 配置方式 | kubeadm-config.yaml | /etc/rancher/rke2/config.yaml.d/ | KubeKey config.yaml |
| CNI | 手动安装 | 内置 (multus, canal) | 指定 CNI plugin |
| 镜像管理 | 手动预加载 | 内置 HelmChart 控制器 | 手动 helm install |
| 加入方式 | kubeadm join + token | RKE2 agent + server URL + token | KubeKey join + token |

**RKE2 的特殊之处**：
1. **不用 kubeadm**：RKE2 有自己的集群引导机制，不依赖 kubeadm init/join
2. **二进制嵌入容器镜像**：RKE2 二进制打包在 `rancher/system-agent-installer-rke2` 镜像中，通过 `wharfie` 工具提取
3. **内置 HelmChart 控制器**：RKE2 自动监听 `HelmChart` CRD，自动部署 Chart
4. **内置 containerd**：RKE2 自带 containerd，不依赖系统 containerd

### 9.7 加入集群的流程

```
configureInstalledNode() (pkg/console/util.go:831)
  1. roleSetup()                    # 设置节点角色标签
  2. generateTempConfigFiles()      # 生成 COS + Harvester 配置文件
  3. applyRancherdConfig()          # 应用 Rancherd 配置
     ├─ GenerateRancherdConfig()    # 生成 yip 配置
     │   └─ initRancherdStage()     # 写入 rancherd-config.yaml（含 server URL + token）
     ├─ yip -s live <config>        # 应用 live 阶段（网络、用户、RKE2 配置）
     └─ yip -s finalise <config>    # 应用 finalise 阶段（持久化配置文件）
  4. restartCoreServices()          # 重启 rancherd/rke2-agent
```

### 9.8 Install-only 模式

"Install Harvester binaries only" 模式（`ModeInstall`）：
- 仅将 OS 写入磁盘，不配置网络、不启动 Rancherd
- 用于预装 QCOW2 镜像场景
- 设置 `installModeOnly = true`，跳过网络/Rancherd 配置
- `harv-install` 中通过 `HARVESTER_MODE=install` 环境变量控制

### 9.9 VDI 的 K8s 安装方式（KubeKey）

VDI 使用 KubeKey 引导 K8s 集群，KubeKey 底层调用 kubeadm：

```
KubeKey create cluster:
  1. 下载 K8s 二进制（kubelet, kubeadm, kubectl）
  2. kubeadm init --config <KubeKey 生成的配置>
  3. 安装 CNI 插件（Kube-OVN）
  4. 部署 addons（Helm Charts）

KubeKey join:
  1. 下载 K8s 二进制
  2. kubeadm join <master-ip>:6443 --token <token>
```

**VDI 的 harv-install 改造**：

```bash
# 原 Harvester 流程：
elemental install → 预加载 RKE2 镜像 → 保存 Rancherd 配置 → 重启 → Rancherd 启动 RKE2

# VDI 改造流程：
elemental install → 预加载 K8s/KubeVirt/Longhorn 镜像 → 保存 KubeKey 配置 → 重启 → KubeKey 引导 K8s
```

关键变化：
- `preload_rke2_images()` → `preload_k8s_images()`（导入 K8s + KubeVirt + Longhorn + Kube-OVN + kagent 镜像）
- `preload_rancherd_images()` → `preload_kubekey_images()`（导入 KubeKey bootstrap 镜像）
- Rancherd 配置 → KubeKey 配置（`/etc/kubekey/config.yaml`）
- RKE2 server/agent → KubeKey create/join

## 10. 风险与缓解（更新）

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| elemental 不支持 Ubuntu | ISO 构建失败 | 验证 elemental 兼容性，必要时使用 Ubuntu 的 casper/live-build 作为后备 |
| Ubuntu initrd 生成方式 | initrd 生成失败 | 主方案：使用 Ubuntu 原生 update-initramfs；后备方案：显式安装 dracut 并使用 dracut（与 Harvester 一致）|
| KubeKey 不支持离线 bootstrap | 集群初始化失败 | 准备 KubeKey 离线配置和本地镜像仓库 |
| Harvester 上游变更 | 合并冲突 | 定期 rebase，关注关键文件变更 |
| Ubuntu 包依赖差异 | 运行时错误 | 在 Dockerfile 中显式声明所有依赖 |
| KubeKey 底层依赖 kubeadm | 与 RKE2 的无 kubeadm 方案不同，需要额外配置 | KubeKey 自动管理 kubeadm 配置，无需手动干预；但需确保 K8s 版本与 KubeKey 兼容 |
| KubeKey 离线模式限制 | 离线集群初始化可能失败 | 使用 KubeKey 的 manifest 离线模式，预打包所有二进制和镜像 |
