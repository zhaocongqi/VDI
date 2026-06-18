# VDI 安装器架构重设计实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork harvester-installer，改造为 VDI 离线安装器（Ubuntu + RKE2 + HelmChart CRD），替换现有 iso-builder。

**Architecture:** Fork harvester-installer 仓库，保留 Dapper 构建系统 + Go/gocui TUI 安装器 + elemental ISO 构建工具链，替换 OS 基础为 Ubuntu 22.04，K8s 运行时为 RKE2，组件栈为 Kube-OVN + Longhorn + KubeVirt + kagent，addon 管理为 RKE2 HelmChart CRD。

**Tech Stack:** Go 1.26, gocui, elemental, RKE2, HelmChart CRD, Dapper, xorriso, squashfs-tools

## Global Constraints

- 所有构建在 Dapper 容器内执行，不依赖宿主机环境
- 版本号通过 `scripts/version-*` 脚本管理，Go 二进制通过 ldflags 注入
- 离线资源通过 `scripts/build-bundle` 下载，打包到 ISO 的 bundle/ 目录
- RKE2 配置写入 `/etc/rancher/rke2/config.yaml`，HelmChart manifests 写入 `/var/lib/rancher/rke2/server/manifests/`
- 镜像使用 skopeo 下载为 docker-archive + zstd 压缩
- ISO 使用 elemental build-iso 从 Docker 镜像构建

---

## 子任务清单

### 子任务 1：Fork 并清理 Harvester 特有文件

**目标：** Fork harvester-installer 仓库，删除 VDI 不需要的 Harvester 特有文件。

**Files:**
- Delete: `scripts/version-rancher`
- Delete: `scripts/version-harvester`
- Delete: `scripts/patch-harvester`
- Delete: `scripts/bump-rancher`
- Delete: `scripts/archive-images-lists.sh`
- Delete: `scripts/collect-deps.sh`
- Delete: `scripts/check-images`
- Delete: `scripts/images/rancherd-bootstrap-images.txt`
- Delete: `scripts/images/rancher-images.txt`
- Delete: `scripts/images/harvester-additional-images.txt`
- Delete: `package/harvester-repo/`
- Delete: `pkg/config/rename.go`
- Delete: `ci/terraform/`

**Steps:**

- [ ] 1.1 Fork harvester-installer 到 vdi-installer 目录
- [ ] 1.2 删除上述文件
- [ ] 1.3 验证仓库结构完整（`ls scripts/ package/ pkg/`）
- [ ] 1.4 提交：`chore: fork harvester-installer, remove Harvester-specific files`

---

### 子任务 2：创建 version-* 版本脚本

**目标：** 创建 VDI 组件的独立版本脚本，替换 Harvester 的版本脚本。

**Files:**
- Create: `scripts/version-rke2`
- Create: `scripts/version-kubevirt`
- Create: `scripts/version-longhorn`
- Create: `scripts/version-kubeovn`
- Create: `scripts/version-kagent`
- Modify: `scripts/version`（删除 QCOW 逻辑）

**Steps:**

- [ ] 2.1 创建 `scripts/version-rke2`：

```bash
#!/bin/bash
RKE2_VERSION="v1.31.4+rke2r1"
```

- [ ] 2.2 创建 `scripts/version-kubevirt`：

```bash
#!/bin/bash
KUBEVIRT_VERSION="v1.5.0"
```

- [ ] 2.3 创建 `scripts/version-longhorn`：

```bash
#!/bin/bash
LONGHORN_VERSION="v1.8.1"
```

- [ ] 2.4 创建 `scripts/version-kubeovn`：

```bash
#!/bin/bash
KUBEOVN_VERSION="v1.17.0"
```

- [ ] 2.5 创建 `scripts/version-kagent`：

```bash
#!/bin/bash
KAGENT_VERSION="0.9.6"
```

- [ ] 2.6 修改 `scripts/version`，删除 BUILD_QCOW 逻辑（保留 COMMIT/VERSION/TAG/ARCH）
- [ ] 2.7 验证：`source scripts/version-rke2 && echo $RKE2_VERSION`
- [ ] 2.8 提交：`feat: add VDI component version scripts`

---

### 子任务 3：修改 Dockerfile.dapper（Ubuntu + Go 构建环境）

**目标：** 将构建环境从 SUSE/OpenSUSE 改为 Ubuntu/Debian。

**Files:**
- Modify: `Dockerfile.dapper`

**Steps:**

- [ ] 3.1 修改 `Dockerfile.dapper`：

