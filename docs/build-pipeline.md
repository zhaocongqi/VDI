# VDI 构建流程

VDI 离线安装器从源码到可引导 ISO 的完整构建链路。面向接手构建/运维的同事。

## 总览

构建用 **Dapper + Docker** 模式：`make <target>` 在容器内执行 `scripts/<target>`，外部依赖全挂载、纯离线。最终产物是 UEFI 可引导的 Live ISO。

```
make default
  ├─ scripts/build              编译 Go 安装器
  ├─ scripts/build-bundle       下载离线镜像 + Helm chart
  └─ scripts/package-vdi-os     构建 OS 镜像 + elemental build-iso + 注入 grubx64.efi
       └─ (自动) scripts/build-bclinux-base   若 bclinux:21.10U5 不存在
```

产物：`dist/artifacts/vdi-$VERSION-$ARCH.iso`（~3.3GB）

## 一、Makefile + Dapper 编排

`Makefile` 把 `scripts/*` 全部注册为 target：

```makefile
TARGETS := $(shell ls scripts)
$(TARGETS): .dapper
	./.dapper $@
```

- `./.dapper` 首次运行时从 `releases.rancher.com` 下载（带 SHA512 校验）
- 容器镜像由 `Dockerfile.dapper` 构建（基于 `golang:1.26-bookworm`，预装 xorriso/mtools/squashfs-tools/grub-efi-amd64-bin/rpm2cpio 等）
- **外部依赖通过 `DAPPER_RUN_ARGS` 挂载**（不从网络下载）：
  - `/usr/bin/docker` + buildx 插件
  - `/usr/local/bin/helm`、`/tmp/yq`
  - `~/go/pkg/mod`（Go 模块缓存，配合 `GOPROXY=off GOTOOLCHAIN=local`）
  - `cache/`、`dist/`（构建缓存与产物）
  - `/usr/lib/ISOLINUX` + `/usr/lib/syslinux`（ISO 后处理引导文件）
  - containerd socket + `--privileged`
- `DAPPER_OUTPUT` 声明容器→宿主机回传：`./bin ./dist ./cache ./package/vdi-os/files/usr/bin ./package/vdi-installer`

## 二、scripts 脚本职责

| 脚本 | 职责 | 产物 |
|------|------|------|
| `version` / `version-*` | 定义 VERSION + RKE2/KubeVirt/Longhorn/Kube-OVN/kagent 版本号 | shell 变量 |
| `build` | `go build` 编译安装器，ldflags 注入版本号 | `bin/vdi-installer` → `package/vdi-os/files/usr/bin/` |
| `build-bundle` | 下载组件镜像 tar + Helm chart | `package/vdi-os/iso/bundle/`、`package/vdi-cluster-repo/charts/` |
| `build-bclinux-base` | 从 BCLinux ISO 用 `dnf --installroot` 造基础镜像 | `bclinux:21.10U5` |
| `package-vdi-os` | 构建 OS 镜像 + elemental build-iso + 注入 grubx64.efi | `dist/artifacts/vdi-$VERSION-$ARCH.iso` |
| `package-vdi-installer` | 安装器二进制镜像（**当前跳过**，无 Dockerfile） | — |
| `package-vdi-repo` | Helm Chart 仓库镜像（**当前跳过**，需 nginx:alpine） | — |
| `test` / `validate` / `ci` | 测试 / golangci-lint / CI | — |

### build
`CGO_ENABLED=0 GOPROXY=off GOTOOLCHAIN=local go build`，通过 `-ldflags` 把 `version-*` 的版本号注入 `pkg/config` 和 `pkg/version` 的变量。编译后复制到 `package/vdi-os/files/usr/bin/vdi-installer`。

### build-bundle
为每个组件拉取镜像 tar + Helm chart，落盘到 `package/vdi-os/iso/bundle/vdi/images/`（镜像）和 `package/vdi-cluster-repo/charts/`（chart）。公共函数在 `scripts/lib/http`（`get_url`/`save_image_list`）和 `scripts/lib/image`（`save_image`/`pull_images`）。

支持 `LOCAL_PKG_DIR` 环境变量指定本地离线包检索路径（命中则本地拷贝，否则无代理 curl 下载）；未设置时默认检索 `cache/downloads`。

### build-bclinux-base
1. `7z` 从 BCLinux ISO 提取 `Packages/` + `repodata/` 到 `cache/bclinux-repo/`
2. 用 `almalinux:8` 辅助容器跑 `dnf --installroot` 装最小系统（@core/kernel/dracut/systemd/NetworkManager/openssh 等）
3. 打包为 `bclinux:21.10U5` 镜像

### package-vdi-os（8 步）

| 步骤 | 动作 |
|------|------|
| 0 | 生成 `vdi-release.yaml`（版本元数据） |
| 1 | 确保 `bclinux:21.10U5` 存在，否则调 `build-bclinux-base` |
| 2 | 准备本地 BCLinux RPM 仓库（7z 解包 ISO 的 Packages/repodata） |
| 3 | `docker buildx build` 构建 `rancher/vdi-os:$VERSION`（`--build-context bclinux-repo=<dir>` 挂载 RPM 仓库给 Dockerfile dnf 用） |
| 4 | 从镜像提取 `elemental` 二进制到宿主机 `/usr/bin/elemental` |
| 5 | 提取 kernel/initrd 到 `dist/artifacts/`（供 PXE/调试） |
| 6 | `elemental build-iso` 打包 Live ISO（`--overlay-iso` 叠加 `package/vdi-os/iso` 的 bundle+grub.cfg+isolinux.cfg） |
| 7 | **字节级注入 grubx64.efi**（Python 定位 EFI 镜像偏移 → mtools 注入 → `dd conv=notrunc` 原位写回） |
| 8 | 验证 ISO + 生成 SHA512 |

