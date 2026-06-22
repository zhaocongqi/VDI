# BCLinux Docker 镜像制备 + Live ISO 构建实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 BCLinux 安装 ISO 的 RPM 仓库制备干净的 Docker 基础镜像，再用 elemental build-iso 制作可启动 Live ISO。

**Architecture:** 用 `dnf --installroot` 在辅助容器中从 ISO 的 RPM 仓库安装最小 BCLinux 系统，生成 Docker 镜像；VDI Dockerfile 基于此镜像安装 dracut + dmsquash-live 并重建 initrd；最后用 `elemental build-iso`（和 Harvester 一致）打包 Live ISO。

**Tech Stack:** Docker, dnf, dracut, elemental-toolkit, xorriso, BCLinux 21.10 U5

## Global Constraints

- BCLinux ISO 路径：`dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso`
- Docker 镜像名：`bclinux:21.10U5`（基础）、`rancher/vdi-os:$VERSION`（VDI 定制）
- ISO 卷标：`VDI_LIVE`（已在 manifest.yaml 中定义）
- 内核：5.10.0-200.bclinux.21.10U5
- elemental 二进制：`package/vdi-os/files/usr/bin/elemental`（已存在）
- 所有中文注释和提交信息遵循 Conventional Commits 规范

---

## File Structure

| 文件 | 责任 | 状态 |
|------|------|------|
| `scripts/build-bclinux-base` | 从 ISO 用 dnf --installroot 创建 BCLinux 基础 Docker 镜像 | 新增 |
| `package/vdi-os/Dockerfile` | VDI OS 镜像构建（FROM bclinux + dracut 重建 initrd） | 重写 |
| `package/vdi-os/manifest.yaml` | elemental build-iso 的 ISO 配置 | 已存在（VDI_LIVE） |
| `package/vdi-os/iso/boot/grub2/grub.cfg` | elemental build-iso 的 GRUB 引导配置 | 新增 |
| `scripts/package-vdi-os` | ISO 打包主脚本（改为调用 elemental build-iso） | 重写 |

---

### Task 1: 创建 BCLinux 基础镜像构建脚本

**Files:**
- Create: `scripts/build-bclinux-base`
- Reference: `dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso`

**Interfaces:**
- Produces: Docker 镜像 `bclinux:21.10U5`（后续 Dockerfile 的 FROM 目标）

- [ ] **Step 1: 验证 ISO 中的 RPM 仓库结构**

```bash
7z l dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso | grep -c "\.rpm"
```
Expected: 1327（RPM 包数量）

```bash
7z l dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso | grep -iE "comps|repomd|primary\.xml"
```
Expected: 包含 repodata 目录的元数据文件

- [ ] **Step 2: 创建 scripts/build-bclinux-base 脚本**

```bash
#!/bin/bash -e
# 从 BCLinux ISO 的 RPM 仓库创建基础 Docker 镜像
# 用 dnf --installroot 在辅助容器中安装最小系统

TOP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
BCLINUX_ISO="${TOP_DIR}/dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso"
CACHE_DIR="${TOP_DIR}/cache"
REPO_DIR="${CACHE_DIR}/bclinux-repo"
ROOTFS_DIR="${CACHE_DIR}/bclinux-rootfs"

echo ">>> 提取 BCLinux RPM 仓库"
rm -rf "${REPO_DIR}"
mkdir -p "${REPO_DIR}"
7z x -o"${REPO_DIR}" "${BCLINUX_ISO}" Packages repodata -y

echo ">>> 用 dnf --installroot 安装最小 BCLinux 系统"
rm -rf "${ROOTFS_DIR}"
mkdir -p "${ROOTFS_DIR}"

# 用 almalinux:8 作为辅助容器（自带 dnf）
docker run --rm \
    -v "${REPO_DIR}:/iso:ro" \
    -v "${ROOTFS_DIR}:/rootfs" \
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
        iproute iputils net-tools \
        bash passwd

echo ">>> 创建 Docker 镜像"
tar -C "${ROOTFS_DIR}" -c . | docker import - bclinux:21.10U5

echo ">>> 验证"
docker run --rm bclinux:21.10U5 cat /etc/os-release | head -5
docker run --rm bclinux:21.10U5 ls /lib/modules/

echo ">>> 清理"
rm -rf "${ROOTFS_DIR}"
echo "完成: bclinux:21.10U5"
```

- [ ] **Step 3: 执行脚本并验证**

