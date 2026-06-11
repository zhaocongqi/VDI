# P4: package-iso — bootloader 模板 + ISO 打包

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 bootloader 模板和 `scripts/package-iso/` 阶段脚本，`make iso` 产出完整 ISO + PXE 产物。

**Architecture:** bootloader 配置从脚本内联抽离为 `iso/` 目录下的模板文件。xorriso 使用 Harvester 的 `pack_iso` 风格参数。PXE 产物作为构建的额外输出。

**Tech Stack:** xorriso, squashfs-tools, grub-mkimage, mkfs.vfat, mtools

**前置依赖:** P2 + P3 完成

---

### Task 4.1: 创建 bootloader 模板文件

**Files:**
- Create: `iso-builder/iso/boot/grub/grub.cfg`
- Create: `iso-builder/iso/isolinux/isolinux.cfg`

- [ ] **Step 1: 创建 GRUB 模板**

```bash
cat > /home/zcq/Github/VDI/iso-builder/iso/boot/grub/grub.cfg << 'GRUB'
serial --unit=0 --speed=115200
terminal_input serial console
terminal_output serial console

set default=0
set timeout=30
set color_normal=white/black
set color_color_highlight=black/light-gray

menuentry "Install VDI Cluster ${vdi_version}" {
    linux /casper/vmlinuz boot=live live-media-path=/casper console=ttyS0,115200 console=tty0 ---
    initrd /casper/initrd
}

menuentry "VDI Live Shell" {
    linux /casper/vmlinuz boot=live live-media-path=/casper text console=ttyS0,115200 console=tty0 ---
    initrd /casper/initrd
}

menuentry "Install VDI Cluster (Safe Mode)" {
    linux /casper/vmlinuz boot=live live-media-path=/casper nomodeset text console=ttyS0,115200 console=tty0 ---
    initrd /casper/initrd
}
GRUB
```

- [ ] **Step 2: 创建 isolinux 模板**

```bash
cat > /home/zcq/Github/VDI/iso-builder/iso/isolinux/isolinux.cfg << 'ISOLINUX'
SERIAL 0 115200
CONSOLE 0
DEFAULT install
PROMPT 1
TIMEOUT 50

LABEL install
    MENU LABEL ^Install VDI Cluster
    KERNEL /casper/vmlinuz
    APPEND initrd=/casper/initrd boot=live live-media-path=/casper console=ttyS0,115200 console=tty0 ---

LABEL shell
    MENU LABEL ^VDI Live Shell
    KERNEL /casper/vmlinuz
    APPEND initrd=/casper/initrd boot=live live-media-path=/casper text console=ttyS0,115200 console=tty0 ---

LABEL safe
    MENU LABEL ^Safe Mode
    KERNEL /casper/vmlinuz
    APPEND initrd=/casper/initrd boot=live live-media-path=/casper nomodeset text console=ttyS0,115200 console=tty0 ---
ISOLINUX
```

- [ ] **Step 3: 提交**

```bash
git add iso/
git commit -m "feat(iso-builder): 创建 bootloader 模板文件 (GRUB + isolinux)"
```

---

### Task 4.2: 创建 scripts/package-iso/entry

**Files:**
- Create: `iso-builder/scripts/package-iso/entry`

- [ ] **Step 1: 创建阶段 3 入口**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/package-iso/entry << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 阶段 3: package-iso 入口
# 将 rootfs 和 bundle 组装为最终 ISO + PXE 产物

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-v1.0.0}"
ISO_NAME="vdi-offline-${VERSION}"

source "${SCRIPT_DIR}/../common.sh"
source "${SCRIPT_DIR}/../lib/iso.sh"

CACHE_DIR="${WORKSPACE}/cache"
DIST_DIR="${WORKSPACE}/dist"
ROOTFS_CACHE="${CACHE_DIR}/rootfs"
BUNDLE_DIR="${CACHE_DIR}/bundle"

echo "============================================"
echo "  阶段 3: package-iso"
echo "  版本: ${VERSION}"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ========== 前置校验 ==========
step "校验前置依赖"
validate_dir "${ROOTFS_CACHE}" "rootfs 缓存" || exit 1
validate_dir "${BUNDLE_DIR}" "bundle 缓存" || exit 1
validate_file "${BUNDLE_DIR}/metadata.yaml" "metadata.yaml" || exit 1

# ========== 准备 ISO 目录 ==========
ISO_ROOT="${CACHE_DIR}/iso-staging"
rm -rf "${ISO_ROOT}"
mkdir -p "${ISO_ROOT}"/{boot/grub,efi/boot,isolinux,casper,bundle,scripts,configs,tui,.disk}

