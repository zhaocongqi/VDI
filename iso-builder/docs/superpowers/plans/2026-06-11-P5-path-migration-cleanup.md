# P5: 路径迁移 & 清理 — offline→bundle 全局更新、遗留删除

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有路径引用从 `offline/` 改为 `bundle/`，删除遗留脚本和旧目录，更新文档。

**Architecture:** 此计划纯粹是路径替换和清理，不涉及新功能开发。

**Tech Stack:** Bash, sed, git

**前置依赖:** P1-P4 完成

---

### Task 5.1: 更新 load-offline-images 路径引用

**Files:**
- Modify: `iso-builder/scripts/load-offline-images`

**变更:** `OFFLINE_BASE` 默认值从 `/cdrom/offline` 改为 `/cdrom/bundle`，镜像导入逻辑改为基于 metadata.yaml 的 tar.zst 格式。

- [ ] **Step 1: 重写 load-offline-images**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/load-offline-images << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 离线容器镜像加载脚本
# [部署时] 将 docker-archive + zstd 格式镜像导入到 containerd k8s.io 命名空间
# 基于 metadata.yaml 索引逐条导入

# 离线资源路径（优先 bundle/，兼容旧版 offline/）
OFFLINE_BASE="${OFFLINE_BASE:-}"
if [ -z "$OFFLINE_BASE" ]; then
    if [ -d /cdrom/bundle ]; then
        OFFLINE_BASE="/cdrom/bundle"
    elif [ -d /cdrom/offline ]; then
        OFFLINE_BASE="/cdrom/offline"
    elif [ -d /mnt/iso/bundle ]; then
        OFFLINE_BASE="/mnt/iso/bundle"
    elif [ -d /mnt/iso/offline ]; then
        OFFLINE_BASE="/mnt/iso/offline"
    fi
fi

OFFLINE_IMAGES="${OFFLINE_IMAGES:-${OFFLINE_BASE}/images}"
METADATA="${OFFLINE_BASE}/metadata.yaml"

# 日志
LOG_DIR="/var/log/vdi-deploy"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/images.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 基于 metadata.yaml 导入镜像
load_from_metadata() {
    local metadata="$1"
    local image_count
    image_count=$(yq '.images | length' "$metadata" 2>/dev/null || echo "0")
    [ "$image_count" = "0" ] && { log "metadata.yaml 中无镜像定义"; return 0; }

    log "从 metadata.yaml 导入 ${image_count} 个镜像"

    for i in $(seq 0 $((image_count - 1))); do
        local name tag file
        name=$(yq ".images[${i}].name" "$metadata")
        tag=$(yq ".images[${i}].tag" "$metadata")
        file=$(yq ".images[${i}].file" "$metadata")

        local zst_file="${OFFLINE_BASE}/${file}"
        local full_name="${name}:${tag}"

        if [ ! -f "$zst_file" ]; then
            log "[WARN] 文件不存在: ${zst_file}"
            continue
        fi

        log "  [DECOMPRESS] $(basename "$zst_file")"
        local tar_file="${zst_file%.zst}"
        zstd -d "$zst_file" -o "$tar_file" -f -q

        log "  [IMPORT] ${full_name}"
        if ctr -n k8s.io images import "$tar_file" 2>/dev/null; then
            log "  [OK] ${full_name}"
        else
            log "  [FAIL] ${full_name}"
        fi
        rm -f "$tar_file"
    done
}