```bash
chmod +x scripts/build-bclinux-base
scripts/build-bclinux-base
```
Expected: 输出 `BigCloud Enterprise Linux 21.10 U5` + 内核模块目录

```bash
docker run --rm bclinux:21.10U5 which dracut
```
Expected: `/usr/sbin/dracut`（有 dracut 二进制）

- [ ] **Step 4: 提交**

```bash
git add scripts/build-bclinux-base
git commit -m "feat(build): 新增 BCLinux 基础镜像构建脚本

用 dnf --installroot 从 ISO 的 RPM 仓库安装最小 BCLinux 系统，
生成干净的 Docker 基础镜像（含 dracut 二进制，可重建 initrd）。"
```

---

### Task 2: 重写 VDI Dockerfile

**Files:**
- Rewrite: `package/vdi-os/Dockerfile`
- Reference: `package/vdi-os/files/`（VDI 文件）

**Interfaces:**
- Consumes: Docker 镜像 `bclinux:21.10U5`（来自 Task 1）
- Produces: Docker 镜像 `rancher/vdi-os:$VERSION`（含正确 initrd）

- [ ] **Step 1: 重写 Dockerfile**

```dockerfile
ARG BASE_OS_IMAGE=bclinux:21.10U5
FROM ${BASE_OS_IMAGE}

ARG ARCH=amd64

# 配置本地 BCLinux 仓库（用于安装额外包）
# 仓库由 build 脚本挂载到 /iso
RUN if [ -d /iso ]; then \
        printf "[bclinux]\nname=BCLinux\nbaseurl=file:///iso\nenabled=1\ngpgcheck=0\n" \
            > /etc/yum.repos.d/bclinux.repo; \
    fi

# 安装 dracut + dmsquash-live + VDI 依赖
RUN dnf install -y \
    dracut dracut-live \
    squashfs-tools \
    NetworkManager \
    openssh-server \
    iproute iputils net-tools \
    conntrack-tools \
    iscsi-initiator-utils nfs-utils \
    ebtables ipvsadm \
    && dnf clean all

# 注入 VDI 文件
COPY files/ /
COPY vdi-release.yaml /etc/

# elemental 二进制
COPY files/usr/bin/elemental /usr/bin/elemental
RUN chmod +x /usr/bin/elemental

# 配置 systemd：禁用 Anaconda 残留，启用 VDI 服务
RUN systemctl set-default multi-user.target && \
    systemctl disable anaconda.service anaconda-direct.service 2>/dev/null || true && \
    systemctl enable vdi-setup-installer.service vdi-network-setup.service 2>/dev/null || true && \
    systemctl enable NetworkManager sshd 2>/dev/null || true

# 配置 NetworkManager 管理所有接口
RUN mkdir -p /etc/NetworkManager/conf.d && \
    printf "[keyfile]\nunmanaged-devices=none\n" > /etc/NetworkManager/conf.d/10-manage-all.conf

# 配置 SSH
RUN mkdir -p /etc/ssh/sshd_config.d && \
    printf "PermitRootLogin yes\nPasswordAuthentication yes\n" > /etc/ssh/sshd_config.d/allow-root.conf

# 关键：用 dracut 重建 initrd（包含 dmsquash-live 模块）
RUN KERNEL_VERSION=$(ls /lib/modules/ | head -1) && \
    echo "重建 initrd for kernel ${KERNEL_VERSION}" && \
    dracut -f --add dmsquash-live /boot/initrd-${KERNEL_VERSION} && \
    ls -la /boot/initrd-${KERNEL_VERSION}

# 设置默认密码
RUN echo 'root:vdi123' | chpasswd

ARG VDI_PRETTY_NAME="VDI Platform"
RUN sed -i "s/^PRETTY_NAME.*/PRETTY_NAME=\"${VDI_PRETTY_NAME}\"/g" /etc/os-release
```

- [ ] **Step 2: 构建 VDI OS 镜像（需要本地仓库挂载）**

由于 BCLinux 基础镜像没有配置远程仓库，需要把 ISO 仓库挂载进去：

```bash
# 准备本地仓库缓存（如果不存在）
if [ ! -d cache/bclinux-repo ]; then
    mkdir -p cache/bclinux-repo
    7z x -ocache/bclinux-repo dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso Packages repodata -y
fi

# 构建（挂载本地仓库）
docker build \
    -v $(pwd)/cache/bclinux-repo:/iso:ro \
    --build-arg BASE_OS_IMAGE="bclinux:21.10U5" \
    -t rancher/vdi-os:test \
    -f package/vdi-os/Dockerfile \
    package/vdi-os/
```
Expected: 构建成功，最后输出 initrd 文件大小

