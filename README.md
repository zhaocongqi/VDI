# VDI 离线安装器

基于 BCLinux + Anaconda Addon 架构的 VDI (Virtual Desktop Infrastructure) 离线安装器，使用 RKE2 + HelmChart CRD 声明式部署 KubeVirt/Longhorn/Kube-OVN/kagent 组件栈。

## 技术栈

| 组件 | 技术 |
|------|------|
| K8s 运行时 | RKE2 (Rancher Kubernetes Engine 2) |
| addon 管理 | HelmChart CRD (helm.cattle.io/v1) |
| 网络 | Kube-OVN |
| 存储 | Longhorn |
| 虚拟化 | KubeVirt |
| AI Agent | kagent |
| 安装 GUI | Anaconda Addon (Python + Gtk3 + D-Bus) |
| ISO 构建 | kickstart + xorriso（BCLinux DVD + anaconda） |
| 基础 OS | BCLinux 21.10 U5 |

## 快速开始

### 前置条件

- Docker
- BCLinux ISO（客户提供）：放至 `dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso`

### 构建 ISO

```bash
# 完整构建（编译 + 下载离线资源 + 打包 ISO）
make default

# 或分步执行
make build              # 编译 Go 版本 CLI
make build-bundle       # 下载离线资源（RKE2 二进制/镜像/charts）
make package-vdi-iso    # 构建安装型 ISO（BCLinux DVD + kickstart + xorriso）
```

在执行 `make build-bundle` 时，支持使用 `LOCAL_PKG_DIR` 环境变量配置本地离线包的检索路径（例如 `export LOCAL_PKG_DIR=/opt/vdi-pkgs`）。若本地目录存在与所下载的目标或 URL 文件名一致的文件，将优先进行本地拷贝；否则执行纯净的无代理 `curl` 正常下载。若未设置此环境变量，默认会尝试从项目根目录下的 `cache/downloads` 目录进行检索拷贝。

ISO 产物位于 `dist/artifacts/vdi-$VERSION-$ARCH.iso`。

### 测试 ISO

```bash
# UEFI 模式（需 OVMF 固件）
./scripts/qemu-test-ks dist/artifacts/vdi-*.iso uefi

# BIOS 模式
./scripts/qemu-test-ks dist/artifacts/vdi-*.iso bios
```

## 安装流程

1. **ISO 引导** — BCLinux DVD ISO 引导，`inst.ks` 加载 kickstart 模板
2. **Anaconda Addon 图形化安装** — 加载 VDI Addon，提供网卡/Bond/IP/VIP 配置 GUI
3. **`execute` 阶段全量写盘** — Anaconda 生命周期钩子自动完成：网络持久化、RKE2 离线部署、数据盘格式化挂载
4. **首次启动** — RKE2 首启自动导入离线镜像，HelmChart 控制器部署 KubeVirt/Longhorn/Kube-OVN/kagent

## 目录结构

```
VDI/
├── main.go              # Go 版本输出 CLI
├── Makefile             # Dapper 构建系统
├── Dockerfile.dapper    # 构建容器环境
├── pkg/version/         # 版本信息（ldflags 注入）
├── scripts/             # 构建脚本（Makefile 自动生成同名 target）
│   ├── version-*        # 组件版本
│   ├── build            # 编译 Go CLI
│   ├── build-bundle     # 下载离线资源
│   ├── package-vdi-iso  # 构建 ISO
│   ├── hot-reload-addon # Addon 热重载
│   └── qemu-test-ks    # QEMU 装机验证
├── package/vdi-os/
│   ├── ks/ks.cfg        # 静态 kickstart 模板
│   ├── iso/bundle/      # 离线资源（.gitignore 忽略）
│   └── anaconda/addons/vdi/  # Anaconda Addon Python 插件
└── docs/                # 设计文档
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