# 回退：扫描目录导入（兼容旧版 OCI 格式）
load_from_directory() {
    local images_dir="$1"
    log "从目录扫描导入镜像: ${images_dir}"

    for comp_dir in "${images_dir}"/*/; do
        [ ! -d "$comp_dir" ] && continue
        local component
        component=$(basename "$comp_dir")

        log "导入组件: ${component}"
        for file in "$comp_dir"/*.tar.zst; do
            [ ! -f "$file" ] && continue
            local tar_file="${file%.zst}"
            zstd -d "$file" -o "$tar_file" -f -q
            ctr -n k8s.io images import "$tar_file" 2>/dev/null && \
                log "  [OK] $(basename "$file")" || \
                log "  [FAIL] $(basename "$file")"
            rm -f "$tar_file"
        done
    done
}

# 主入口
COMPONENT="${1:-all}"

log "开始导入离线镜像 (OFFLINE_BASE=${OFFLINE_BASE})"

if [ -f "$METADATA" ]; then
    load_from_metadata "$METADATA"
else
    log "metadata.yaml 不存在，回退到目录扫描模式"
    load_from_directory "$OFFLINE_IMAGES"
fi

log "镜像导入完成"
ctr -n k8s.io images ls 2>/dev/null | head -20 | tee -a "$LOG_FILE"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/load-offline-images
```

- [ ] **Step 2: 提交**

```bash
git add scripts/load-offline-images
git commit -m "refactor(iso-builder): load-offline-images 改为基于 metadata.yaml 的 tar.zst 导入"
```

---

### Task 5.2: 更新 setup-local-repo 和 verify-offline-pack 路径

**Files:**
- Modify: `iso-builder/scripts/setup-local-repo`
- Modify: `iso-builder/scripts/verify-offline-pack`

- [ ] **Step 1: 更新 setup-local-repo**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/setup-local-repo << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 配置本地 APT 仓库
# [部署时] 将 ISO 中的 deb 包配置为本地 APT 源

# 路径兼容：优先 bundle/，回退 offline/
OFFLINE_BASE="${OFFLINE_BASE:-}"
if [ -z "$OFFLINE_BASE" ]; then
    for dir in /cdrom/bundle /cdrom/offline /mnt/iso/bundle /mnt/iso/offline; do
        [ -d "$dir" ] && OFFLINE_BASE="$dir" && break
    done
fi

OFFLINE_PACKAGES="${OFFLINE_PACKAGES:-${OFFLINE_BASE}/packages/deb}"
DEB_DIR="${OFFLINE_PACKAGES}"

if [ ! -d "$DEB_DIR" ]; then
    echo "[WARN] Offline deb dir not found: ${DEB_DIR}"
    exit 0
fi

echo "Setting up local APT repo..."

# 生成 Packages 索引（如果不存在）
if [ ! -f "${DEB_DIR}/Packages.gz" ]; then
    cd "$DEB_DIR"
    dpkg-scanpackages . /dev/null 2>/dev/null | gzip -9c > Packages.gz
fi

# 写入 APT 源配置
cat > /etc/apt/sources.list.d/vdi-offline.list <<EOF
deb [trusted=yes] file://${DEB_DIR} ./
EOF

# 更新索引
apt-get update -o Dir::Etc::sourcelist="/etc/apt/sources.list.d/vdi-offline.list" \
    -o Dir::Etc::sourceparts="-" -o APT::Get::List-Cleanup="0"

echo "[OK] Local APT repo configured"
echo "  Source: file://${DEB_DIR}"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/setup-local-repo
```

- [ ] **Step 2: 更新 verify-offline-pack**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/verify-offline-pack << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 离线资源校验脚本
# [部署时] 验证 ISO 中离线资源的完整性

# 路径兼容
OFFLINE_BASE="${OFFLINE_BASE:-}"
if [ -z "$OFFLINE_BASE" ]; then
    for dir in /cdrom/bundle /cdrom/offline /mnt/iso/bundle /mnt/iso/offline; do
        [ -d "$dir" ] && OFFLINE_BASE="$dir" && break
    done
fi

CHECKSUM_FILE="${OFFLINE_BASE}/checksums.sha256"

if [ ! -f "$CHECKSUM_FILE" ]; then
    echo "[WARN] Checksum file not found: ${CHECKSUM_FILE}"
    exit 0
fi

echo "Verifying offline resources..."

if sha256sum -c "$CHECKSUM_FILE" --quiet 2>/dev/null; then
    echo "[OK] Offline pack verified"
    exit 0
else
    echo "[FAIL] Offline pack corrupted, re-download ISO" >&2
    exit 1
fi
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/verify-offline-pack
```

- [ ] **Step 3: 提交**

```bash
git add scripts/setup-local-repo scripts/verify-offline-pack
git commit -m "refactor(iso-builder): 部署时脚本路径兼容 bundle/ 和 offline/"
```

---

### Task 5.3: 更新 TUI offline.py 路径

**Files:**
- Modify: `iso-builder/tui/utils/offline.py`

**变更:** `_detect()` 方法同时搜索 `bundle` 和 `offline` 目录。

- [ ] **Step 1: 更新 _detect 方法**

将 `offline.py` 的 `_detect` 方法修改为：

```python
    def _detect(self):
        """检测离线资源路径（兼容 bundle/ 和 offline/）"""
        resource_names = ["bundle", "offline"]
        for path in self.MOUNT_CANDIDATES:
            for name in resource_names:
                resource_path = os.path.join(path, name)
                if os.path.isdir(resource_path):
                    self.base_dir = resource_path
                    logger.info(f"检测到离线资源: {self.base_dir}")
                    return
```

- [ ] **Step 2: 更新 get_manifest 方法**

将 `get_manifest` 中的 manifest.yaml 路径适配顶层位置：

```python
    def get_manifest(self):
        """读取离线资源清单"""
        # 优先从 bundle/metadata.yaml 读取
        metadata_path = self.get_path("metadata.yaml")
        if metadata_path and os.path.exists(metadata_path):
            try:
                import yaml
                with open(metadata_path, "r") as f:
                    return yaml.safe_load(f)
            except Exception as e:
                logger.error(f"Failed to read metadata: {e}")

        # 回退到 manifest.yaml
        manifest_path = self.get_path("manifest.yaml")
        if not manifest_path or not os.path.exists(manifest_path):
            return None
        try:
            import yaml
            with open(manifest_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to read manifest: {e}")
            return None
```

- [ ] **Step 3: 提交**

```bash
git add tui/utils/offline.py
git commit -m "refactor(iso-builder): TUI OfflineManager 兼容 bundle/ 和 offline/ 路径"
```

---

### Task 5.4: 更新 configs/env-config.sh 路径

**Files:**
- Modify: `iso-builder/configs/env-config.sh`

- [ ] **Step 1: 更新离线检测路径**

将 env-config.sh 的离线检测段（第 33-53 行）替换为：

```bash
# ========== 离线环境变量（ISO 挂载后自动设置）==========
# 检测 ISO 挂载点（优先 bundle/，兼容 offline/）
if [ -d /cdrom/bundle ]; then
    OFFLINE_BASE="/cdrom/bundle"
elif [ -d /cdrom/offline ]; then
    OFFLINE_BASE="/cdrom/offline"
elif [ -d /mnt/iso/bundle ]; then
    OFFLINE_BASE="/mnt/iso/bundle"
elif [ -d /mnt/iso/offline ]; then
    OFFLINE_BASE="/mnt/iso/offline"
fi

if [ -n "${OFFLINE_BASE:-}" ]; then
    export OFFLINE_BASE
    export OFFLINE_BINARIES="${OFFLINE_BASE}/binaries"
    export OFFLINE_IMAGES="${OFFLINE_BASE}/images"
    export OFFLINE_CHARTS="${OFFLINE_BASE}/charts"
    export OFFLINE_MANIFESTS="${OFFLINE_BASE}/k8s-manifests"
    export OFFLINE_PACKAGES="${OFFLINE_BASE}/packages/deb"

    # 将离线工具加入 PATH
    export PATH="${OFFLINE_BINARIES}:${PATH}"

    echo "[Offline] Resource path: ${OFFLINE_BASE}"
fi
```

- [ ] **Step 2: 提交**

```bash
git add configs/env-config.sh
git commit -m "refactor(iso-builder): env-config.sh 离线路径兼容 bundle/ 和 offline/"
```

---

### Task 5.5: 删除遗留脚本和旧目录

**Files:**
- Delete: `iso-builder/scripts/build-iso` (遗留构建脚本)
- Delete: `iso-builder/scripts/build-iso-lb` (当前构建脚本，已被三阶段取代)
- Delete: `iso-builder/scripts/create-live` (遗留 debootstrap)
- Delete: `iso-builder/scripts/generate-iso` (遗留 xorriso)
- Delete: `iso-builder/scripts/integrate-offline` (遗留离线整合)
- Delete: `iso-builder/scripts/integrate-tui` (遗留 TUI 整合)
- Delete: `iso-builder/scripts/download-resources` (已被 build-bundle/entry 取代)
- Delete: `iso-builder/scripts/download-images` (已被 build-bundle/images.sh 取代)
- Delete: `iso-builder/scripts/download-binaries` (已被 build-bundle/binaries.sh 取代)
- Delete: `iso-builder/scripts/download-charts` (已被 build-bundle/charts.sh 取代)
- Delete: `iso-builder/scripts/download-manifests` (已被 build-bundle/manifests.sh 取代)
- Delete: `iso-builder/scripts/download-packages` (已被 build-bundle/packages.sh 取代)
- Delete: `iso-builder/scripts/generate-manifest` (已被 package-iso/checksum.sh 取代)
- Delete: `iso-builder/lb-config/` (已迁移到 rootfs/)
- Delete: `iso-builder/offline/` (已迁移到 cache/bundle/，manifest.yaml 在顶层)

- [ ] **Step 1: 删除遗留脚本**

```bash
cd /home/zcq/Github/VDI/iso-builder

# 删除遗留构建脚本
rm -f scripts/build-iso
rm -f scripts/build-iso-lb
rm -f scripts/create-live
rm -f scripts/generate-iso
rm -f scripts/integrate-offline
rm -f scripts/integrate-tui

# 删除已迁移的下载脚本
rm -f scripts/download-resources
rm -f scripts/download-images
rm -f scripts/download-binaries
rm -f scripts/download-charts
rm -f scripts/download-manifests
rm -f scripts/download-packages
rm -f scripts/generate-manifest
```

- [ ] **Step 2: 删除旧目录**

```bash
# 删除 lb-config/（已迁移到 rootfs/）
rm -rf lb-config/

# 删除 offline/（manifest.yaml 已在顶层，资源在 cache/bundle/）
rm -rf offline/
```

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "chore(iso-builder): 删除遗留脚本和旧目录（迁移到三阶段 pipeline）"
```

---

### Task 5.6: 更新 CLAUDE.md

**Files:**
- Modify: `iso-builder/CLAUDE.md`

- [ ] **Step 1: 重写 CLAUDE.md 反映新架构**

```markdown
# CLAUDE.md — iso-builder AI 开发指南

## 项目概述

VDI 离线 ISO 构建系统，产出一个包含完整离线部署资源的 Live ISO。
启动后通过 TUI 引导用户在无互联网环境中部署 VDI 集群。

## 技术栈

- **构建环境**: Docker + Dapper (Dockerfile.dapper)
- **Live 系统**: Ubuntu 22.04 + live-build (bootstrap/chroot) + squashfs
- **离线镜像**: docker-archive + zstd 压缩 (skopeo 下载，ctr 导入)
- **ISO 打包**: xorriso (BIOS isolinux + UEFI GRUB 双模式)
- **TUI**: Python 3 + whiptail（无额外 pip 依赖）
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
│   │   ├── entry        # 入口
│   │   ├── bootstrap.sh # live-build bootstrap+chroot
│   │   └── configure.sh # chroot hooks 执行
│   ├── build-bundle/    # 阶段 2: 离线资源打包
│   │   ├── entry        # 入口
│   │   ├── images.sh    # 容器镜像 (docker-archive+zstd)
│   │   ├── binaries.sh  # 二进制工具
│   │   ├── charts.sh    # Helm Charts
│   │   ├── manifests.sh # K8s YAML
│   │   ├── packages.sh  # deb 包
│   │   └── metadata.sh  # metadata.yaml 索引生成
│   └── package-iso/     # 阶段 3: ISO 打包
│       ├── entry        # 入口
│       ├── squashfs.sh  # squashfs 打包
│       ├── bootloader.sh # bootloader 配置生成
│       ├── iso.sh       # xorriso 打包
│       ├── pxe.sh       # PXE 产物生成
│       └── checksum.sh  # 校验和 + version.yaml
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
5. **OFFLINE_BASE 条件回退**: 部署脚本兼容 bundle/ 和 offline/ 路径
6. **TUI 通过 symlink**: /opt/vdi/tui → /cdrom/tui，不复制到 squashfs
7. **PXE 仅用于 Worker**: Master 必须手动部署

## 注意事项

- ISO 目标大小 < 8GB（不含 Windows VM 镜像）
- 仅支持 amd64 (x86_64)
- 目标 OS: Ubuntu 22.04 LTS
- TUI 运行需要 root 权限和 TTY 环境
```

- [ ] **Step 2: 提交**

```bash
git add CLAUDE.md
git commit -m "docs(iso-builder): 更新 CLAUDE.md 反映三阶段 pipeline 架构"
```

---

## P5 完成标准

- [ ] 所有部署时脚本兼容 `bundle/` 和 `offline/` 路径
- [ ] TUI `offline.py` 同时搜索 `bundle` 和 `offline` 目录
- [ ] `configs/env-config.sh` 路径兼容
- [ ] `rootfs/hooks/0300-tui-welcome.hook.chroot` 路径兼容
- [ ] 所有遗留脚本已删除
- [ ] `lb-config/` 和 `offline/` 目录已删除
- [ ] `CLAUDE.md` 反映新的三阶段架构
- [ ] `git status` 无遗留文件