- [ ] **Step 3: 验证 initrd 包含 dmsquash-live**

```bash
# 提取 initrd 检查 dmsquash-live 模块
docker run --rm rancher/vdi-os:test bash -c \
    "ls /lib/modules/*/kernel/fs/squashfs/ && \
     ls /usr/lib/dracut/modules.d/90dmsquash-live/ 2>/dev/null | head -5"
```
Expected: squashfs.ko 存在 + dmsquash-live 模块目录存在

- [ ] **Step 4: 提交**

```bash
git add package/vdi-os/Dockerfile
git commit -m "refactor(dockerfile): 重写 VDI Dockerfile 基于 BCLinux 基础镜像

- FROM bclinux:21.10U5（干净的最小系统）
- 安装 dracut-live 提供 dmsquash-live 模块
- dracut -f --add dmsquash-live 重建 initrd
- 禁用 Anaconda 残留，启用 VDI 服务"
```

---

### Task 3: 创建 elemental build-iso 的 GRUB 配置

**Files:**
- Create: `package/vdi-os/iso/boot/grub2/grub.cfg`
- Reference: `harvester-installer/package/harvester-os/iso/boot/grub2/grub.cfg`

**Interfaces:**
- Consumes: manifest.yaml（已存在，label=VDI_LIVE）
- Produces: GRUB 配置文件（elemental build-iso 的 --overlay-iso 使用）

- [ ] **Step 1: 创建 GRUB 配置**

```bash
mkdir -p package/vdi-os/iso/boot/grub2
cat > package/vdi-os/iso/boot/grub2/grub.cfg <<'EOF'
search --no-floppy --file --set=root /boot/kernel.xz
set default=0
set timeout=10
set timeout_style=menu
set linux=linux
set initrd=initrd

if [ "${grub_cpu}" = "x86_64" -o "${grub_cpu}" = "i386" ];then
    if [ "${grub_platform}" = "efi" ]; then
        set linux=linuxefi
        set initrd=initrdefi
    fi
fi

menuentry "VDI Installer" --class os --unrestricted {
    echo Loading kernel...
    $linux ($root)/boot/x86_64/loader/linux cdroot root=live:CDLABEL=VDI_LIVE rd.live.dir=/ rd.live.squashimg=rootfs.squashfs console=tty0 console=ttyS0,115200n8 net.ifnames=1
    echo Loading initrd...
    $initrd ($root)/boot/x86_64/loader/initrd
}

menuentry "VDI Installer (Debug)" --class os --unrestricted {
    echo Loading kernel...
    $linux ($root)/boot/x86_64/loader/linux cdroot root=live:CDLABEL=VDI_LIVE rd.live.dir=/ rd.live.squashimg=rootfs.squashfs console=tty0 console=ttyS0,115200n8 net.ifnames=1 debug
    echo Loading initrd...
    $initrd ($root)/boot/x86_64/loader/initrd
}
EOF
```

**关键参数说明：**
- `root=live:CDLABEL=VDI_LIVE`：通过卷标查找 live 介质
- `rd.live.dir=/`：squashfs 在 ISO 根目录（elemental 默认）
- `rd.live.squashimg=rootfs.squashfs`：squashfs 文件名（elemental 默认）
- `console=tty0 console=ttyS0`：VGA + 串口双输出

- [ ] **Step 2: 提交**

```bash
git add package/vdi-os/iso/boot/grub2/grub.cfg
git commit -m "feat(iso): 新增 elemental build-iso 的 GRUB 配置

使用 root=live:CDLABEL=VDI_LIVE 启动参数，与 Harvester 一致。
squashfs 路径用 elemental 默认值（/rootfs.squashfs）。"
```

---

### Task 4: 重写 package-vdi-os 脚本使用 elemental build-iso

**Files:**
- Rewrite: `scripts/package-vdi-os`
- Reference: `harvester-installer/scripts/package-harvester-os`（elemental build-iso 调用部分）

**Interfaces:**
- Consumes: `rancher/vdi-os:$VERSION` Docker 镜像（来自 Task 2）
- Consumes: `package/vdi-os/manifest.yaml` + `iso/`（来自 Task 3）
- Produces: `dist/artifacts/vdi-$VERSION-$ARCH.iso`

