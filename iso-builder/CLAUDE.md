# CLAUDE.md — iso-builder AI 开发指南

## 项目概述

VDI 离线 ISO 构建系统，产出一个包含完整离线部署资源的 Live ISO。
启动后通过 TUI 引导用户在无互联网环境中部署 VDI 集群。

## 技术栈

- **构建环境**: Docker + Dapper (Dockerfile.dapper)
- **Live 系统**: Ubuntu 22.04 + debootstrap + squashfs
- **TUI**: Python 3 + whiptail（无额外 pip 依赖）
- **PXE**: dnsmasq (DHCP/TFTP) + python3 http.server
- **离线镜像**: OCI 目录格式（skopeo 下载，ctr 导入）

## 项目结构

```
iso-builder/
├── Dockerfile.dapper    # 构建环境容器
├── Makefile             # 构建入口（make iso / make download）
├── scripts/             # 构建和部署时脚本
│   ├── build-iso        # 主构建编排
│   ├── create-live      # 创建 Ubuntu Live 根文件系统
│   ├── generate-iso     # xorriso 打包 ISO
│   ├── download-*       # 各类离线资源下载
│   ├── integrate-*      # 资源集成到 ISO
│   ├── load-offline-images  # [部署时] 导入镜像到 containerd
│   ├── setup-local-repo    # [部署时] 配置本地 APT 源
│   └── common.sh       # 共享函数库
├── tui/                 # TUI 安装器
│   ├── installer.py     # 主程序入口
│   ├── screens/         # 各界面模块
│   ├── backend/         # 配置生成和部署引擎
│   └── utils/           # whiptail 封装、校验、日志、离线管理
├── pxe/                 # PXE 网络安装服务
│   └── start-pxe.sh     # PXE 服务启动脚本
├── configs/             # 配置模板
│   ├── env-config.sh    # 离线环境变量模板
│   └── preseed.cfg      # Ubuntu 自动安装配置
├── offline/             # 离线资源（构建时生成）
│   └── manifest.yaml    # 离线资源清单（唯一真相来源）
└── tests/               # 测试脚本
```

## 核心构建命令

```bash
make iso           # 完整构建（需要 Docker + 互联网）
make download      # 仅下载离线资源
make shell         # 进入构建容器调试
make verify        # 校验离线资源 checksums
make clean         # 清理构建产物
```

## 关键设计决策

1. **manifest.yaml 是唯一真相来源**: 所有组件版本、镜像列表、下载 URL 只在此文件定义
2. **OFFLINE_BASE 条件回退**: deploy/ 脚本通过 `if [ -n "${OFFLINE_BASE}" ]` 条件切换离线/在线路径
3. **env-config.sh 兼容性**: TUI 生成的 env-config.sh 与 VDI 仓库 deploy/env-config.sh 格式完全一致
4. **PXE 仅用于 Worker**: Master 必须手动部署（模式 1/2），确保对集群初始化的完全控制

## 离线适配模式

现有 deploy/ 脚本的离线适配策略：在 env-config.sh 中增加 OFFLINE_BASE 等变量，
各脚本在需要网络的步骤中检测 OFFLINE_BASE，存在则走本地路径，不存在则走在线路径。
**一套脚本同时支持在线和离线两种模式**。

## 注意事项

- ISO 目标大小 < 8GB（不含 Windows VM 镜像）
- 仅支持 amd64 (x86_64)
- 目标 OS: Ubuntu 22.04 LTS
- TUI 运行需要 root 权限和 TTY 环境
