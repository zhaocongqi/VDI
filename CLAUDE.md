# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本仓库是 VDI (Virtual Desktop Infrastructure) 离线安装器，基于 Harvester Installer 架构改造，使用 RKE2 + HelmChart CRD 声明式部署 KubeVirt/Longhorn/Kube-OVN/kagent 组件栈。

**技术栈**：
- **语言**：Go 1.26
- **TUI**：gocui (终端 UI 框架，kickstart `%pre` 阶段作配置收集 + ks 生成器)
- **K8s 运行时**：RKE2
- **addon 管理**：HelmChart CRD (helm.cattle.io/v1)
- **ISO 构建**：kickstart + xorriso（`feat/kickstart-xorriso` 分支，复用 BCLinux DVD anaconda stage2；main 分支保留 elemental Live 型）
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
├── scripts/             # 构建脚本（Makefile 用 find 自动生成同名 target）
│   ├── version-*        # 组件版本（RKE2/KubeVirt/Longhorn/Kube-OVN/kagent）
│   ├── build            # 编译 Go 安装器
│   ├── build-bundle     # 下载离线资源（RKE2 二进制/镜像/组件镜像/charts）
│   ├── package-vdi-iso  # xorriso 重建 BCLinux DVD ISO（注入 ks + vdi-installer + bundle）
│   ├── package-vdi-installer # 构建安装器二进制镜像
│   └── package-vdi-repo # 构建 Helm Chart 仓库镜像
├── package/             # Docker 镜像定义 + ISO 输入
│   ├── vdi-os/          # BCLinux 21.10 U5 + VDI 安装器文件（ks/ + iso/bundle/）
│   ├── vdi-installer/   # 安装器二进制镜像
│   └── vdi-cluster-repo/# Helm Chart 仓库
└── docs/                # 设计文档 + 实施计划
```

## 构建命令

```bash
make build              # 编译 Go 安装器
make build-bundle       # 下载离线资源（RKE2 二进制/镜像/charts）
make package-vdi-iso    # 构建 VDI 安装型 ISO（BCLinux DVD + kickstart + xorriso）
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

构建依赖 1 个外部输入（`.gitignore` 忽略，不入 git）：
- **BCLinux ISO**（客户提供）：放至 `dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso`

`make package-vdi-iso` 解包该 DVD ISO 重建。kickstart 链路不再需要 elemental/wharfie/yip 二进制（已随 elemental 死代码一并删除）。

```bash
make build           # 编译 vdi-installer → bin/vdi-installer
make build-bundle    # 下载 RKE2 二进制/镜像/charts → package/vdi-os/iso/bundle/vdi/
make package-vdi-iso # 解包 BCLinux DVD + 注入 ks/vdi-installer/bundle + xorriso 重建 → dist/artifacts/vdi-*.iso
make default         # build + build-bundle + package-vdi-iso 全链路
```

#### 本地包缓存与无代理下载

运行 `make build-bundle` 时支持通过环境变量 `LOCAL_PKG_DIR`（如 `export LOCAL_PKG_DIR=/opt/vdi-pkgs`）指定本地离线包检索路径。若该路径下存在与下载目标同名的文件，系统将优先进行本地拷贝；若不存在或未命中，则使用无代理配置的 `curl` 正常下载。若未设置此环境变量，则默认优先尝试检索项目下的 `cache/downloads` 目录。

### TUI winsize 前置校验（踩坑）

kickstart 链路下 TUI 在 anaconda `%pre` 阶段跑（`ks.cfg` 交互分支 `exec </dev/tty1` + `chvt 1`）。`pkg/console/console.go` 有 `g.Size() >= 80x24` 前置校验，尺寸不足明确报错而非黑屏。gocui 经 `ioctl(TIOCGWINSZ)` 读取实际 winsize。

`%pre` 串口诊断：`ks.cfg` 开头 `exec > /dev/ttyS0 2>&1` + `set -x` 把 %pre 全量输出重定向到串口，便于 qemu 验证时实时观察。交互分支再 `exec </dev/tty1 >/dev/tty1` 切到物理控制台。验证装机产物用"挂盘直读"（`vgchange -ay` + 只读挂载 bclinux/root LV），不靠串口 pexpect（`-no-reboot`+`-serial stdio` 模式 qemu 会提前退出，pexpect 必 EOF）。

### 安装型 ISO 构建红线（kickstart + xorriso）

`feat/kickstart-xorriso` 分支已弃 elemental，改用 BCLinux 母语的 kickstart + xorriso 做"安装型"ISO（复用 BCLinux DVD 自带 anaconda stage2，非自建 squashfs Live）。构建链 `scripts/package-vdi-iso`：xorriso 解包 BCLinux DVD → 注入 `ks.cfg` + `vdi/vdi-installer` + `bundle/` → 改 `isolinux.cfg`/`grub.cfg` 加 `inst.ks=hd:LABEL=BCLinux.x86_64:/ks.cfg` → xorriso 重建（`-isohybrid-mbr` 保留 BIOS+UEFI 双引导，卷标必须 `BCLinux.x86_64`）。踩坑：