- [ ] **Step 1: 重写 scripts/package-vdi-os**

```bash
#!/bin/bash -e
# 构建 VDI Live ISO（使用 elemental build-iso）
# 参考 Harvester 的 scripts/package-harvester-os

TOP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
SCRIPTS_DIR="${TOP_DIR}/scripts"
PACKAGE_VDI_OS_DIR="${TOP_DIR}/package/vdi-os"

source ${SCRIPTS_DIR}/version-rke2
source ${SCRIPTS_DIR}/version-kubevirt
source ${SCRIPTS_DIR}/version-longhorn
source ${SCRIPTS_DIR}/version-kubeovn
source ${SCRIPTS_DIR}/version-kagent
source ${SCRIPTS_DIR}/version

VDI_OS_IMAGE=rancher/vdi-os:${VERSION}
PRETTY_NAME="VDI ${VERSION}"
CACHE_DIR="${TOP_DIR}/cache"

echo "============================================"
echo "  构建 VDI Live ISO (BCLinux + elemental)"
echo "  版本: ${VERSION}"
echo "  RKE2: ${RKE2_VERSION}"
echo "============================================"

# 生成 vdi-release.yaml
cat > ${PACKAGE_VDI_OS_DIR}/vdi-release.yaml <<EOF
vdi: ${VERSION}
installer: ${COMMIT}
os: ${PRETTY_NAME}
rke2: ${RKE2_VERSION}
kubevirt: ${KUBEVIRT_VERSION}
longhorn: ${LONGHORN_VERSION}
kubeovn: ${KUBEOVN_VERSION}
kagent: ${KAGENT_VERSION}
EOF

# ============================================================
# 步骤 1: 确保 BCLinux 基础镜像存在
# ============================================================
if ! docker image inspect bclinux:21.10U5 > /dev/null 2>&1; then
    echo ">>> BCLinux 基础镜像不存在，开始构建..."
    ${SCRIPTS_DIR}/build-bclinux-base
fi

# ============================================================
# 步骤 2: 构建 VDI OS Docker 镜像
# ============================================================
echo ">>> 构建 VDI OS 镜像"

# 准备本地 BCLinux 仓库（供 Dockerfile 中 dnf 使用）
REPO_DIR="${CACHE_DIR}/bclinux-repo"
if [ ! -d "${REPO_DIR}" ]; then
    mkdir -p "${REPO_DIR}"
    7z x -o"${REPO_DIR}" ${TOP_DIR}/dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso Packages repodata -y 2>/dev/null
fi

cd ${PACKAGE_VDI_OS_DIR}
docker build \
    -v ${REPO_DIR}:/iso:ro \
    --build-arg BASE_OS_IMAGE="bclinux:21.10U5" \
    --build-arg VDI_PRETTY_NAME="${PRETTY_NAME}" \
    --build-arg ARCH="${ARCH}" \
    -t ${VDI_OS_IMAGE} .

# ============================================================
# 步骤 3: 提取 elemental 二进制到宿主机
# ============================================================
echo ">>> 提取 elemental 二进制"
docker create --cidfile=/tmp/elemental-extract ${VDI_OS_IMAGE} -- tail -f /dev/null
docker cp $(</tmp/elemental-extract):/usr/bin/elemental /usr/bin/elemental 2>/dev/null || \
    sudo docker cp $(</tmp/elemental-extract):/usr/bin/elemental /usr/bin/elemental
docker rm $(</tmp/elemental-extract) && rm -f /tmp/elemental-extract

# ============================================================
# 步骤 4: 用 elemental build-iso 构建 Live ISO
# ============================================================
echo ">>> 构建 Live ISO (elemental build-iso)"
ARTIFACTS_DIR="${TOP_DIR}/dist/artifacts"
mkdir -p ${ARTIFACTS_DIR}
ISO_PREFIX="vdi-${VERSION}-${ARCH}"

cd ${PACKAGE_VDI_OS_DIR}
elemental build-iso \
    --config-dir "${PACKAGE_VDI_OS_DIR}" \
    --debug \
    "docker:${VDI_OS_IMAGE}" \
    --local \
    -n "${ISO_PREFIX}" \
    -o "${ARTIFACTS_DIR}" \
    --overlay-iso "${PACKAGE_VDI_OS_DIR}/iso" \
    -x "-comp xz" \
    --platform "linux/${ARCH}"

cd ${TOP_DIR}

# ============================================================
# 步骤 5: 验证
# ============================================================
ISO_FILE="${ARTIFACTS_DIR}/${ISO_PREFIX}.iso"
if [ ! -f "${ISO_FILE}" ]; then
    echo "ERROR: ISO 文件未生成: ${ISO_FILE}"
    exit 1
fi

echo ">>> ISO 内容验证"
isoinfo -d -i "${ISO_FILE}" 2>/dev/null | grep "Volume id"
7z l "${ISO_FILE}" 2>/dev/null | grep -iE "rootfs.squashfs|vmlinuz|initrd|grub.cfg" | head -10

# 生成校验和
cd ${ARTIFACTS_DIR}
sha512sum ${ISO_PREFIX}.iso > ${ISO_PREFIX}.sha512

echo "============================================"
echo "  构建完成!"
echo "  ISO: ${ISO_FILE}"
echo "  大小: $(du -sh ${ISO_FILE} | cut -f1)"
echo "============================================"
```

