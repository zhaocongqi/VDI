# VDI 离线安装器

基于 [Harvester Installer](https://github.com/harvester/harvester-installer) 架构改造的 VDI (Virtual Desktop Infrastructure) 离线安装器，使用 RKE2 + HelmChart CRD 声明式部署 KubeVirt/Longhorn/Kube-OVN/kagent 组件栈。

## 技术栈

| 组件 | 技术 |
|------|------|
| K8s 运行时 | RKE2 (Rancher Kubernetes Engine 2) |
| addon 管理 | HelmChart CRD (helm.cattle.io/v1) |
| 网络 | Kube-OVN |
| 存储 | Longhorn |
| 虚拟化 | KubeVirt |
| AI Agent | kagent |
| 安装器 | Go + gocui |
| ISO 构建 | elemental + xorriso |
| 构建系统 | Dapper (Docker-in-Docker) |

## 快速开始

### 前置条件

- Docker
- Git
- Go 1.26+
- Helm

### 构建 ISO

```bash
# 完整构建（编译 + 下载离线资源 + 打包 ISO）
make default

# 或分步执行
make build              # 编译 Go 安装器
make build-bundle       # 下载离线资源
make package-vdi-os     # 构建 OS 镜像 + ISO
```

ISO 产物位于 `dist/artifacts/vdi-$VERSION-$ARCH.iso`。

### 测试 ISO

```bash
# BIOS 模式
make test-iso

# UEFI 模式
qemu-system-x86_64 -m 4096 -smp 2 \
    -cdrom dist/artifacts/vdi-*.iso \
    -boot d -bios /usr/share/ovmf/OVMF.fd -nographic
```

## 安装流程

1. **TUI 配置收集** — 选择安装模式（首节点/管理节点/工作节点），配置网络、磁盘、VIP
2. **配置生成** — 生成 RKE2 config.yaml + HelmChart manifests
3. **OS 安装** — elemental install 将 OS 写入目标磁盘
4. **镜像预加载** — 将离线镜像导入目标 OS 的 containerd
5. **首次启动** — RKE2 server/agent 启动，HelmChart 控制器自动部署组件

## 目录结构

```
VDI/
├── main.go              # 安装器入口
├── Makefile             # Dapper 构建系统
├── Dockerfile.dapper    # Ubuntu 22.04 + Go + elemental 构建环境
├── go.mod / go.sum      # Go module (vdi-installer)
├── pkg/                 # Go 代码
│   ├── config/          # VDIConfig 结构体 + RKE2 模板
│   ├── console/         # gocui TUI 安装器
│   ├── preflight/       # 硬件预检
│   ├── util/            # 工具函数
│   └── widgets/         # gocui 控件
├── scripts/             # 构建脚本
│   ├── version-*        # 组件版本
│   ├── build            # 编译 Go 安装器
│   ├── build-bundle     # 下载离线资源
│   ├── package-vdi-os   # 构建 OS 镜像 + ISO
│   └── package-vdi-repo # 构建 Helm Chart 仓库镜像
├── package/             # Docker 镜像定义
│   ├── vdi-os/          # Ubuntu 22.04 + RKE2 + HelmChart manifests
│   ├── vdi-installer/   # 安装器二进制镜像
│   └── vdi-cluster-repo/# Helm Chart 仓库
└── docs/                # 设计文档 + 实施计划
```

## 版本管理

版本号通过 `scripts/version-*` 脚本管理，Go 二进制通过 ldflags 注入：

```bash
scripts/version-rke2      # RKE2_VERSION="v1.31.4+rke2r1"
scripts/version-kubevirt  # KUBEVIRT_VERSION="v1.5.0"
scripts/version-longhorn  # LONGHORN_VERSION="v1.8.1"
scripts/version-kubeovn   # KUBEOVN_VERSION="v1.17.0"
scripts/version-kagent    # KAGENT_VERSION="0.9.6"
```

## License

Copyright (c) 2026 [SUSE, LLC.](https://www.suse.com/)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

[http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0)

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
