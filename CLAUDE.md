# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本仓库是 VDI (Virtual Desktop Infrastructure) 离线安装器，基于 Harvester Installer 架构改造，使用 RKE2 + HelmChart CRD 声明式部署 KubeVirt/Longhorn/Kube-OVN/kagent 组件栈。

**技术栈**：
- **语言**：Go 1.26
- **TUI**：gocui (终端 UI 框架)
- **K8s 运行时**：RKE2
- **addon 管理**：HelmChart CRD (helm.cattle.io/v1)
- **ISO 构建**：dracut dmsquash-live + xorriso
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
│   ├── build-bundle     # 下载离线资源
│   ├── package-vdi-os   # 构建 OS 镜像 + ISO
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

## 关键配置

### VDIConfig 结构体

安装器的核心配置结构体，定义在 `pkg/config/config.go`：

```go
type VDIConfig struct {
    SchemeVersion       uint32
    Automatic           bool
    ServerURL           string
    Token               string
    OS                  OSConfig
    Install             InstallConfig
    Hostname            string
    ClusterPodCIDR      string
    ClusterServiceCIDR  string
    ClusterDNS          string
    ManagementInterface Network
    RKE2Version         string
    KubevirtVersion     string
    LonghornVersion     string
    KubeovnVersion      string
    KagentVersion       string
}
```

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