- [ ] **Step 2: 执行完整构建流程**

```bash
chmod +x scripts/package-vdi-os

# 确保先编译 Go 安装器
export PATH=~/go-sdk/go/bin:$PATH
export GOROOT=~/go-sdk/go
scripts/build

# 构建 ISO
export ARCH=amd64
export COMMIT=$(git rev-parse --short HEAD)
source scripts/version
scripts/package-vdi-os
```
Expected: ISO 生成在 `dist/artifacts/vdi-$VERSION-amd64.iso`，卷标为 `VDI_LIVE`

- [ ] **Step 3: 验证 ISO 结构**

```bash
isoinfo -d -i dist/artifacts/vdi-*.iso | grep "Volume id"
# Expected: Volume id: VDI_LIVE

7z l dist/artifacts/vdi-*.iso | grep -iE "rootfs.squashfs|loader|grub"
# Expected: 包含 rootfs.squashfs + boot/x86_64/loader/linux + boot/x86_64/loader/initrd
```

- [ ] **Step 4: 提交**

```bash
git add scripts/package-vdi-os
git commit -m "refactor(iso): 改用 elemental build-iso 构建 Live ISO

放弃手动 xorriso，改用 elemental build-iso（和 Harvester 一致）。
elemental 自动处理 squashfs + kernel + initrd + GRUB + 引导配置。
解决了之前 BCLinux Anaconda initrd 不兼容 dmsquash-live 的问题。"
```

---

### Task 5: VMware 测试验证

**Files:** 无（测试任务）

- [ ] **Step 1: VMware 创建虚拟机**

- 类型：Linux → Other Linux 6.x 64-bit
- 内存：≥ 4GB
- CPU：≥ 2 核
- 磁盘：≥ 50GB
- 挂载 ISO 文件

- [ ] **Step 2: 启动并验证**

Expected 启动流程：
1. GRUB 菜单显示 "VDI Installer" 和 "VDI Installer (Debug)"
2. 选择后内核加载（不再卡在 dracut emergency shell）
3. 进入 VDI TUI 安装界面（显示安装模式选择）

- [ ] **Step 3: 验证 TUI 功能**

- 选择"首节点"模式
- 网络配置（DHCP，选网卡）
- 确认能正常操作

- [ ] **Step 4: 如果失败，收集诊断信息**

在 GRUB 菜单按 `e` 编辑启动参数，添加 `rd.debug` 然后按 Ctrl+X 启动。
或在 dracut shell 中执行：
```bash
cat /proc/cmdline
ls /dev/disk/by-label/
dmesg | tail -20
```

---

## Self-Review

**Spec coverage:**
- ✅ 步骤1（提取 RPM 仓库）→ Task 1 Step 2
- ✅ 步骤2（dnf --installroot）→ Task 1 Step 2
- ✅ 步骤3（VDI Dockerfile + dracut 重建 initrd）→ Task 2
- ✅ 步骤4（elemental build-iso）→ Task 3 + Task 4
- ✅ GRUB 启动参数 → Task 3
- ✅ manifest.yaml → 已存在（VDI_LIVE）
- ✅ 验证方法 → Task 4 Step 3 + Task 5

**Placeholder scan:** 无 TBD/TODO，所有步骤都有具体代码和命令

**Type consistency:** Docker 镜像名 `bclinux:21.10U5` 和 `rancher/vdi-os:$VERSION` 在所有任务中一致；卷标 `VDI_LIVE` 在 manifest.yaml、GRUB、脚本中一致
