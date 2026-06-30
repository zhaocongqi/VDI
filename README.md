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
| ISO 构建 | kickstart + xorriso（BCLinux DVD + anaconda） |
| 基础 OS | BCLinux 21.10 U5 |

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
make build-bundle       # 下载离线资源（RKE2 二进制/镜像/charts）
make package-vdi-iso    # 构建安装型 ISO（BCLinux DVD + kickstart + xorriso）
```

在执行 `make build-bundle` 时，支持使用 `LOCAL_PKG_DIR` 环境变量配置本地离线包的检索路径（例如 `export LOCAL_PKG_DIR=/opt/vdi-pkgs`）。若本地目录存在与所下载的目标或 URL 文件名一致的文件，将优先进行本地拷贝；否则执行纯净的无代理 `curl` 正常下载。若未设置此环境变量，默认会尝试从项目根目录下的 `cache/downloads` 目录进行检索拷贝。

ISO 产物位于 `dist/artifacts/vdi-$VERSION-$ARCH.iso`。

### 测试 ISO

当前 ISO 仅支持 UEFI 引导（通过字节级注入 grubx64.efi 到 EFI 引导镜像）。

```bash
# UEFI 模式（需 OVMF 固件）
qemu-system-x86_64 -m 4096 -smp 2 \
    -cdrom dist/artifacts/vdi-*.iso \
    -boot d -bios /usr/share/ovmf/OVMF.fd -nographic
```

## 安装流程

1. **ISO 引导** — BCLinux DVD ISO 引导，`inst.ks` 加载 kickstart 模板
2. **`%pre` 配置收集** — ks `%pre` 调 vdi-installer：交互模式弹 gocui TUI（模式/网络/磁盘/VIP/密码/role）；自动模式用预置配置。渲染 ks 写 `/tmp/ks-include.cfg`
3. **anaconda 装机** — `%include` 展开：LVM 分区 + 装包 + `%post` 解压 RKE2、写 config/manifests、enable rke2-server/agent
4. **首次启动** — RKE2 首启自动导入离线镜像，HelmChart 控制器部署 KubeVirt/Longhorn/Kube-OVN/kagent

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
│   ├── version-*        # 组件版本
│   ├── build            # 编译 Go 安装器
│   ├── build-bundle     # 下载离线资源（RKE2 二进制/镜像/charts）
│   ├── package-vdi-iso  # xorriso 重建 BCLinux DVD ISO（注入 ks + bundle）
│   └── package-vdi-repo # 构建 Helm Chart 仓库镜像
├── package/             # Docker 镜像定义
│   ├── vdi-os/          # BCLinux 21.10 U5 + VDI 安装器文件
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
scripts/version-kubeovn   # KUBEOVN_VERSION="v1.16.2"
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
