# CLAUDE.md — iso-builder AI 开发指南

## 项目概述

VDI 离线 ISO 构建系统，产出一个包含完整离线部署资源的 Live ISO。
启动后通过 TUI 引导用户在无互联网环境中部署 VDI 集群。

## 技术栈

- **构建环境**: Docker + Dapper (Dockerfile.dapper)
- **Live 系统**: Ubuntu 22.04 + live-build (bootstrap/chroot) + squashfs
- **离线镜像**: docker-archive + zstd 压缩 (skopeo 下载，ctr 导入)
- **ISO 打包**: xorriso (BIOS isolinux + UEFI GRUB 双模式)
- **TUI**: Python 3 + curses 标准库（零外部依赖，curses.wrapper() 保证终端状态恢复）
- **PXE**: dnsmasq (DHCP/TFTP) + python3 http.server

## 项目结构

```
iso-builder/
├── Dockerfile.dapper    # 构建环境容器
├── Makefile             # 三阶段 pipeline 入口
├── manifest.yaml        # 离线资源清单（唯一真相来源）
│
├── scripts/             # 构建和部署时脚本
│   ├── common.sh        # 共享函数库
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
├── iso/                 # ISO 结构配置模板
│   ├── boot/grub/       # GRUB 模板
│   └── isolinux/        # isolinux 模板
│
├── pxe/                 # PXE 配置模板
├── tui/                 # TUI 安装器
├── configs/             # 配置模板
└── cache/               # 构建缓存 (gitignore)
```

## 核心构建命令

```bash
make iso               # 完整构建（三阶段 pipeline）
make build-rootfs      # 阶段 1: 构建 rootfs
make build-bundle      # 阶段 2: 下载离线资源
make package-iso       # 阶段 3: 打包 ISO
make download          # 别名: make build-bundle
make shell             # 进入构建容器调试
make verify            # 校验离线资源 checksums
make clean             # 清理构建产物（保留 bundle）
make distclean         # 清理全部（含缓存）
```

## 三阶段 Pipeline

```
阶段 1: build-rootfs  → cache/rootfs/     (完整 chroot)
阶段 2: build-bundle  → cache/bundle/     (离线资源 + metadata.yaml)
阶段 3: package-iso   → dist/*.iso        (最终 ISO + PXE 产物)
```

增量构建支持：
- `SKIP_BOOTSTRAP=1 make build-rootfs` — 跳过 debootstrap
- `make package-iso-only` — 仅重新打包 ISO
- `make build-bundle-only` — 仅更新离线资源

## 关键设计决策

1. **manifest.yaml 是唯一真相来源**: 所有组件版本、镜像列表、下载 URL 只在此文件定义
2. **三阶段分离**: 每阶段独立可缓存、可调试
3. **metadata.yaml 索引**: bundle 的结构化索引，支持快速查找和校验
4. **docker-archive + zstd**: 镜像格式稳定，ctr import 可靠，压缩率高
5. **OFFLINE_BASE 条件回退**: 部署脚本兼容 bundle/ 和 offline/ 路径（检测优先 `/cdrom/bundle`）
6. **TUI 通过 symlink**: /opt/vdi/tui → /cdrom/tui，不复制到 squashfs
7. **PXE 仅用于 Worker**: Master 必须手动部署

## 部署执行约定（TUI 运行时）

- **配置生成路径**：TUI 收集的配置（`config.yaml`/`hosts`/`env-config.sh`）生成到 `/etc/vdi/`（非 root 回退 `~/vdi-config`），通过 `env-config.sh` 的 `VDI_CONFIG_DIR` 暴露。部署脚本必须从 `$VDI_CONFIG_DIR` 读取——**不要硬编码 `/cdrom/scripts/deploy/`（只读，只有 `.template`）**，否则 kk/helm 拿不到配置而失败。
- **子进程流式执行**：部署步骤必须走 `DeployEngine._run_streaming()`（`Popen` 逐行读 + ring buffer），不要用 `subprocess.run`（阻塞会让 ProgressBar 日志面板冻结）。`_run_streaming` 同时落盘日志和喂实时缓冲。
- **KubeKey v4 配置体系**（踩坑警示，曾因假设 v1alpha2 导致部署失败）：kk v4.0.4 用 `Config`+`Inventory` 分离设计，命令是 `kk create cluster -c config.yaml -i inventory.yaml`（**不是 `-f`，也没有 `--skip-check-os`**）。`config.yaml` 是 `kind: Config`（apiVersion `v1`，下划线字段 `kube_version`/`control_plane_endpoint`/`container_manager`），`inventory.yaml` 是 `kind: Inventory`（`hosts.<name>.connector` + `groups.kube_control_plane/etcd`，Kubespray 风格）。不要用旧版 `v1alpha2`/`Cluster`/`roleGroups` 格式。改前务必 `kk create config` 看 ground truth。
- **失败可恢复**：步骤失败后 `ErrorScreen` 返回 `retry`/`skip`/`exit`，`ProgressScreen` 消费——不要丢弃返回值直接 `sys.exit(1)`。

## 注意事项

- ISO 目标大小 < 8GB（不含 Windows VM 镜像）
- 仅支持 amd64 (x86_64)
- 目标 OS: Ubuntu 22.04 LTS
- TUI 运行需要 root 权限和 TTY 环境