```dockerfile
FROM golang:1.26-bookworm

ARG http_proxy=$http_proxy
ARG https_proxy=$https_proxy
ARG no_proxy=$no_proxy
ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy
ENV no_proxy=$no_proxy

ARG DAPPER_HOST_ARCH
ENV ARCH $DAPPER_HOST_ARCH

# 系统工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl docker.io gzip tar wget zstd squashfs-tools xorriso \
    awk jq mtools dosfstools unzip rsync patch \
    && rm -rf /var/lib/apt/lists/*

# yq
ARG YQ_VERSION=v4.52.5
RUN curl -sfL "https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_${ARCH}" \
    -o /usr/bin/yq && chmod +x /usr/bin/yq

# golangci-lint
RUN go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@v2.12.2

# helm
ARG HELM_VERSION=v3.20.0
RUN curl -sfL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${ARCH}.tar.gz" | \
    tar xz -C /tmp && mv /tmp/linux-${ARCH}/helm /usr/bin/helm && \
    rm -rf /tmp/linux-${ARCH}

# elemental
ARG ELEMENTAL_VERSION=v0.10.0
RUN curl -sfL "https://github.com/rancher/elemental/releases/download/${ELEMENTAL_VERSION}/elemental-${ARCH}" \
    -o /usr/bin/elemental && chmod +x /usr/bin/elemental

ENV DAPPER_ENV REPO TAG DRONE_TAG DRONE_BRANCH ARCH \
    RKE2_VERSION KUBEVIRT_VERSION LONGHORN_VERSION KUBEOVN_VERSION KAGENT_VERSION \
    USE_LOCAL_IMAGES DISABLE_BUILD_NET_INSTALL_ISO
ENV DAPPER_SOURCE /go/src/github.com/vdi-installer/
ENV DAPPER_OUTPUT ./bin ./dist
ENV DAPPER_DOCKER_SOCKET true
ENV DAPPER_RUN_ARGS "-v /run/containerd/containerd.sock:/run/containerd/containerd.sock --privileged"

ENV HOME ${DAPPER_SOURCE}
WORKDIR ${DAPPER_SOURCE}

ENTRYPOINT ["./scripts/entry"]
CMD ["default"]
```

- [ ] 3.2 验证：`docker build -f Dockerfile.dapper -t vdi-installer-builder .`
- [ ] 3.3 提交：`feat: adapt Dockerfile.dapper for Ubuntu + elemental`

---

### 子任务 4：修改 scripts/build（编译安装器）

**目标：** 适配 VDI 版本脚本和 LINKFLAGS。

**Files:**
- Modify: `scripts/build`

**Steps:**

- [ ] 4.1 修改 `scripts/build`，替换版本 source 和 LINKFLAGS：

```bash
#!/bin/bash
set -e

TOP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
SCRIPTS_DIR="${TOP_DIR}/scripts"

cd ${TOP_DIR}

source ${SCRIPTS_DIR}/version-rke2
source ${SCRIPTS_DIR}/version-kubevirt
source ${SCRIPTS_DIR}/version-longhorn
source ${SCRIPTS_DIR}/version-kubeovn
source ${SCRIPTS_DIR}/version-kagent
source ${SCRIPTS_DIR}/version

echo "Installer version: ${VERSION}"
echo "RKE2 version: ${RKE2_VERSION}"
echo "KubeVirt version: ${KUBEVIRT_VERSION}"
echo "Longhorn version: ${LONGHORN_VERSION}"
echo "KubeOVN version: ${KUBEOVN_VERSION}"
echo "kagent version: ${KAGENT_VERSION}"
echo "ARCH: ${ARCH}"

mkdir -p bin

LINKFLAGS="-X github.com/vdi-installer/pkg/config.RKE2Version=${RKE2_VERSION}
           -X github.com/vdi-installer/pkg/config.KubevirtVersion=${KUBEVIRT_VERSION}
           -X github.com/vdi-installer/pkg/config.LonghornVersion=${LONGHORN_VERSION}
           -X github.com/vdi-installer/pkg/config.KubeovnVersion=${KUBEOVN_VERSION}
           -X github.com/vdi-installer/pkg/config.KagentVersion=${KAGENT_VERSION}
           -X github.com/vdi-installer/pkg/version.Version=${VERSION}
           -X github.com/vdi-installer/pkg/version.GitCommit=${COMMIT}"

if [ "$(uname)" = "Linux" ]; then
    OTHER_LINKFLAGS="-extldflags -static -s"
fi

CGO_ENABLED=0 go build -ldflags "$LINKFLAGS $OTHER_LINKFLAGS" -o bin/vdi-installer .

# 复制到 package 目录
mkdir -p package/vdi-os/files/usr/bin
install bin/vdi-installer package/vdi-os/files/usr/bin/
mkdir -p package/vdi-installer
install bin/vdi-installer package/vdi-installer/
```

- [ ] 4.2 验证：`go build -o /dev/null .`（确认 Go 代码编译通过）
- [ ] 4.3 提交：`feat: adapt scripts/build for VDI version injection`

---

### 子任务 5：重写 pkg/config/config.go（VDIConfig 结构体）

**目标：** 将 HarvesterConfig 替换为 VDIConfig，适配 VDI 组件栈。

**Files:**
- Modify: `pkg/config/config.go`

**Steps:**

- [ ] 5.1 创建 `pkg/config/config.go`，定义 VDIConfig 结构体：

