# VDI 离线 ISO 构建系统

构建一个一体化 Live ISO，在离线环境（有局域网、无互联网）下通过 TUI 菜单引导部署 VDI 集群。

## 功能特性

- **单一 ISO 介质**：包含所有离线资源（容器镜像、Helm Chart、二进制工具、系统包）
- **TUI 菜单引导**：类似 Ubuntu Server 安装体验，4 种部署模式
- **PXE 批量部署**：Worker 节点可通过网络自动安装并加入集群
- **三阶段 Pipeline**：构建过程分阶段可缓存、可增量、可独立调试
- **可重复构建**：基于 Dapper 容器化构建，确保环境一致

## 快速开始

### 构建前提

- Docker 已安装
- 互联网连接（构建时下载资源）
- 磁盘空间 > 20GB

### 构建 ISO

```bash
# 完整构建（三阶段 pipeline）
make iso

# 或分步执行
make build-rootfs      # 阶段 1: 构建 rootfs
make build-bundle      # 阶段 2: 下载离线资源
make package-iso       # 阶段 3: 打包 ISO
```

### 增量构建

```bash
make package-iso-only  # 仅重新打包 ISO（不重建 rootfs/bundle）
make build-bundle-only # 仅更新离线资源
SKIP_BOOTSTRAP=1 make build-rootfs  # 跳过 debootstrap（使用缓存）
```

### 构建产物

```
dist/
├── vdi-offline-v1.0.0.iso           # ISO 镜像
├── vdi-offline-v1.0.0.iso.sha256    # SHA256 校验和
├── version.yaml                      # 构建元数据
└── pxe/                              # PXE 启动产物
    ├── vmlinuz
    ├── initrd
    └── rootfs.squashfs
```

### 使用 ISO

1. 将 ISO 写入 USB 或挂载为虚拟光驱
2. 从 ISO 启动进入 Live 环境
3. TUI 安装器自动启动
4. 选择部署模式并配置参数
5. 确认后自动执行部署

## 部署模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| 全新安装 | 安装 Ubuntu OS + 部署 VDI 集群 | 裸机部署 Master 节点 |
| 追加部署 | 在已有 OS 上部署 VDI 集群 | 已安装系统的服务器 |
| 添加节点 | 作为 Worker 加入已有集群 | 扩展集群节点 |
| PXE 服务 | 启动 PXE 服务器 | 批量部署 Worker 节点 |

## 三阶段 Pipeline

```
阶段 1: build-rootfs  → cache/rootfs/     (完整 chroot 目录树)
阶段 2: build-bundle  → cache/bundle/     (离线资源 + metadata.yaml)
阶段 3: package-iso   → dist/*.iso        (最终 ISO + PXE 产物)
```

- **阶段 1** 使用 live-build 进行 debootstrap + chroot，产出完整 rootfs
- **阶段 2** 通过 skopeo 下载镜像（docker-archive + zstd）、下载二进制/Chart/Manifest/deb
- **阶段 3** 创建 squashfs + bootloader（GRUB/isolinux 模板）+ xorriso 打包

## 离线资源清单

通过 `manifest.yaml`（项目根目录）管理所有离线资源：

- **K8s 核心**: v1.34.3（apiserver、controller-manager、scheduler、proxy、etcd、coredns）
- **kube-vip**: v0.7.2（API Server HA）
- **Kube-OVN**: v1.17.0（CNI 网络插件）
- **Longhorn**: v1.8.1（分布式块存储）
- **KubeVirt**: v1.5.0 + CDI v1.61.0（虚拟化运行时）
- **kagent**: 0.9.6（AI Agent 框架）

## 开发调试

```bash
make shell       # 进入构建容器交互 shell
make verify      # 校验离线资源完整性
make clean       # 清理构建产物（保留缓存）
make distclean   # 清理全部（含缓存）
```

## 项目结构

```
iso-builder/
├── Dockerfile.dapper    # 构建环境容器
├── Makefile             # 三阶段 pipeline 入口
├── manifest.yaml        # 离线资源清单（唯一真相来源）
│
├── scripts/             # 构建和部署时脚本
│   ├── common.sh        # 共享函数
│   ├── lib/             # 共享函数模块
│   │   ├── image.sh     # 镜像拉取/保存/校验
│   │   ├── iso.sh       # xorriso/EFI 封装
│   │   └── template.sh  # 模板渲染
│   ├── build-rootfs/    # 阶段 1: rootfs 构建
│   ├── build-bundle/    # 阶段 2: 离线资源打包
│   └── package-iso/     # 阶段 3: ISO 打包
│
├── rootfs/              # rootfs 配置
│   ├── package-lists/   # apt 包列表
│   ├── hooks/           # chroot hooks
│   └── includes.chroot/ # 额外文件
│
├── iso/                 # bootloader 模板
│   ├── boot/grub/       # GRUB 模板
│   └── isolinux/        # isolinux 模板
│
├── pxe/                 # PXE 配置模板
├── tui/                 # TUI 安装器 (Python)
├── configs/             # 配置模板
└── cache/               # 构建缓存 (gitignore)
```

## 许可证

内部项目，未公开许可。