# ========== squashfs ==========
step "创建 squashfs"
source "${SCRIPT_DIR}/squashfs.sh"

# ========== bootloader ==========
step "配置 bootloader"
source "${SCRIPT_DIR}/bootloader.sh"

# ========== 整合资源 ==========
step "整合离线资源"
rsync -a --exclude='.gitkeep' "${BUNDLE_DIR}/" "${ISO_ROOT}/bundle/"

# 复制部署脚本
VDI_DEPLOY="${WORKSPACE}/../deploy"
if [ -d "$VDI_DEPLOY" ]; then
    rsync -a --exclude='hosts' --exclude='k8s/inventory.yaml' --exclude='.git' \
        "${VDI_DEPLOY}/" "${ISO_ROOT}/scripts/deploy/"
fi

# 复制配置文件
if [ -d "${WORKSPACE}/configs" ]; then
    rsync -a "${WORKSPACE}/configs/" "${ISO_ROOT}/configs/"
fi

# 复制部署时脚本
mkdir -p "${ISO_ROOT}/scripts"
for script in load-offline-images setup-local-repo verify-offline-pack; do
    [ -f "${WORKSPACE}/scripts/${script}" ] && cp "${WORKSPACE}/scripts/${script}" "${ISO_ROOT}/scripts/"
done

# 复制 TUI（仅 ISO 根目录一份）
if [ -d "${WORKSPACE}/tui" ]; then
    rsync -a "${WORKSPACE}/tui/" "${ISO_ROOT}/tui/"
fi

ok "离线资源整合完成"

# ========== ISO 元数据 ==========
echo "VDI Offline Install ${VERSION} - amd64 ($(date '+%Y-%m-%d %H:%M:%S'))" > "${ISO_ROOT}/.disk/info"
echo "${ISO_NAME}" > "${ISO_ROOT}/.disk/base_installable"

# ========== 打包 ISO ==========
step "打包 ISO"
source "${SCRIPT_DIR}/iso.sh"

# ========== PXE 产物 ==========
step "生成 PXE 产物"
source "${SCRIPT_DIR}/pxe.sh"

# ========== 校验和 ==========
step "生成校验和"
source "${SCRIPT_DIR}/checksum.sh"

# ========== 最终校验 ==========
ISO_FILE="${DIST_DIR}/${ISO_NAME}.iso"
ISO_SIZE=$(du -m "$ISO_FILE" | cut -f1)
if [ "$ISO_SIZE" -lt 100 ]; then
    error "ISO 文件异常小 (${ISO_SIZE}MB)，构建可能失败"
    exit 1
fi

echo ""
echo "============================================"
ok "阶段 3 完成!"
echo "  ISO: ${ISO_FILE}"
echo "  大小: $(du -sh "$ISO_FILE" | cut -f1)"
echo "  SHA256: ${DIST_DIR}/${ISO_NAME}.iso.sha256"
echo "  PXE: ${DIST_DIR}/pxe/"
echo "============================================"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/package-iso/entry
```

- [ ] **Step 2: 提交**

```bash
git add scripts/package-iso/entry
git commit -m "feat(iso-builder): 创建 package-iso 阶段入口脚本"
```

---

### Task 4.3: 创建 scripts/package-iso/squashfs.sh

**Files:**
- Create: `iso-builder/scripts/package-iso/squashfs.sh`

- [ ] **Step 1: 创建 squashfs 打包脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/package-iso/squashfs.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 创建 squashfs + 复制内核和 initrd

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"

CACHE_DIR="${WORKSPACE}/cache"
ROOTFS_CACHE="${CACHE_DIR}/rootfs"
ISO_ROOT="${CACHE_DIR}/iso-staging"

validate_dir "${ROOTFS_CACHE}" "rootfs" || exit 1

# 复制内核和 initrd
KERNEL=$(find "${ROOTFS_CACHE}/boot" -name "vmlinuz-*" -type f 2>/dev/null | head -1)
INITRD=$(find "${ROOTFS_CACHE}/boot" -name "initrd.img-*" -type f 2>/dev/null | head -1)

if [ -n "$KERNEL" ] && [ -n "$INITRD" ]; then
    cp "$KERNEL" "${ISO_ROOT}/casper/vmlinuz"
    cp "$INITRD" "${ISO_ROOT}/casper/initrd"
    ok "内核和 initrd 已复制"
else
    error "未找到内核文件"
    exit 1
fi

# 创建 squashfs
rm -f "${ISO_ROOT}/casper/filesystem.squashfs"
mksquashfs "$ROOTFS_CACHE" "${ISO_ROOT}/casper/filesystem.squashfs" \
    -comp xz -no-progress -noappend \
    -e boot/grub -e var/cache -e var/lib/apt/lists

ok "squashfs 已创建 ($(du -sh "${ISO_ROOT}/casper/filesystem.squashfs" | cut -f1))"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/package-iso/squashfs.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/package-iso/squashfs.sh
git commit -m "feat(iso-builder): 创建 squashfs.sh 打包脚本"
```