```go
package config

import (
    "fmt"
    "net"
    "runtime"
    "strings"

    "github.com/imdario/mergo"
    yipSchema "github.com/rancher/yip/pkg/schema"
    "k8s.io/apimachinery/pkg/util/validation"
)

const (
    SchemeVersion = 1
    SanitizeMask  = "***"
)

const (
    SingleDiskMinSizeGiB   uint64 = 250
    MultipleDiskMinSizeGiB uint64 = 180
    HardMinDataDiskSizeGiB uint64 = 50
    MaxPods                       = 200
)

type NetworkInterface struct {
    Name   string `json:"name,omitempty"`
    HwAddr string `json:"hwAddr,omitempty"`
}

type Network struct {
    Interfaces   []NetworkInterface `json:"interfaces,omitempty"`
    Method       string             `json:"method,omitempty"`
    IP           string             `json:"ip,omitempty"`
    SubnetMask   string             `json:"subnetMask,omitempty"`
    Gateway      string             `json:"gateway,omitempty"`
    DefaultRoute bool               `json:"-"`
    BondOptions  map[string]string  `json:"bondOptions,omitempty"`
    MTU          int                `json:"mtu,omitempty"`
    VlanID       int                `json:"vlanId,omitempty"`
}

type Webhook struct {
    Event   string `json:"event,omitempty"`
    Method  string `json:"method,omitempty"`
    Headers map[string][]string `json:"headers,omitempty"`
    URL     string `json:"url,omitempty"`
    Payload string `json:"payload,omitempty"`
}

type InstallConfig struct {
    Automatic           bool      `json:"automatic,omitempty"`
    Mode                string    `json:"mode,omitempty"`
    Role                string    `json:"role,omitempty"`
    ManagementInterface Network   `json:"managementInterface,omitempty"`
    VIP                 string    `json:"vip,omitempty"`
    VIPMode             string    `json:"vipMode,omitempty"`
    Device              string    `json:"device,omitempty"`
    DataDisk            string    `json:"dataDisk,omitempty"`
    ConfigURL           string    `json:"configUrl,omitempty"`
    Silent              bool      `json:"silent,omitempty"`
    PowerOff            bool      `json:"powerOff,omitempty"`
    Debug               bool      `json:"debug,omitempty"`
    TTY                 string    `json:"tty,omitempty"`
    Webhooks            []Webhook `json:"webhooks,omitempty"`
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

type VDIConfig struct {
    SchemeVersion uint32        `json:"schemeVersion,omitempty"`
    ServerURL     string        `json:"serverUrl,omitempty"`
    Token         string        `json:"token,omitempty"`
    SANS          []string      `json:"sans,omitempty"`
    OS            OSConfig      `json:"os,omitempty"`
    Install       InstallConfig `json:"install,omitempty"`

    RKE2Version     string `json:"rke2Version,omitempty"`
    KubevirtVersion string `json:"kubevirtVersion,omitempty"`
    LonghornVersion string `json:"longhornVersion,omitempty"`
    KubeovnVersion  string `json:"kubeovnVersion,omitempty"`
    KagentVersion   string `json:"kagentVersion,omitempty"`
}

func NewVDIConfig() *VDIConfig {
    return &VDIConfig{}
}

func (c *VDIConfig) DeepCopy() (*VDIConfig, error) {
    newConf := NewVDIConfig()
    if err := mergo.Merge(newConf, c, mergo.WithAppendSlice); err != nil {
        return nil, fmt.Errorf("fail to create copy of %T: %s", *c, err.Error())
    }
    return newConf, nil
}

func (c *VDIConfig) Merge(other VDIConfig) error {
    return mergo.Merge(c, other, mergo.WithAppendSlice)
}

func (c *VDIConfig) GetKubeletArgs() ([]string, error) {
    labelStrs := make([]string, 0, len(c.OS.Labels))
    for name, value := range c.OS.Labels {
        if errs := validation.IsQualifiedName(name); len(errs) > 0 {
            return nil, fmt.Errorf("invalid label name '%s': %s", name, strings.Join(errs, ", "))
        }
        if errs := validation.IsValidLabelValue(value); len(errs) > 0 {
            return nil, fmt.Errorf("invalid label value '%s': %s", value, strings.Join(errs, ", "))
        }
        labelStrs = append(labelStrs, fmt.Sprintf("%s=%s", name, value))
    }
    args := []string{fmt.Sprintf("max-pods=%d", MaxPods)}
    if len(labelStrs) > 0 {
        args = append(args, fmt.Sprintf("node-labels=%s", strings.Join(labelStrs, ",")))
    }
    return args, nil
}

func (n *NetworkInterface) FindNetworkInterfaceNameAndHwAddr() error {
    if n.Name == "" && n.HwAddr != "" {
        hwAddr, err := net.ParseMAC(n.HwAddr)
        if err != nil { return err }
        interfaces, err := net.Interfaces()
        if err != nil { return err }
        for _, iface := range interfaces {
            if iface.HardwareAddr.String() == hwAddr.String() {
                n.Name = iface.Name
                return nil
            }
        }
        return fmt.Errorf("no interface matching hardware address %s found", n.HwAddr)
    }
    if n.Name != "" && n.HwAddr == "" {
        interfaces, err := net.Interfaces()
        if err != nil { return err }
        for _, iface := range interfaces {
            if iface.Name == n.Name {
                n.HwAddr = iface.HardwareAddr.String()
                return nil
            }
        }
        return fmt.Errorf("no interface matching name %s found", n.Name)
    }
    return nil
}

func GenerateBootstrapConfig(config *VDIConfig) (*yipSchema.YipConfig, error) {
    runtimeConfig := yipSchema.Stage{
        Users:     make(map[string]yipSchema.User),
        TimeSyncd: make(map[string]string),
        SSHKeys:   make(map[string][]string),
        Sysctl:    make(map[string]string),
        Environment: make(map[string]string),
    }
    runtimeConfig.Hostname = config.OS.Hostname
    if len(config.OS.NTPServers) > 0 {
        runtimeConfig.TimeSyncd["NTP"] = strings.Join(config.OS.NTPServers, " ")
    }
    runtimeConfig.Users["rancher"] = yipSchema.User{PasswordHash: config.OS.Password}
    runtimeConfig.SSHKeys["rancher"] = config.OS.SSHAuthorizedKeys
    conf := &yipSchema.YipConfig{
        Name: "VDI Configuration",
        Stages: map[string][]yipSchema.Stage{
            "live": {runtimeConfig},
        },
    }
    return conf, nil
}
```

