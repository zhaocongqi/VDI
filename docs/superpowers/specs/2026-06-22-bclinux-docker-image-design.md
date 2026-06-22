# BCLinux Docker 镜像制备 + Live ISO 构建设计

## 背景与动机

VDI 项目需要将基础 OS 从 Ubuntu 迁移到 BCLinux 21.10 U5。之前的尝试直接从 BCLinux ISO 的 `install.img` 提取 rootfs，但 `install.img` 是 **Anaconda 安装器运行时**，不是真正的操作系统：

- 缺少 dracut 二进制（无法重建 initrd）
- initrd 中塞满 Anaconda dracut hooks，干扰 dmsquash-live 正常工作
- 没有配置 yum 仓库（无法用 dnf 安装缺失包）
- 导致 Live ISO 启动时内核 panic（`Unable to mount root fs`）

**正确的方法**：从 ISO 的 RPM 仓库（`Packages/` + `repodata/`）用 `dnf --installroot` 安装一个干净的 BCLinux 最小系统，制作成 Docker 镜像，再用 `elemental build-iso`（和 Harvester 完全一致的方式）制作 Live ISO。

## BCLinux ISO 结构

| 路径 | 内容 | 用途 |
|------|------|------|
| `images/install.img` (813MB) | Anaconda 安装器运行时 | ❌ 不使用 |
| `Packages/` (1327个RPM) | 操作系统软件包 | ✅ RPM 仓库源 |
| `repodata/` | yum/dnf 仓库元数据 | ✅ RPM 仓库源 |
| `images/pxeboot/vmlinuz` | Anaconda 安装器内核 | ❌ 不使用（elemental 会用 Docker 镜像中的内核） |

## 整体架构

```
BCLinux ISO (3.3GB)
    │
    ├─ 1. 提取 Packages/ + repodata/ 作为本地 RPM 仓库
    │
    ├─ 2. dnf --installroot 安装最小系统
    │   └─ 辅助容器（almalinux:8）执行
    │   └─ 产出：bclinux:21.10U5 Docker 镜像（干净的 OS rootfs）
    │
    ├─ 3. VDI Dockerfile 定制
    │   └─ FROM bclinux:21.10U5
    │   └─ 安装 dracut + dmsquash-live + NetworkManager + VDI 组件
    │   └─ 注入 VDI 文件（安装器、脚本、systemd 服务）
    │   └─ dracut -f --regenerate-all（生成正确的 initrd）
    │   └─ 产出：rancher/vdi-os:$VERSION Docker 镜像
    │
    └─ 4. elemental build-iso 制作 Live ISO
        └─ 输入：rancher/vdi-os:$VERSION Docker 镜像
        └─ elemental 自动处理 squashfs + kernel + initrd + GRUB
        └─ 产出：vdi-$VERSION-$ARCH.iso（可启动）
```

## 详细实现

### 步骤 1：提取 RPM 仓库

```bash
7z x BCLinux-21.10U5-dvd-x86_64-260610.iso -o./cache/bclinux-repo Packages repodata
```

### 步骤 2：dnf --installroot 创建基础镜像

```bash
docker run --rm \
    -v ./cache/bclinux-repo:/iso:ro \
    -v ./cache/bclinux-rootfs:/rootfs \
    almalinux:8 \
    dnf --installroot=/rootfs \
        --releasever=21.10U5 \
        --repofrompath=bclinux,/iso \
        --nogpgcheck \
        install -y \
        @core \
        kernel \
        dracut \
        systemd \
        NetworkManager \
        openssh-server \
        iproute iputils net-tools

tar -C ./cache/bclinux-rootfs -c . | docker import - bclinux:21.10U5
```

**需要验证的点（实现时检查）：**
1. BCLinux 的 `comps.xml` 是否定义了 `@core` 组
2. `--releasever` 的正确值（从 repodata 推断）
3. 内核包名（预期 `kernel-5.10.0-200.*.bclinux.21.10U5`）

### 步骤 3：VDI Dockerfile

```dockerfile
ARG BASE_OS_IMAGE=bclinux:21.10U5
FROM ${BASE_OS_IMAGE}

RUN dnf install -y dracut dracut-live squashfs-tools NetworkManager openssh-server \
    iproute iputils net-tools conntrack-tools iscsi-initiator-utils nfs-utils && \
    dnf clean all

COPY files/ /
COPY vdi-release.yaml /etc/
COPY files/usr/bin/elemental /usr/bin/elemental
RUN chmod +x /usr/bin/elemental

RUN systemctl set-default multi-user.target && \
    systemctl enable vdi-setup-installer.service vdi-network-setup.service

# 关键：用 dracut 重建 initrd（包含 dmsquash-live 模块）
RUN KERNEL_VERSION=$(ls /lib/modules/ | head -1) && \
    dracut -f --add dmsquash-live /boot/initrd-${KERNEL_VERSION}

RUN echo 'root:vdi123' | chpasswd
```

### 步骤 4：elemental build-iso

**manifest.yaml：**
```yaml
iso:
  bootloader-in-rootfs: true
  label: "VDI_LIVE"
```

**GRUB 配置（overlay-iso/boot/grub2/grub.cfg）：**
```
root=live:CDLABEL=VDI_LIVE rd.live.dir=/ rd.live.squashimg=rootfs.squashfs console=tty1
```

**构建命令：**
```bash
elemental build-iso \
    --config-dir ./package/vdi-os \
    --debug \
    "docker:rancher/vdi-os:${VERSION}" \
    --local \
    -n "vdi-${VERSION}-${ARCH}" \
    -o ./dist/artifacts \
    --overlay-iso ./package/vdi-os/iso \
    -x "-comp xz"
```

## 与 Harvester 的对比

| 项目 | Harvester | VDI（本设计） |
|------|-----------|--------------|
| 基础镜像 | SLE Micro（预装 elemental） | BCLinux 21.10 U5（从 ISO 用 dnf 安装） |
| initrd 生成 | `dracut --regenerate-all` | `dracut -f --add dmsquash-live` |
| ISO 构建 | `elemental build-iso` | `elemental build-iso` |
| squashfs 路径 | `/rootfs.squashfs` | `/rootfs.squashfs`（elemental 默认） |
| 启动参数 | `root=live:CDLABEL=COS_LIVE` | `root=live:CDLABEL=VDI_LIVE` |
| 卷标 | `COS_LIVE` | `VDI_LIVE` |

## 验证方法

```bash
# 1. 构建 Docker 镜像
docker build -t rancher/vdi-os:$VERSION ./package/vdi-os

# 2. 验证 Docker 镜像中有正确的 initrd
docker run --rm rancher/vdi-os:$VERSION ls -la /boot/initrd-*

# 3. 构建 Live ISO
elemental build-iso ...

# 4. VMware 测试
# - 挂载 ISO → 选择 VDI Installer → 应直接进入 TUI 安装界面
```

## 涉及的文件变更

| 文件 | 变更 |
|------|------|
| `scripts/build-bclinux-base`（新增） | dnf --installroot 创建 BCLinux 基础镜像 |
| `package/vdi-os/Dockerfile` | 改为 FROM bclinux:21.10U5 + dracut 重建 initrd |
| `package/vdi-os/manifest.yaml` | ISO 卷标 VDI_LIVE |
| `package/vdi-os/iso/boot/grub2/grub.cfg`（新增） | elemental build-iso 的 GRUB 配置 |
| `scripts/package-vdi-os` | 改为调用 elemental build-iso |
