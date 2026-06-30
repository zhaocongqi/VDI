# VDI 构建环境前置条件

> ⚠️ **状态说明（2026-06-30）**：本文档描述的是 `main` 分支 elemental Live ISO 的构建环境（含 elemental/wharfie/yip 二进制依赖）。`feat/kickstart-xorriso` 分支已改用 kickstart + xorriso，**不再需要 elemental/wharfie/yip**，外部输入仅剩 BCLinux ISO。kickstart 链路现状以 [`CLAUDE.md`](../CLAUDE.md) 为准。本文档待重写。

新环境从零构建 VDI Live ISO 的前置条件清单。满足后 `make default` 一条命令跑通。

## 一、必须提供

### 1. BCLinux ISO（客户提供，无法自动下载）

放至：
```
dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso
```

`build-bclinux-base` 从中提取 RPM 仓库（`Packages/` + `repodata/`），用 `dnf --installroot` 本地安装最小系统，生成 `bclinux:21.10U5` 基础镜像。这一步纯离线，不联网。

### 2. 宿主机工具

- **docker + buildx**：DinD 模式（容器内调宿主机 daemon）。Makefile 探测路径（`which docker` + `/usr/libexec/docker/docker-buildx`），探测失败明确报错。CLI 版本需与 daemon 匹配。
- **python3**：`package-vdi-os` 步骤 7 用其定位 ISO 内 EFI 引导镜像偏移。
- **7z**：`build-bclinux-base` + `package-vdi-os` 从 BCLinux ISO 提取 RPM 仓库。
- **mtools**（`mcopy`/`mdir`）：`package-vdi-os` 步骤 7 注入 grubx64.efi 到 FAT EFI 镜像。
- **xorriso / isoinfo**：ISO 验证。
- **jq / yq**：构建脚本（部分步骤用）。

其余工具（helm、yq、Go 模块）由 `Dockerfile.dapper` 容器内安装/下载，宿主机无需预装。

## 二、自动下载（需网络）

`make default` 自动调 `fetch-deps`（幂等，已存在则跳过）下载：

| 二进制 | 版本 | 来源 | 用途 |
|--------|------|------|------|
| elemental | v0.3.1 | github.com/rancher/elemental-cli | `elemental install` + `elemental build-iso` |
| wharfie | v0.6.8 | github.com/rancher/wharfie | 从 system-agent-installer-rke2 镜像提取 rke2 二进制 |
| yip | v1.9.2 | github.com/rancher/yip | applyPassword 配置用户密码 |

`.dapper` 二进制首次由 Makefile 从 `releases.rancher.com` 下载（带 SHA512 校验）。

## 三、网络访问要求

构建需访问以下站点（网络受限环境需配代理或 registry mirror）：

| 站点 | 用途 |
|------|------|
| `docker.io` | `golang:1.26-bookworm`（dapper 容器）、`almalinux:8`（build-bclinux-base 辅助）、`debian:bookworm-slim`（grub-efi-modules 提取）、RKE2/组件镜像（build-bundle `docker pull`） |
| `proxy.golang.org` | Go 模块下载（无 vendor 目录，`go build` 联网拉取） |
| `github.com` / `raw.githubusercontent.com` | elemental/wharfie/yip 二进制、RKE2/Helm chart、镜像列表 |
| `releases.rancher.com` | `.dapper` 二进制 |
| `charts.longhorn.io` / `kubevirt.io` | Helm chart（build-bundle `helm pull`） |

**docker.io 不可达时**：配 `/etc/docker/daemon.json` 的 `registry-mirrors`（如阿里云 `registry.cn-hangzhou.aliyuncs.com`、中科大 `docker.mirrors.ustc.edu.cn`），重启 docker。

## 四、资源要求

| 资源 | 要求 | 原因 |
|------|------|------|
| 内存 | ≥16G | elemental build-iso 的 squashfs xz 压缩峰值 ~9.7GB，不足会 OOM（exit 137）。不足时加 swap（`fallocate -l 8G /swapfile && mkswap /swapfile && swapon /swapfile`） |
| 磁盘 | ≥30G | Docker 层 + squashfs + ISO 临时空间。`dist/`（BCLinux ISO 输入 + ISO 产物）、`cache/`（BCLinux 仓库 + rootfs） |

## 五、一条命令构建

前置条件就绪后：

```bash
make default    # fetch-deps → check-deps → build → build-bundle → package-vdi-os
```

产物：`dist/artifacts/vdi-$VERSION-amd64.iso`（UEFI 可引导）。

也可分步：
```bash
make fetch-deps        # 下载 elemental/wharfie/yip
make build             # 编译 Go 安装器
make build-bundle      # 下载离线镜像 + Helm chart
make package-vdi-os    # 构建 OS 镜像 + elemental build-iso + 注入 grubx64.efi
```

## 六、构建链路（排除网络后的产物依赖）

```
BCLinux ISO ──build-bclinux-base──→ bclinux:21.10U5 ──┐
        │                                              ├─→ Dockerfile ──→ rancher/vdi-os:$VER
        └─→ 7z 解包 RPM 仓库 ──────────────────────────┘            │
                                                                     ↓
Go 源码 ──build──→ vdi-installer ──→ files/usr/bin/ ────────────────┤
                                                                     │
elemental/wharfie/yip ──fetch-deps──→ files/usr/bin/ ───────────────┤
                                                                     ↓
网络镜像 ──build-bundle──→ bundle/ + charts/ ──→ iso/ (overlay) ────┤
                                                                     ↓
                                                          elemental build-iso
                                                                  │
                                                          字节级注入 grubx64.efi
                                                                  │
                                                          dist/artifacts/vdi-$VER.iso
```

## 七、常见问题

- **`check-deps` 报缺 elemental/wharfie/yip**：`make default` 已自动调 `fetch-deps`；单独跑 `make package-vdi-os` 也会自动调。手动补：`make fetch-deps`。
- **OOM（exit 137）**：内存不足，加 swap（见第四节）。
- **docker.io TLS handshake timeout**：网络受限，配 registry mirror（见第三节）。
- **`.docker` permission denied**：dapper cp 模式回传时容器内 root 创建 `.docker`（root:root 700），`.dockerignore` 已加 `.docker` 排除，正常不触发。若残留：`sudo rm -rf .docker`。
- **dapper 每次重建 vdi:main**：dapper 设计如此（每次 `docker build Dockerfile.dapper`），需网络拉 `golang:1.26-bookworm` metadata。
- **qemu 端到端验证**：用 `-kernel` + `-initrd` 绕过 UEFI 引导（OVMF 无法从 ISO El Torito EFI 引导）。vdi-installer `--auto-install` 跳过 TUI 直接安装。KVM 需 `/dev/kvm` 权限（`chmod 666 /dev/kvm` 或加入 kvm 组）。磁盘 ≥250G，内存 ≥8G。`scripts/qemu-test` 提供自动化脚本。