- [ ] 5.2 验证：`go build ./pkg/config/...`
- [ ] 5.3 提交：`feat: add VDIConfig struct replacing HarvesterConfig`

---

### 子任务 6：修改 pkg/config/constants.go（版本常量）

**目标：** 替换 Harvester 版本常量为 VDI 版本常量。

**Files:**
- Modify: `pkg/config/constants.go`

**Steps:**

- [ ] 6.1 替换版本变量：

```go
package config

var (
    // 通过 ldflags 注入
    RKE2Version     string
    KubevirtVersion string
    LonghornVersion string
    KubeovnVersion  string
    KagentVersion   string
)
```

- [ ] 6.2 验证：`go build ./pkg/config/...`
- [ ] 6.3 提交：`feat: replace Harvester version constants with VDI constants`

---

### 子任务 7：修改 main.go（VDI 安装器入口）

**目标：** 替换 Harvester 安装器入口为 VDI 安装器。

**Files:**
- Modify: `main.go`

**Steps:**

- [ ] 7.1 修改 `main.go`：

```go
package main

import (
    "context"
    "log"
    "os"

    "github.com/urfave/cli/v3"
    "github.com/vdi-installer/pkg/console"
    "github.com/vdi-installer/pkg/version"
)

func main() {
    cmd := &cli.Command{
        Name:    "vdi-installer",
        Version: version.FriendlyVersion(),
        Usage:   "Console application to install VDI platform",
        Action: func(context.Context, *cli.Command) error {
            return console.RunConsole()
        },
    }
    if err := cmd.Run(context.Background(), os.Args); err != nil {
        log.Fatalf("Error: %v", err)
    }
}
```

- [ ] 7.2 更新 `go.mod` 中的 module 名称：`github.com/harvester/harvester-installer` → `github.com/vdi-installer`
- [ ] 7.3 验证：`go build -o bin/vdi-installer .`
- [ ] 7.4 提交：`feat: rename installer entry point to vdi-installer`

---

### 子任务 8：修改 go.mod（模块名称和依赖）

**目标：** 更新 Go 模块名称，清理不需要的依赖。

**Files:**
- Modify: `go.mod`

**Steps:**

- [ ] 8.1 修改 `go.mod` 中的 module 名称
- [ ] 8.2 更新所有 import 路径（`github.com/harvester/harvester-installer` → `github.com/vdi-installer`）
- [ ] 8.3 运行 `go mod tidy` 清理不需要的依赖
- [ ] 8.4 验证：`go build ./...`
- [ ] 8.5 提交：`refactor: rename Go module to github.com/vdi-installer`

---

### 子任务 9：修改 pkg/console/install_panels.go（TUI 面板）

**目标：** 适配 VDI 安装模式（首节点/管理节点/工作节点）。

**Files:**
- Modify: `pkg/console/install_panels.go`

**Steps:**

- [ ] 9.1 修改 `addAskCreatePanel`，替换安装模式选项：

```go
// 替换 Harvester 的 Create/Join/Install-only 为 VDI 的三模式
options := []widgets.Option{
    {Value: "first", Text: "Create a new VDI cluster (first node)"},
    {Value: "master", Text: "Join as a management node"},
    {Value: "worker", Text: "Join as a worker node"},
}
```

- [ ] 9.2 修改面板标题和提示文本（Harvester → VDI）
- [ ] 9.3 修改 `addConfirmInstallPanel` 中的确认文本
- [ ] 9.4 验证：`go build ./pkg/console/...`
- [ ] 9.5 提交：`feat: adapt TUI panels for VDI installation modes`

---

### 子任务 10：修改 pkg/console/util.go（安装执行逻辑）

**目标：** 适配 VDI 的 doInstall 流程（RKE2 替代 Rancherd）。

**Files:**
- Modify: `pkg/console/util.go`

**Steps:**