- **ISO 9660 文件 0444 只读**：xorriso 解包后 `chmod -R u+w`，改写 `isolinux.cfg`/`grub.cfg` 前再 `chmod u+w`，否则写失败。
- **BCLinux anaconda 36 兼容性**：`install`/`autostep` 指令已移除（报错）→ 删除；`%packages` 缺包即失败 → 只列仓库内有的包；`rootpw --iscrypted` 偶发不生效 → `%post` 用 `chpasswd` 兜底。
- **产线 ISO 默认走交互 TUI**：`isolinux.cfg`/`grub.cfg` 默认装机项**不带** `vdi.install.automatic=true`（让 `%pre` 弹 gocui TUI 收集配置）。qemu 无人值守验证需显式注入该参数——`scripts/qemu-test-ks` 阶段1 用 `-kernel`/`-initrd` 从 ISO 解出 vmlinuz/initrd 直引导，`-append` 带 `vdi.install.automatic=true`。
- **`%pre` → `%include` 时序**：`ks.cfg` 的 `%pre` 调 `vdi-installer`（交互 `RunConsole` 或自动 `AutoInstall`）把 `KickstartRender(cfg)` 写到 `/tmp/ks-include.cfg`，随后 `%include /tmp/ks-include.cfg` 展开。`KickstartRender` 输出**完整 ks**（text/network/clearpart/autopart/%packages/%post），经 `%include` 文本展开等价内联。
- **磁盘探测在 %pre 用 Go 读 `/sys/block/*`**：`pkg/config/kickstart.go` 的 `detectInstallAndDataDisk` 在 `%pre`（vdi-installer 运行时）探测主盘/数据盘，结果作字面量嵌入 ks（`ignoredisk --only-use=<主盘>` + `DataDisk` 非空时 `ignoredisk --drives=<数据盘>`）和 `%post` 数据盘格式化段。**不依赖 lsblk**（历史踩坑：Ramdisk 环境缺 lsblk 崩溃）。
- **RKE2 离线**：`rke2.linux-amd64.tar.gz` 解压 `/usr/local`（二进制内嵌 containerd，删 wharfie）；镜像 `*.tar.zst` 放 `agent/images/`，RKE2 首启自动导入（删 chroot ctr import）。`%post --nochroot` 从 `/run/install/repo/bundle/vdi` 复制，chroot `%post` 写 `config.yaml`/manifests + `enable rke2-server`/`rke2-agent`。
- **内存**：kickstart 装机无 squashfs/active.img，4G 够（elemental 时代需 ≥16G）。

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

## 安装流程（kickstart 链路）

1. **ISO 引导** — BCLinux DVD ISO 引导，`inst.ks=hd:LABEL=BCLinux.x86_64:/ks.cfg` 加载 ks 模板
2. **`%pre` 配置收集** — ks `%pre` 调 `vdi-installer`：交互模式弹 gocui TUI（选模式/网络/磁盘/VIP/密码/role）；自动模式（`vdi.install.automatic=true`）用默认/预置配置。`KickstartRender(cfg)` 渲染完整 ks 写 `/tmp/ks-include.cfg`
3. **anaconda 装机** — `%include /tmp/ks-include.cfg` 展开：分区（LVM autopart）+ 装包 + `%post --nochroot` 从 ISO 复制 RKE2 bundle + `%post` chroot 解压 RKE2、写 config.yaml/manifests、enable rke2-server/agent
4. **首次启动** — RKE2 server/agent 启动，首启自动导入 `agent/images/*.tar.zst`，HelmChart 控制器 apply `server/manifests/` 部署 KubeVirt/Longhorn/Kube-OVN/kagent

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
3. 在 `pkg/config/templates/helmchart-<组件>.yaml` 中添加 HelmChart 模板（由 `RenderRKE2Manifests` 渲染，`kickstart.go` 嵌入 `%post` 写到目标盘 `server/manifests/`）
4. 在 `pkg/config/cos.go` 的 `genBootstrapResources` 注册新组件 manifest

## 深入文档指针

- [构建流程](file:///home/zcq/Github/VDI/docs/build-pipeline.md)：Makefile+Dapper 编排、scripts 脚本链、Go 版本注入、package-vdi-iso 流程、产物依赖图、外部输入契约。
- [构建环境前置条件](file:///home/zcq/Github/VDI/docs/build-env.md)：新环境从零构建的前置清单（BCLinux ISO、宿主机工具、网络访问、内存/磁盘、常见问题）。
- [本地包缓存设计说明书](file:///home/zcq/Github/VDI/docs/superpowers/specs/2026-06-23-local-pkg-cache-design.md)：阐述了本地离线包查找拷贝逻辑以及无代理 curl 回退设计。
- [本地包缓存实施计划](file:///home/zcq/Github/VDI/docs/superpowers/plans/2026-06-23-local-pkg-cache.md)：记录了具体的实施、校验和测试脚本细节。