---

### Task 4.4: 创建 scripts/package-iso/bootloader.sh

**Files:**
- Create: `iso-builder/scripts/package-iso/bootloader.sh`

- [ ] **Step 1: 创建 bootloader 配置生成脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/package-iso/bootloader.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 配置 bootloader（从模板生成）
# 使用 iso/ 目录下的模板文件，注入版本号

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"
source "${WORKSPACE}/scripts/lib/iso.sh"
source "${WORKSPACE}/scripts/lib/template.sh"

CACHE_DIR="${WORKSPACE}/cache"
ISO_ROOT="${CACHE_DIR}/iso-staging"
ISO_TEMPLATES="${WORKSPACE}/iso"
VERSION="${1:-v1.0.0}"

# ========== isolinux (BIOS) ==========
step "配置 isolinux (BIOS)"
copy_isolinux_files "${ISO_ROOT}/isolinux"

# 从模板渲染 isolinux.cfg
render_template "${ISO_TEMPLATES}/isolinux/isolinux.cfg" \
    "${ISO_ROOT}/isolinux/isolinux.cfg"

ok "isolinux 配置完成"

# ========== GRUB (UEFI) ==========
step "配置 GRUB (UEFI)"
render_template "${ISO_TEMPLATES}/boot/grub/grub.cfg" \
    "${ISO_ROOT}/boot/grub/grub.cfg" \
    "vdi_version=${VERSION}"

ok "GRUB 配置完成"

# ========== EFI 引导镜像 ==========
step "创建 EFI 引导镜像"
create_efi_image "${ISO_ROOT}/efi/boot/efiboot.img" "${ISO_ROOT}/boot/grub"

ok "EFI 引导镜像创建完成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/package-iso/bootloader.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/package-iso/bootloader.sh
git commit -m "feat(iso-builder): 创建 bootloader.sh 从模板生成引导配置"
```

---

### Task 4.5: 创建 scripts/package-iso/iso.sh

**Files:**
- Create: `iso-builder/scripts/package-iso/iso.sh`

- [ ] **Step 1: 创建 xorriso 打包脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/package-iso/iso.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# xorriso 打包 ISO（参考 Harvester 的 pack_iso 风格）

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"
source "${WORKSPACE}/scripts/lib/iso.sh"

CACHE_DIR="${WORKSPACE}/cache"
DIST_DIR="${WORKSPACE}/dist"
ISO_ROOT="${CACHE_DIR}/iso-staging"
VERSION="${1:-v1.0.0}"
ISO_NAME="vdi-offline-${VERSION}"

mkdir -p "${DIST_DIR}"

# 使用 lib/iso.sh 的 pack_iso 函数
pack_iso \
    "${DIST_DIR}/${ISO_NAME}.iso" \
    "${ISO_ROOT}" \
    "${ISO_ROOT}/efi/boot/efiboot.img" \
    "VDI-INSTALL"

# 清理 ISO 暂存目录
rm -rf "${ISO_ROOT}"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/package-iso/iso.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/package-iso/iso.sh
git commit -m "feat(iso-builder): 创建 iso.sh xorriso 打包脚本"
```

---

### Task 4.6: 创建 scripts/package-iso/pxe.sh

**Files:**
- Create: `iso-builder/scripts/package-iso/pxe.sh`

- [ ] **Step 1: 创建 PXE 产物生成脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/package-iso/pxe.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 生成 PXE 启动产物（参考 Harvester 的 PXE 文件输出）

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
source "${WORKSPACE}/scripts/common.sh"

CACHE_DIR="${WORKSPACE}/cache"
DIST_DIR="${WORKSPACE}/dist"
ISO_ROOT="${CACHE_DIR}/iso-staging"
PXE_DIR="${DIST_DIR}/pxe"

# ISO 可能已经被 iso.sh 清理，从 squashfs 产物读取
# 如果 ISO_ROOT 已清理，从 dist/ 中提取
SQUASHFS="${ISO_ROOT}/casper/filesystem.squashfs"

mkdir -p "${PXE_DIR}"