- [ ] 10.1 修改 `doInstall` 函数，替换 Rancherd 配置为 RKE2 配置
- [ ] 10.2 修改 `configureInstalledNode` 函数，适配 RKE2 agent 加入
- [ ] 10.3 修改 `generateEnvAndConfig`，输出 VDI 环境变量
- [ ] 10.4 验证：`go build ./pkg/console/...`
- [ ] 10.5 提交：`feat: adapt doInstall for RKE2 bootstrap`

---

### 子任务 11：创建 RKE2 配置模板

**目标：** 创建 RKE2 server/agent 配置和 HelmChart manifests 的 Go template。

**Files:**
- Create: `pkg/config/templates/rke2-server.yaml`
- Create: `pkg/config/templates/rke2-agent.yaml`
- Create: `pkg/config/templates/helmchart-kube-ovn.yaml`
- Create: `pkg/config/templates/helmchart-longhorn.yaml`
- Create: `pkg/config/templates/helmchart-kubevirt.yaml`
- Create: `pkg/config/templates/helmchart-kagent.yaml`

**Steps:**

- [ ] 11.1 创建 `pkg/config/templates/rke2-server.yaml`：

```yaml
token: {{ printf "%q" .Token }}
tls-san:
  - {{ .VIP }}
cluster-cidr: {{ or .ClusterPodCIDR "10.52.0.0/16" }}
service-cidr: {{ or .ClusterServiceCIDR "10.53.0.0/16" }}
cluster-dns: {{ or .ClusterDNS "10.53.0.10" }}
cni: none
disable:
  - rke2-ingress-nginx
kubelet-arg:
{{- range $arg := .GetKubeletArgs }}
  - {{ printf "%q" $arg }}
{{- end }}
```

- [ ] 11.2 创建 `pkg/config/templates/rke2-agent.yaml`：

```yaml
server: {{ .ServerURL }}
token: {{ printf "%q" .Token }}
kubelet-arg:
{{- range $arg := .GetKubeletArgs }}
  - {{ printf "%q" $arg }}
{{- end }}
```

- [ ] 11.3 创建 HelmChart 模板（kube-ovn、longhorn、kubevirt、kagent）
- [ ] 11.4 验证：`go build ./pkg/config/...`
- [ ] 11.5 提交：`feat: add RKE2 config and HelmChart templates`

---

### 子任务 12：修改 pkg/config/cos.go（cOS/elemental 配置）

**目标：** 适配 VDI 的 cOS 配置，替换 Rancherd 初始化为 RKE2 初始化。

**Files:**
- Modify: `pkg/config/cos.go`

**Steps:**

- [ ] 12.1 修改 `initRancherdStage` → `initRKE2Stage`，输出 RKE2 配置文件
- [ ] 12.2 修改 `genBootstrapResources`，生成 HelmChart manifests（非 Rancherd bootstrap）
- [ ] 12.3 修改 `ConvertToCOS`，适配 VDIConfig
- [ ] 12.4 验证：`go build ./pkg/config/...`
- [ ] 12.5 提交：`feat: adapt cos.go for RKE2 bootstrap`

---

### 子任务 13：创建 package/vdi-os/Dockerfile

**目标：** 基于 Ubuntu 22.04 构建 VDI OS 镜像。

**Files:**
- Create: `package/vdi-os/Dockerfile`
- Create: `package/vdi-os/manifest.yaml`

**Steps:**

- [ ] 13.1 创建 `package/vdi-os/Dockerfile`：

```dockerfile
ARG BASE_OS_IMAGE=ubuntu:22.04
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64

# elemental
ARG ELEMENTAL_VERSION=v0.10.0
RUN curl -sfL "https://github.com/rancher/elemental/releases/download/${ELEMENTAL_VERSION}/elemental-${ARCH}" \
    -o /usr/bin/elemental && chmod +x /usr/bin/elemental

# wharfie
ARG WHARFIE_VERSION=v0.6.8
RUN curl -sfL "https://github.com/rancher/wharfie/releases/download/${WHARFIE_VERSION}/wharfie-${ARCH}" \
    -o /usr/bin/wharfie && chmod +x /usr/bin/wharfie

# 系统组件
RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd systemd-sysv \
    open-iscsi nfs-common \
    conntrack ipvsadm ebtables \
    jq curl wget \
    && rm -rf /var/lib/apt/lists/*

COPY files/ /
COPY vdi-release.yaml /etc/

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"$VDI_PRETTY_NAME\"/g" /etc/os-release
```

- [ ] 13.2 创建 `package/vdi-os/manifest.yaml`：

```yaml
iso:
  bootloader-in-rootfs: true
  label: "VDI_LIVE"
```

- [ ] 13.3 验证：`docker build -f package/vdi-os/Dockerfile -t vdi-os:test package/vdi-os/`
- [ ] 13.4 提交：`feat: add vdi-os Dockerfile based on Ubuntu 22.04`

---

### 子任务 14：创建 scripts/package-vdi-os（OS 镜像 + ISO 构建）

**目标：** 替换 Harvester 的 package-harvester-os 为 VDI 版本。

**Files:**
- Create: `scripts/package-vdi-os`
- Rename: `scripts/package-harvester-os` → `scripts/package-vdi-os`（如果存在）

