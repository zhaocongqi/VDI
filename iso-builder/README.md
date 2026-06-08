# VDI 离线 ISO 构建系统

构建一个一体化 Live ISO，在离线环境（有局域网、无互联网）下通过 TUI 菜单引导部署 VDI 集群。

## 功能特性

- **单一 ISO 介质**：包含所有离线资源（容器镜像、Helm Chart、二进制工具、系统包）
- **TUI 菜单引导**：类似 Ubuntu Server 安装体验，4 种部署模式
- **PXE 批量部署**：Worker 节点可通过网络自动安装并加入集群
- **可重复构建**：基于 Dapper 容器化构建，确保环境一致

## 快速开始

### 构建前提

- Docker 已安装
- 互联网连接（构建时下载资源）
- 磁盘空间 > 20GB

### 构建 ISO

```bash
# 完整构建（下载资源 + 打包 ISO）
make iso

# 或分步执行
make download    # 下载离线资源
make iso         # 打包 ISO
```

构建产物：
```
dist/
├── vdi-offline-v1.0.0.iso           # ISO 镜像
├── vdi-offline-v1.0.0.iso.sha256    # SHA256 校验和
└── vdi-offline-v1.0.0.manifest      # 构建信息
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

## 离线资源清单

通过 `offline/manifest.yaml` 管理所有离线资源：

- **K8s 核心**: v1.34.3（apiserver、controller-manager、scheduler、proxy、etcd、coredns）
- **kube-vip**: v0.7.2（API Server HA）
- **Kube-OVN**: v1.17.0（CNI 网络插件）
- **Longhorn**: v1.8.1（分布式块存储）
- **KubeVirt**: v1.5.0 + CDI v1.61.0（虚拟化运行时）
- **kagent**: 0.9.6（AI Agent 框架）

## 开发调试

```bash
make shell       # 进入构建容器交互 shell
make live-only   # 仅创建 Live 系统基础 ISO（不含离线资源）
make verify      # 校验离线资源完整性
make clean       # 清理构建产物
make distclean   # 清理全部（含下载资源）
```

## 项目结构

```
iso-builder/
├── Dockerfile.dapper       # 构建环境
├── Makefile                # 构建入口
├── scripts/                # 构建脚本
├── tui/                    # TUI 安装器 (Python)
├── pxe/                    # PXE 服务
├── configs/                # 配置模板
├── offline/                # 离线资源 + manifest
└── tests/                  # 测试
```

## 许可证

内部项目，未公开许可。
