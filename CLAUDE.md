# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本仓库是 VDI (Virtual Desktop Infrastructure) 离线安装器，基于 Harvester Installer 架构改造，使用 RKE2 + HelmChart CRD 声明式部署 KubeVirt/Longhorn/Kube-OVN/kagent 组件栈。

**技术栈**：
- **语言**：Go 1.26
- **TUI**：gocui (终端 UI 框架)
- **K8s 运行时**：RKE2
- **addon 管理**：HelmChart CRD (helm.cattle.io/v1)
- **ISO 构建**：dracut dmsquash-live + elemental build-iso
- **基础 OS**：BCLinux 21.10 U5

## 目录结构

```
VDI/
├── main.go              # 安装器入口
├── Makefile             # Dapper 构建系统
├── Dockerfile.dapper    # 构建宿主机环境（Go + 工具链）
├── go.mod / go.sum      # Go module (vdi-installer)
├── pkg/                 # Go 代码
│   ├── config/          # VDIConfig 结构体 + RKE2 模板
│   ├── console/         # gocui TUI 安装器
│   ├── preflight/       # 硬件预检
│   ├── util/            # 工具函数
│   └── widgets/         # gocui 控件
├── scripts/             # 构建脚本
│   ├── version-*        # 组件版本（RKE2/KubeVirt/Longhorn/Kube-OVN/kagent）
│   ├── build            # 编译 Go 安装器
│   ├── build-bclinux-base # 从 ISO RPM 仓库创建 BCLinux 基础 Docker 镜像
│   ├── build-bundle     # 下载离线资源
│   ├── package-vdi-os   # 构建 VDI Docker 镜像 + elemental build-iso
│   └── package-vdi-repo # 构建 Helm Chart 仓库镜像
├── package/             # Docker 镜像定义
│   ├── vdi-os/          # BCLinux 21.10 U5 + VDI 安装器文件
│   ├── vdi-installer/   # 安装器二进制镜像
│   └── vdi-cluster-repo/# Helm Chart 仓库
└── docs/                # 设计文档 + 实施计划
```

## 构建命令

```bash
make default            # 完整构建（编译 + 打包 ISO）
make build              # 编译 Go 安装器
make build-bundle       # 下载离线资源
make package-vdi-os     # 构建 OS 镜像 + ISO
make package-vdi-repo   # 构建 Helm Chart 仓库镜像
make shell              # 进入构建容器调试
make test               # 运行测试
make validate           # golangci-lint 检查
```

### 构建容器（Dapper）