**Steps:**

- [ ] 14.1 创建 `scripts/package-vdi-os`（参考 Harvester 的 `scripts/package-harvester-os`）：

```bash
#!/bin/bash -e
TOP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
SCRIPTS_DIR="${TOP_DIR}/scripts"
PACKAGE_VDI_OS_DIR="${TOP_DIR}/package/vdi-os"

source ${SCRIPTS_DIR}/version-rke2
source ${SCRIPTS_DIR}/version-kubevirt
source ${SCRIPTS_DIR}/version-longhorn
source ${SCRIPTS_DIR}/version-kubeovn
source ${SCRIPTS_DIR}/version-kagent
source ${SCRIPTS_DIR}/version
source ${SCRIPTS_DIR}/lib/iso

VDI_OS_IMAGE=rancher/vdi-os:${VERSION}
PRETTY_NAME="VDI ${VERSION}"

# 生成 vdi-release.yaml
cat > ${PACKAGE_VDI_OS_DIR}/vdi-release.yaml <<EOF
vdi: ${VERSION}
installer: ${COMMIT}
os: ${PRETTY_NAME}
rke2: ${RKE2_VERSION}
kubevirt: ${KUBEVIRT_VERSION}
longhorn: ${LONGHORN_VERSION}
kubeovn: ${KUBEOVN_VERSION}
kagent: ${KAGENT_VERSION}
EOF

# 构建 OS 镜像
cd ${PACKAGE_VDI_OS_DIR}
docker build --pull \
    --build-arg BASE_OS_IMAGE="ubuntu:22.04" \
    --build-arg VDI_PRETTY_NAME="${PRETTY_NAME}" \
    --build-arg ARCH="${ARCH}" \
    -t ${VDI_OS_IMAGE} .

# 提取 kernel/initrd
ARTIFACTS_DIR="${TOP_DIR}/dist/artifacts"
mkdir -p ${ARTIFACTS_DIR}
KERNEL=$(docker run --rm ${VDI_OS_IMAGE} readlink -f /boot/vmlinuz)
INITRD=$(docker run --rm ${VDI_OS_IMAGE} readlink -f /boot/initrd)
docker create --cidfile=os-img-container ${VDI_OS_IMAGE} -- tail -f /dev/null
docker cp $(<os-img-container):${KERNEL} ${ARTIFACTS_DIR}/vdi-vmlinuz-${ARCH}
docker cp $(<os-img-container):${INITRD} ${ARTIFACTS_DIR}/vdi-initrd-${ARCH}
docker rm $(<os-img-container) && rm -f os-img-container

# 构建 ISO
ISO_PREFIX="vdi-${VERSION}-${ARCH}"
elemental build-iso --config-dir "${PACKAGE_VDI_OS_DIR}" --debug \
    "docker:${VDI_OS_IMAGE}" --local \
    -n "${ISO_PREFIX}" -o "${ARTIFACTS_DIR}" \
    --overlay-iso "${PACKAGE_VDI_OS_DIR}/iso" \
    -x "-comp xz" --platform "linux/${ARCH}"

# 生成校验和
cd ${ARTIFACTS_DIR}
sha512sum vdi-* > ${ISO_PREFIX}.sha512
```

- [ ] 14.2 验证脚本语法：`bash -n scripts/package-vdi-os`
- [ ] 14.3 提交：`feat: add package-vdi-os script for OS image and ISO build`

---

### 子任务 15：创建 scripts/build-bundle（离线资源下载）

**目标：** 替换 Harvester 的 build-bundle 为 VDI 组件版本。

**Files:**
- Modify: `scripts/build-bundle`

**Steps:**

- [ ] 15.1 修改 `scripts/build-bundle`，替换组件栈：

```bash
#!/bin/bash
set -e

TOP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
SCRIPTS_DIR="${TOP_DIR}/scripts"
PACKAGE_VDI_OS_DIR="${TOP_DIR}/package/vdi-os"

source ${SCRIPTS_DIR}/version-rke2
source ${SCRIPTS_DIR}/version-kubevirt
source ${SCRIPTS_DIR}/version-longhorn
source ${SCRIPTS_DIR}/version-kubeovn
source ${SCRIPTS_DIR}/version-kagent
source ${SCRIPTS_DIR}/version
source ${SCRIPTS_DIR}/lib/image

BUNDLE_DIR="${PACKAGE_VDI_OS_DIR}/iso/bundle"
IMAGES_DIR="${BUNDLE_DIR}/vdi/images"
IMAGES_LISTS_DIR="${BUNDLE_DIR}/vdi/images-lists"
CHARTS_DIR="${BUNDLE_DIR}/charts"
mkdir -p ${IMAGES_DIR} ${IMAGES_LISTS_DIR} ${CHARTS_DIR}

# RKE2 镜像
RKE2_IMAGES_URL="https://github.com/rancher/rke2/releases/download/${RKE2_VERSION}"
RKE2_VERSION_NORMALIZED=${RKE2_VERSION/+/-}
image_list_file="${IMAGES_LISTS_DIR}/rke2-images-${RKE2_VERSION_NORMALIZED}.txt"
get_url "${RKE2_IMAGES_URL}/rke2-images.linux-amd64.txt" $image_list_file
save_image "kubernetes" $BUNDLE_DIR $image_list_file ${IMAGES_DIR}

# KubeVirt 镜像
# ... 类似逻辑

# Longhorn 镜像
# ... 类似逻辑

# Kube-OVN chart
helm pull oci://kubeovn/kube-ovn --version ${KUBEOVN_VERSION} -d ${CHARTS_DIR}

# Longhorn chart
helm repo add longhorn https://charts.longhorn.io 2>/dev/null || true
helm pull longhorn/longhorn --version ${LONGHORN_VERSION#v} -d ${CHARTS_DIR}

# kagent chart
helm pull oci://ghcr.io/kagent-dev/charts/kagent --version ${KAGENT_VERSION} -d ${CHARTS_DIR}

# Helm repo index
helm repo index ${CHARTS_DIR}

# 生成 metadata.yaml
# ... 使用 add_image_list_to_metadata 函数

# 校验
generate_checksums "${BUNDLE_DIR}" "${BUNDLE_DIR}/checksums.sha256"
```