> 步骤 7 的背景：elemental build-iso 默认只把 `grub.efi` 放进 EFI 引导镜像，但 BCLinux shim 硬编码找 `grubx64.efi`，缺失则 UEFI 引导失败。此前用 xorriso 全量重建 ISO 注入，但 3.3GB ISO 重建后体积超 xorriso stdio 媒体容量上限（~3174MB）导致重建失败，改为字节级注入绕过。

## 三、Go 代码侧的构建参与

### 版本注入（`pkg/version/version.go`）
```go
var (
    Version   = "dev"   // ldflags 注入
    GitCommit = "HEAD"  // ldflags 注入
)
```
`scripts/build` 的 LINKFLAGS 把 `version-*` 版本号注入 `pkg/config` 的版本变量 + `pkg/version.Version/GitCommit`。

### VDI OS Dockerfile（`package/vdi-os/Dockerfile`）
FROM `bclinux:21.10U5`，依次：
1. dnf 安装 dracut/squashfs-tools/NetworkManager/openssh/iscsi/ebtables/ipvsadm 等
2. `rpm2cpio` 从 RPM 提取 EFI 文件（shim/grubx64/MokManager/fbx64）到 `/usr/share/efi/x86_64/`
3. `COPY files/` 注入安装器二进制 + systemd service + manifests + dracut 模块
4. 配置 systemd（禁 Anaconda，启 vdi-setup-installer/NetworkManager/sshd）
5. 配置 getty drop-in 覆盖（tty1/ttyS0 → `start-installer.sh`）
6. `dracut` 重建 initrd（加 dmsquash-live 模块，`--no-hostonly` 避免读宿主内核）
7. 设默认密码 root/vdi123、生成 SSH host key

### ISO 启动后的安装落地（`pkg/console/util.go:doInstall`）
ISO 引导 → `start-installer.sh`（设置终端尺寸）→ `vdi-installer` TUI 收集配置 → `doInstall()`：
1. `roleSetup` 设置节点角色 label
2. `generateEnvAndConfig` 生成 elemental 配置
3. `CreateRootPartitioningLayout*` 创建分区布局（含 Longhorn 数据分区）
4. `saveElementalConfig` + 调用 `elemental install` 把 OS 写入目标盘
5. 重启后 RKE2 启动 → 自动 apply `manifests/10-kube-ovn.yaml` 等 HelmChart → 部署 Kube-OVN/Longhorn/KubeVirt/kagent

## 四、构建产物依赖关系

```
Go 源码 ──build──→ bin/vdi-installer ──┐
                                       ├─→ package-vdi-os/files/usr/bin/
BCLinux ISO ──build-bclinux-base──→ bclinux:21.10U5 ──┐
        │                                              ├─→ Dockerfile ──→ rancher/vdi-os:$VER
        └─→ 7z 解包 RPM 仓库 ──────────────────────────┘            │
                                                                     ↓
网络镜像 ──build-bundle──→ bundle/ + charts/ ──→ package/vdi-os/iso/ (overlay)
                                                                     │
                                          elemental build-iso ←──────┘
                                                  │
                                          字节级注入 grubx64.efi
                                                  │
                                          dist/artifacts/vdi-$VER-$ARCH.iso
```

## 五、外部输入契约

构建前宿主机必须具备：

1. **BCLinux ISO**：`dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso`
2. **挂载的二进制**：docker、buildx、helm、yq（见 `DAPPER_RUN_ARGS`）
3. **Go 模块缓存**：`~/go/pkg/mod`（`GOPROXY=off` 纯离线）
4. **ISOLINUX/syslinux**：`/usr/lib/ISOLINUX` + `/usr/lib/syslinux`
5. **内存 ≥16G**：elemental + mksquashfs xz 压缩峰值 ~9.7GB，不足会 OOM（exit 137）
6. **磁盘 ≥20G**：Docker 层 + squashfs + ISO 临时空间

## 六、构建命令速查

```bash
make default            # 完整构建（build + build-bundle + package-vdi-os）
make build              # 仅编译 Go 安装器
make build-bundle       # 仅下载离线资源
make package-vdi-os     # 仅构建 OS 镜像 + ISO
make shell              # 进入构建容器调试
make test               # 运行测试
make validate           # golangci-lint 检查
```

验证 ISO（UEFI）：
```bash
qemu-system-x86_64 -m 4096 -smp 2 \
    -cdrom dist/artifacts/vdi-*.iso \
    -boot d -bios /usr/share/ovmf/OVMF.fd -nographic
```

## 七、已知缺口

1. `package-vdi-installer` / `package-vdi-repo` 在 `default` 中被跳过（离线环境限制）
2. kagent 镜像未拉取（ghcr.io 需认证，`build-bundle` 注释跳过）
3. `pkg/version.HarvesterVersion` 历史残留未使用
4. 当前 ISO 是 UEFI-only（无 BIOS/isolinux 引导记录）