# 尝试从 ISO staging 目录复制
if [ -f "${ISO_ROOT}/casper/vmlinuz" ]; then
    cp "${ISO_ROOT}/casper/vmlinuz" "${PXE_DIR}/"
    cp "${ISO_ROOT}/casper/initrd" "${PXE_DIR}/"
    cp "${ISO_ROOT}/casper/filesystem.squashfs" "${PXE_DIR}/rootfs.squashfs"
else
    # 从已生成的 ISO 中提取（使用 xorriso）
    ISO_FILE=$(ls -t "${DIST_DIR}"/*.iso 2>/dev/null | head -1)
    if [ -n "$ISO_FILE" ]; then
        step "从 ISO 提取 PXE 文件"
        local_tmp="$(mktemp -d)"
        xorriso -osirrox on -indev "$ISO_FILE" \
            -extract /casper/vmlinuz "${PXE_DIR}/vmlinuz" \
            -extract /casper/initrd "${PXE_DIR}/initrd" \
            -extract /casper/filesystem.squashfs "${PXE_DIR}/rootfs.squashfs"
        rm -rf "$local_tmp"
    else
        warn "无可用的 ISO 或 staging 目录，跳过 PXE 产物生成"
        exit 0
    fi
fi

ok "PXE 产物已生成: ${PXE_DIR}/"
ls -lh "${PXE_DIR}/"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/package-iso/pxe.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/package-iso/pxe.sh
git commit -m "feat(iso-builder): 创建 pxe.sh PXE 启动产物生成脚本"
```

---

### Task 4.7: 创建 scripts/package-iso/checksum.sh

**Files:**
- Create: `iso-builder/scripts/package-iso/checksum.sh`

- [ ] **Step 1: 创建校验和 + version.yaml 生成脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/package-iso/checksum.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 生成 ISO 校验和和 version.yaml 构建元数据

WORKSPACE="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION="${1:-v1.0.0}"
ISO_NAME="vdi-offline-${VERSION}"

source "${WORKSPACE}/scripts/common.sh"

DIST_DIR="${WORKSPACE}/dist"
ISO_FILE="${DIST_DIR}/${ISO_NAME}.iso"
MANIFEST="${WORKSPACE}/manifest.yaml"

# ISO SHA256 校验和
sha256sum "$ISO_FILE" > "${ISO_FILE}.sha256"
ok "校验和已生成: ${ISO_FILE}.sha256"

# 生成 version.yaml（构建元数据）
cat > "${DIST_DIR}/version.yaml" << VERSION
# VDI 离线 ISO 构建信息
# 由 package-iso 阶段自动生成

name: vdi-offline-iso
version: "${VERSION}"
buildDate: "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
buildHost: "$(hostname)"
arch: amd64
os: ubuntu-22.04
pipeline: "3-stage (build-rootfs / build-bundle / package-iso)"
VERSION

# 读取 manifest.yaml 中的组件版本
if [ -f "$MANIFEST" ]; then
    echo "components:" >> "${DIST_DIR}/version.yaml"
    for comp in kubernetes kube-vip kube-ovn longhorn kubevirt cdi kagent; do
        ver=$(yq ".components.${comp}.version // \"\"" "$MANIFEST" 2>/dev/null || echo "")
        [ -n "$ver" ] && echo "  ${comp}: \"${ver}\"" >> "${DIST_DIR}/version.yaml"
    done
fi

# ISO 大小和校验和
if [ -f "$ISO_FILE" ]; then
    ISO_SIZE=$(du -m "$ISO_FILE" | cut -f1)
    ISO_SHA=$(sha256sum "$ISO_FILE" | cut -d' ' -f1)
    cat >> "${DIST_DIR}/version.yaml" << VERSION

isoSize: "${ISO_SIZE}MB"
isoSha256: "${ISO_SHA}"
VERSION
fi

ok "version.yaml 已生成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/package-iso/checksum.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/package-iso/checksum.sh
git commit -m "feat(iso-builder): 创建 checksum.sh 校验和和 version.yaml 生成脚本"
```

---

## P4 完成标准

- [ ] `iso/boot/grub/grub.cfg` 和 `iso/isolinux/isolinux.cfg` 模板就绪
- [ ] `scripts/package-iso/entry` 可被 Makefile 正确调用
- [ ] `make iso` 产出完整的可启动 ISO
- [ ] ISO 支持 BIOS (isolinux) 和 UEFI (GRUB) 双模式启动
- [ ] PXE 产物 (vmlinuz + initrd + rootfs.squashfs) 输出到 `dist/pxe/`
- [ ] `dist/version.yaml` 包含构建元数据和组件版本
- [ ] ISO 校验和文件正确生成