- [ ] 15.2 验证脚本语法：`bash -n scripts/build-bundle`
- [ ] 15.3 提交：`feat: adapt build-bundle for VDI components`

---

### 子任务 16：创建 HelmChart manifests（OS 内嵌）

**目标：** 创建 RKE2 HelmChart manifests，打包到 OS 镜像中。

**Files:**
- Create: `package/vdi-os/files/var/lib/rancher/rke2/server/manifests/10-kube-ovn.yaml`
- Create: `package/vdi-os/files/var/lib/rancher/rke2/server/manifests/20-longhorn.yaml`
- Create: `package/vdi-os/files/var/lib/rancher/rke2/server/manifests/30-kubevirt.yaml`
- Create: `package/vdi-os/files/var/lib/rancher/rke2/server/manifests/40-kagent.yaml`

**Steps:**

- [ ] 16.1 创建目录结构
- [ ] 16.2 创建 Kube-OVN HelmChart：

```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: kube-ovn
  namespace: kube-system
spec:
  chart: /var/lib/rancher/rke2/server/charts/kube-ovn.tgz
  targetNamespace: kube-system
  createNamespace: true
  bootstrap: true
  valuesContent: |-
    FUNC_OPTS: "--enable-mirror=false"
```

- [ ] 16.3 创建 Longhorn HelmChart
- [ ] 16.4 创建 KubeVirt manifest（KubeVirt 使用 CRD 而非 HelmChart）
- [ ] 16.5 创建 kagent HelmChart
- [ ] 16.6 验证 YAML 语法：`yq eval '.' package/vdi-os/files/var/lib/rancher/rke2/server/manifests/*.yaml`
- [ ] 16.7 提交：`feat: add HelmChart manifests for VDI components`

---

### 子任务 17：修改 pkg/config/templates.go（模板注册）

**目标：** 注册新的 RKE2 配置和 HelmChart 模板。

**Files:**
- Modify: `pkg/config/templates.go`

**Steps:**

- [ ] 17.1 注册新模板（rke2-server.yaml、rke2-agent.yaml、helmchart-*.yaml）
- [ ] 17.2 删除 Harvester 特有模板注册（rancherd-*.yaml、rke2-90-harvester-*.yaml）
- [ ] 17.3 验证：`go build ./pkg/config/...`
- [ ] 17.4 提交：`feat: register RKE2 and HelmChart templates`

---

### 子任务 18：创建 vdi-cluster-repo 镜像

**目标：** 创建 Helm Chart 仓库镜像（nginx + charts）。

**Files:**
- Create: `package/vdi-cluster-repo/Dockerfile`

**Steps:**

- [ ] 18.1 创建 `package/vdi-cluster-repo/Dockerfile`：

```dockerfile
FROM nginx:alpine
COPY charts/ /usr/share/nginx/html/charts/
RUN cd /usr/share/nginx/html/charts && \
    [ -f index.yaml ] || helm repo index .
EXPOSE 80
```

- [ ] 18.2 创建 `scripts/package-vdi-repo` 脚本
- [ ] 18.3 验证：`docker build -f package/vdi-cluster-repo/Dockerfile -t vdi-repo:test .`
- [ ] 18.4 提交：`feat: add vdi-cluster-repo Dockerfile`

---

### 子任务 19：修改 Makefile（适配新 target）

**目标：** 确保 Makefile 自动发现新的 scripts/ target。

**Files:**
- Verify: `Makefile`（应无需修改，TARGETS := $(shell ls scripts) 自动适配）

**Steps:**

- [ ] 19.1 验证 `make default` 能找到所有新 target
- [ ] 19.2 验证 `make shell` 能进入构建容器
- [ ] 19.3 提交：无需提交（验证通过即可）

---

### 子任务 20：创建 images/allow.yaml（允许的镜像仓库）

**目标：** 定义 VDI 允许下载的镜像仓库列表。

**Files:**
- Create: `scripts/images/allow.yaml`