构建在 Dapper 容器内执行，构建者**只需宿主机装 docker**，其余工具容器内自行安装：
- **docker + buildx**：宿主机挂载（DinD，容器内调宿主机 daemon，CLI 版本与 daemon 匹配）
- **helm / yq**：Dockerfile.dapper 内 curl 安装（无需宿主机预装）
- **Go 模块**：容器内 `go build` 自动下载（GOPROXY 默认，需网络）
- **cache/ + dist/**：bind 挂载（构建缓存与产物，dist/ 含 BCLinux ISO 输入）

docker/buildx 路径由 Makefile 探测后通过 build-arg 注入 Dockerfile.dapper 的 ARG（不硬编码用户目录），探测失败时 `make` 明确报错。

#### 外部输入准备

构建依赖 4 个外部输入（`.gitignore` 忽略，不入 git）：
- **BCLinux ISO**（客户提供）：放至 `dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso`
- **elemental 二进制**（~18MB，v0.3.1）：`make fetch-deps` 自动下载
- **wharfie 二进制**（~47MB，v0.6.8）：`make fetch-deps` 自动下载
- **yip 二进制**（~10MB，v1.9.2）：`make fetch-deps` 自动下载

`make default` / `make package-vdi-os` 会自动先跑 `fetch-deps`（幂等），无需手动预下载。

```bash
make fetch-deps    # 下载 elemental + wharfie 到 package/vdi-os/files/usr/bin/
make check-deps    # 前置检查（BCLinux ISO + elemental + wharfie），缺失明确报错
make default       # check-deps 已自动接入，依赖不全会在构建前中断
```

#### 本地包缓存与无代理下载

运行 `make build-bundle` 时支持通过环境变量 `LOCAL_PKG_DIR`（如 `export LOCAL_PKG_DIR=/opt/vdi-pkgs`）指定本地离线包检索路径。若该路径下存在与下载目标同名的文件，系统将优先进行本地拷贝；若不存在或未命中，则使用无代理配置的 `curl` 正常下载。若未设置此环境变量，则默认优先尝试检索项目下的 `cache/downloads` 目录。

### TUI 单 console 红线（踩坑）

内核启动参数必须用 `console=tty1`（单 VGA console），**禁止 `console=tty0 console=ttyS0`**。原因：`console=tty0` 让 `setup-installer.sh` 给 tty0 创建 getty override，叠加 Dockerfile 静态 override 会导致 **tty0/tty1/ttyS0 三个 getty 同时跑 vdi-installer**，争用键盘 → 快速按键时面板串行/叠加（TUI 画面错乱）。harvester 用 `console=tty1` 单实例无此问题。

getty drop-in 由 `setup-installer.sh` 运行时根据 `/sys/class/tty/console/active` 只为第一个 VGA tty 创建（对齐 harvester），**Dockerfile 不静态创建 getty override**。`start-installer.sh` 不设 stty/COLUMNS/LINES——用 agetty 提供的实际 winsize，gocui 经 `ioctl(TIOCGWINSZ)` 读取。`pkg/console/console.go` 有 `g.Size() >= 80x24` 前置校验，尺寸不足明确报错而非黑屏。

构建环境内存需 ≥16G（elemental + mksquashfs xz 压缩峰值 ~9.7GB，7.7G 内存会 OOM），不足时加 swap。

### 安装落地分区/镜像红线（踩坑）

elemental install 落地阶段分区大小与镜像加载有一组强约束（`pkg/config/constants.go` + `pkg/config/cos.go` + `package/vdi-os/files/usr/sbin/vdi-install`），任一不满足都会在安装中途 No space / I/O error / command not found：

- **内核参数 `selinux=0`**（不是 `enforcing=0`）：彻底禁用 selinux 不挂 selinuxfs。`enforcing=0`(Permissive) 下 rsync -X 设 `security.selinux` xattr 在 ext2 active.img 上 Permission denied (code 23)。改 `package/vdi-os/iso/boot/grub2/grub.cfg` + `isolinux/isolinux.cfg`。
- **分区大小三常量必须配套**（`pkg/config/constants.go`）：`DefaultCosStateSizeMiB=20480`（容纳 active.img(8G)+passive.img(8G)=16G，elemental 创建两个镜像，超 COS_STATE 会 loop I/O error）、`DefaultCosRecoverySizeMiB=12288`（>active.img，recovery.img 复制 active.img）、`DefaultSystemImageSizeMiB=8192`（active.img 的 ext2 大小，容纳 rootfs+镜像tar+runtime+containerd 数据）。改一个要同步验算另两个。
- **`Install.System.Size` 必须显式设**（`pkg/config/cos.go` 两个 `CreateRootPartitioningLayout*`）：不设则 elemental 自动按 rootfs 算，镜像预加载 No space。
- **grub2 EFI 模块**：BCLinux 仓库无 `grub2-efi-x64-modules`，Dockerfile 多阶段从 `debian:bookworm-slim` 的 `grub-efi-amd64-bin` 提取 x86_64-efi 模块到 `/usr/lib/grub/x86_64-efi/`（elemental 找这个生成 UEFI core.img）。
- **`/etc/cos/grub.cfg` 模板**：elemental install 复制它到目标盘，缺失报 stat no such file。在 `package/vdi-os/files/etc/cos/grub.cfg` + `bootargs.cfg`（参考 harvester）。
- **RKE2 镜像加载需 `system-agent-installer-rke2`**：vdi-install 用 wharfie 从中提取 rke2 二进制+containerd。`build-bundle` 下载到 `bundle/rancherd/images/`，vdi-install 复制到 `target/var/lib/rancher/agent/images/` + chroot 找 `rancherd-bootstrap-images-*.txt`（对齐 harvester harv-install）。containerd 二进制不来自系统包，没这个镜像会 `containerd: command not found`。
- **vdi-install 导入镜像后删原 tar.zst**（`rm -f $i`）：active.img 内部空间紧张，不删会 containerd 导入时 No space。

### 安装后引导链红线（踩坑）

安装到目标盘后引导链四个环节缺一不可（BCLinux 缺 harvester SUSE MicroOS 自带的环节），任一缺失装机完起不来：

- **cos-img dracut 模块**（`package/vdi-os/files/usr/lib/dracut/modules.d/90cos-img/`，Dockerfile `dracut --add cos-img`）：dracut 把 `root=LABEL=COS_STATE` 分区挂到 /sysroot，但 COS_STATE 不是 OS tree（无 os-release）→ switch-root 失败。模块用 `pre-pivot` hook（非 pre-mount，pre-mount 时 /sysroot 尚空）loop 挂 active.img + `mount --bind` 覆盖 /sysroot。`installkernel() { instmods loop; }` 必须有，否则 losetup 报 no unused loop device。
- **grubx64.efi 安装后注入**（`vdi-install: fix_efi_grubx64`）：elemental install 只放 grub.efi，BCLinux shim 硬编码找 grubx64.efi。ISO 阶段的字节级注入只管 ISO，目标盘需 vdi-install 把 grub.efi 复制为 grubx64.efi 到 EFI/boot/ + EFI/elemental/。
- **kernel 复制到 COS_STATE/boot**（`vdi-install: copy_kernel_to_state`）：grub loopback 加载 8G active.img 会 OOM（cannot allocate verified buffer），改把 kernel/initrd 从 active.img 复制到 COS_STATE 分区 /boot/，grub 直接 `linux ($root)/boot/vmlinuz`。
- **grub.cfg 变量在 menuentry 内**（`package/vdi-os/files/etc/cos/grub.cfg`）：`set img` + `kernelcmd` 必须在 menuentry 内定义，否则 `cos-img/filename=` 空值，dracut 找不到 active.img。变量内联不 source bootargs.cfg。

## 关键配置

### VDIConfig 结构体

安装器的核心配置结构体，定义在 `pkg/config/config.go`。安装模式、集群网络、管理网卡等运行时配置统一收归到 `Install`/`OS` 子结构体，顶层只保留版本与集群标识：

```go
type VDIConfig struct {
    SchemeVersion   uint32
    ServerURL       string
    Token           string
    SANS            []string
    OS              OSConfig      // Hostname、SSHAuthorizedKeys、Password、DNS 等
    Install         InstallConfig // Mode、Role、ManagementInterface、ClusterPodCIDR 等
    RKE2Version     string
    KubevirtVersion string
    LonghornVersion string
    KubeovnVersion  string
    KagentVersion   string
}
```

⚠️ 不要在顶层新增 `Automatic/Hostname/ClusterPodCIDR/ManagementInterface` 等字段——它们已迁入 `Install`/`OS`，顶层同名旧字段已删除。读写集群网络配置用 `config.Install.ClusterPodCIDR/ClusterServiceCIDR/ClusterDNS`，hostname 用 `config.OS.Hostname`。

### RKE2 配置模板

- `pkg/config/templates/rke2-server.yaml` — RKE2 server 配置
- `pkg/config/templates/rke2-agent.yaml` — RKE2 agent 配置
- `pkg/config/templates/helmchart-*.yaml` — HelmChart manifests

### 版本管理

版本号通过 `scripts/version-*` 脚本管理，Go 二进制通过 ldflags 注入：

```bash
scripts/version-rke2      # RKE2_VERSION="v1.31.4+rke2r1"
scripts/version-kubevirt  # KUBEVIRT_VERSION="v1.5.0"
scripts/version-longhorn  # LONGHORN_VERSION="v1.8.1"
scripts/version-kubeovn   # KUBEOVN_VERSION="v1.16.2"
scripts/version-kagent    # KAGENT_VERSION="0.9.6"
```

## 安装流程

1. **TUI 配置收集** — 用户选择安装模式（首节点/管理节点/工作节点），配置网络、磁盘、VIP 等
2. **配置生成** — 生成 RKE2 config.yaml + HelmChart manifests
3. **OS 安装** — elemental install 将 OS 写入目标磁盘
4. **镜像预加载** — 将离线镜像导入目标 OS 的 containerd
5. **首次启动** — RKE2 server/agent 启动，HelmChart 控制器自动部署组件

## HelmChart CRD

VDI 使用 RKE2 内置的 HelmChart CRD 声明式管理组件：

```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: kube-ovn
  namespace: kube-system
spec:
  chart: /var/lib/rancher/rke2/server/charts/kube-ovn.tgz
  targetNamespace: kube-system
  bootstrap: true
```

RKE2 启动时自动 apply `/var/lib/rancher/rke2/server/manifests/` 目录下的所有 YAML 文件。

## 开发指南

### 编译

```bash
export PATH=~/go-sdk/go/bin:$PATH
export GOROOT=~/go-sdk/go
go build ./...
```

### 测试

```bash
go test ./pkg/...
```

### 添加新组件

1. 在 `scripts/version-*` 中添加版本号
2. 在 `scripts/build-bundle` 中添加下载逻辑
3. 在 `package/vdi-os/files/var/lib/rancher/rke2/server/manifests/` 中添加 HelmChart YAML
4. 在 `pkg/config/templates/` 中添加 Go template（如需动态配置）

## 深入文档指针

- [构建流程](file:///home/zcq/Github/VDI/docs/build-pipeline.md)：Makefile+Dapper 编排、scripts 脚本链、Go 版本注入、package-vdi-os 8 步、产物依赖图、外部输入契约。
- [构建环境前置条件](file:///home/zcq/Github/VDI/docs/build-env.md)：新环境从零构建的前置清单（BCLinux ISO、宿主机工具、网络访问、内存/磁盘、常见问题）。
- [本地包缓存设计说明书](file:///home/zcq/Github/VDI/docs/superpowers/specs/2026-06-23-local-pkg-cache-design.md)：阐述了本地离线包查找拷贝逻辑以及无代理 curl 回退设计。
- [本地包缓存实施计划](file:///home/zcq/Github/VDI/docs/superpowers/plans/2026-06-23-local-pkg-cache.md)：记录了具体的实施、校验和测试脚本细节。