**Steps:**

- [ ] 20.1 创建 `scripts/images/allow.yaml`：

```yaml
kubernetes:
  - registry.k8s.io
  - docker.io/rancher

kubevirt:
  - quay.io/kubevirt

longhorn:
  - longhornio/longhorn-manager
  - longhornio/longhorn-engine
  - longhornio/longhorn-ui
  - longhornio/longhorn-instance-manager
  - longhornio/support-bundle-kit
  - longhornio/csi-attacher
  - longhornio/csi-provisioner
  - longhornio/csi-resizer
  - longhornio/csi-snapshotter
  - longhornio/livenessprobe
  - longhornio/csi-node-driver-registrar

kubeovn:
  - docker.io/kubeovn/kube-ovn

kagent:
  - ghcr.io/kagent-dev
  - docker.io/library/postgres
```

- [ ] 20.2 验证 YAML 语法
- [ ] 20.3 提交：`feat: add allowed image repositories list`

---

### 子任务 21：创建 harv-install 等效脚本（vdi-install）

**目标：** 创建 VDI 的 OS 安装脚本，对应 Harvester 的 harv-install。

**Files:**
- Create: `package/vdi-os/files/usr/sbin/vdi-install`

**Steps:**

- [ ] 21.1 创建 `package/vdi-os/files/usr/sbin/vdi-install`（参考 Harvester 的 harv-install）：

```bash
#!/bin/bash -e
# VDI OS 安装脚本
# 对应 Harvester 的 harv-install，适配 RKE2 + VDI 组件

ISOMNT=/run/initramfs/live
TARGET=/run/cos/target
DATA_DISK_FSLABEL="VDI_LH_DEFAULT"

# ... 参考 harv-install 的完整逻辑，替换：
# - HARVESTER_* 环境变量 → VDI_*
# - bundle/harvester/ → bundle/vdi/
# - rancherd → rke2
# - RKE2 预加载逻辑保留
# - VDI 镜像预加载逻辑新增

trap cleanup exit

# 阶段 1：环境准备
blkdeactivate --lvmoptions wholevg,retry --dmoptions force,retry || true
clear_disk_label

# 阶段 2：OS 安装
elemental install --config-dir ${ELEMENTAL_CONFIG_DIR} --debug

# 阶段 3：数据盘格式化
do_data_disk_format

# 阶段 4：挂载已安装的 OS
do_detect
do_mount

# 阶段 5：镜像预加载（RKE2 + VDI 组件）
do_preload

# 阶段 6：配置保存
save_configs
save_nm_state

# 阶段 7：引导配置
update_grub_settings
save_installation_log
```

- [ ] 21.2 验证脚本语法：`bash -n package/vdi-os/files/usr/sbin/vdi-install`
- [ ] 21.3 提交：`feat: add vdi-install script for OS installation`

---

### 子任务 22：端到端构建验证

**目标：** 验证完整构建流程通过。

**Steps:**

- [ ] 22.1 `make build-builder` — 构建 Dapper 容器
- [ ] 22.2 `make build` — 编译 Go 安装器
- [ ] 22.3 `make build-bundle` — 下载离线资源
- [ ] 22.4 `make package-vdi-os` — 构建 OS 镜像 + ISO
- [ ] 22.5 `make package-vdi-repo` — 构建 Helm Chart 仓库镜像
- [ ] 22.6 `make package-vdi-installer` — 构建 installer 镜像
- [ ] 22.7 验证 ISO 文件存在且大小合理（>1GB）
- [ ] 22.8 提交：`test: verify full build pipeline`

---

### 子任务 23：QEMU 引导测试

**目标：** 验证 ISO 可以启动并进入 TUI 安装器。

**Steps:**

- [ ] 23.1 `make test-iso` — QEMU 图形模式启动 ISO
- [ ] 23.2 验证 GRUB 菜单显示
- [ ] 23.3 验证 TUI 安装器启动
- [ ] 23.4 验证安装模式选择（首节点/管理节点/工作节点）
- [ ] 23.5 提交：`test: verify ISO boots and TUI launches`

---

## 执行顺序

```
子任务 1 (Fork 清理)
  ↓
子任务 2 (version 脚本) → 子任务 3 (Dockerfile.dapper) → 子任务 4 (scripts/build)
  ↓
子任务 5 (VDIConfig) → 子任务 6 (constants) → 子任务 7 (main.go) → 子任务 8 (go.mod)
  ↓
子任务 9 (TUI 面板) → 子任务 10 (doInstall)
  ↓
子任务 11 (RKE2 模板) → 子任务 12 (cos.go) → 子任务 17 (templates.go)
  ↓
子任务 13 (vdi-os Dockerfile) → 子任务 14 (package-vdi-os)
  ↓
子任务 15 (build-bundle) → 子任务 16 (HelmChart manifests) → 子任务 18 (cluster-repo)
  ↓
子任务 19 (Makefile 验证) → 子任务 20 (allow.yaml) → 子任务 21 (vdi-install)
  ↓
子任务 22 (端到端构建) → 子任务 23 (QEMU 测试)
```
