# P2: build-rootfs — rootfs 配置迁移 + 阶段脚本

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `lb-config/` 迁移到 `rootfs/`，创建 `scripts/build-rootfs/` 阶段脚本，`make build-rootfs` 可产出 `cache/rootfs/`。

**Architecture:** 保留 live-build 的 bootstrap + chroot 能力，但放弃 binary 阶段。rootfs hooks 不再复制 TUI 到 squashfs 内，改为 symlink 指向 `/cdrom/tui/`。

**Tech Stack:** live-build, debootstrap, chroot, bash

**前置依赖:** P1 完成

---

### Task 2.1: 迁移 rootfs 配置文件

**Files:**
- Copy: `iso-builder/lb-config/package-lists/` → `iso-builder/rootfs/package-lists/`
- Copy: `iso-builder/lb-config/hooks/normal/*.hook.chroot` → `iso-builder/rootfs/hooks/`
- Copy: `iso-builder/lb-config/includes.chroot/` → `iso-builder/rootfs/includes.chroot/`

- [ ] **Step 1: 复制 package-lists**

```bash
cd /home/zcq/Github/VDI/iso-builder
cp lb-config/package-lists/*.chroot rootfs/package-lists/
```

- [ ] **Step 2: 复制 chroot hooks**

```bash
cp lb-config/hooks/normal/*.hook.chroot rootfs/hooks/
chmod +x rootfs/hooks/*.chroot
```

注意：不复制 `lb-config/hooks/binary/` 下的 hooks，它们的功能将由 `scripts/package-iso/` 接管。

- [ ] **Step 3: 复制 includes.chroot（如果存在）**

```bash
if [ -d lb-config/includes.chroot ]; then
    rsync -a lb-config/includes.chroot/ rootfs/includes.chroot/
fi
```

- [ ] **Step 4: 提交**

```bash
git add rootfs/
git commit -m "refactor(iso-builder): 迁移 rootfs 配置到独立目录"
```

---

### Task 2.2: 修改 0300-tui-welcome.hook.chroot — 改用 symlink

**Files:**
- Modify: `iso-builder/rootfs/hooks/0300-tui-welcome.hook.chroot`

**变更:** TUI 不再复制到 squashfs 内，改为创建 symlink `/opt/vdi/tui → /cdrom/tui`。deploy 脚本同理。将 `offline` 路径改为 `bundle`（配合 P5 全局迁移）。

- [ ] **Step 1: 重写 hook**

```bash
cat > /home/zcq/Github/VDI/iso-builder/rootfs/hooks/0300-tui-welcome.hook.chroot << 'HOOK'
#!/bin/bash
set -euo pipefail

# Hook: TUI 自动启动 + 离线环境变量
# 重构后：TUI 通过 symlink 指向 /cdrom/tui/，不再复制到 squashfs

# 离线环境变量（profile.d 自动 source）
# 路径从 offline/ 改为 bundle/（配合设计文档第 8 节）
cat > /etc/profile.d/vdi-offline.sh <<'ENVEOF'
#!/bin/bash
# 离线环境变量（ISO 挂载后自动设置）

if [ -d /cdrom/bundle ]; then
    export OFFLINE_BASE="/cdrom/bundle"
elif [ -d /mnt/iso/bundle ]; then
    export OFFLINE_BASE="/mnt/iso/bundle"
elif [ -d /cdrom/offline ]; then
    export OFFLINE_BASE="/cdrom/offline"
elif [ -d /mnt/iso/offline ]; then
    export OFFLINE_BASE="/mnt/iso/offline"
else
    unset OFFLINE_BASE
fi

if [ -n "${OFFLINE_BASE:-}" ]; then
    export OFFLINE_BINARIES="${OFFLINE_BASE}/binaries"
    export OFFLINE_IMAGES="${OFFLINE_BASE}/images"
    export OFFLINE_CHARTS="${OFFLINE_BASE}/charts"
    export OFFLINE_MANIFESTS="${OFFLINE_BASE}/k8s-manifests"
    export OFFLINE_PACKAGES="${OFFLINE_BASE}/packages/deb"
    export PATH="${OFFLINE_BINARIES}:${PATH}"
    echo "[Offline] Resource path: ${OFFLINE_BASE}"
fi
ENVEOF
chmod +x /etc/profile.d/vdi-offline.sh

# 创建 symlink（TUI 和 deploy 从 ISO 根目录读取，不复制到 squashfs）
mkdir -p /opt/vdi
ln -sf /cdrom/tui /opt/vdi/tui
ln -sf /cdrom/scripts/deploy /opt/vdi/deploy

# TUI 欢迎脚本 + 自动启动
cat > /etc/profile.d/vdi-welcome.sh <<'WELCOME'
# VDI Live system welcome + TUI auto-start
if [ -n "$PS1" ]; then
    echo ""
    echo "============================================"
    echo "  VDI Offline Deploy Live System"
    echo "============================================"
    echo ""
    echo "  Offline Resources: /cdrom/bundle/"
    echo "  Deploy Logs:       /var/log/vdi-deploy/"
    echo ""

    # Auto-start TUI on tty1 or ttyS0 as root
    CURRENT_TTY="$(tty 2>/dev/null)"
    IS_ROOT="$(id -u)"
    echo "[vdi-welcome] tty=${CURRENT_TTY} uid=${IS_ROOT} TERM=${TERM:-unset}"
    if [ "$IS_ROOT" -eq 0 ] && { [ "$CURRENT_TTY" = "/dev/tty1" ] || [ "$CURRENT_TTY" = "/dev/ttyS0" ]; }; then
        export TERM="${TERM:-linux}"
        echo "[vdi-welcome] Starting TUI installer..."
        python3 /opt/vdi/tui/installer.py 2>>/var/log/vdi-deploy/installer-stderr.log
        TUI_EXIT=$?
        echo "[vdi-welcome] TUI installer exited (code: ${TUI_EXIT})"
        echo "  Restart manually: python3 /opt/vdi/tui/installer.py"
        echo ""
    else
        echo "[vdi-welcome] TUI skipped (not root TTY)"
    fi
fi
WELCOME

echo "[hook] TUI welcome setup done (symlink mode)"
HOOK
chmod +x /home/zcq/Github/VDI/iso-builder/rootfs/hooks/0300-tui-welcome.hook.chroot
```

- [ ] **Step 2: 提交**

```bash
git add rootfs/hooks/0300-tui-welcome.hook.chroot
git commit -m "refactor(iso-builder): TUI hook 改用 symlink 模式，离线路径改为 bundle/"
```

---

### Task 2.3: 创建 scripts/build-rootfs/entry

**Files:**
- Create: `iso-builder/scripts/build-rootfs/entry`

**职责:** 阶段 1 入口，编排 bootstrap → configure 流程。

- [ ] **Step 1: 创建 entry 脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-rootfs/entry << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 阶段 1: build-rootfs 入口
# 构建 Ubuntu Live rootfs，产出 cache/rootfs/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-v1.0.0}"

source "${SCRIPT_DIR}/../common.sh"

ROOTFS_DIR="${WORKSPACE}/rootfs"
CACHE_DIR="${WORKSPACE}/cache"
ROOTFS_CACHE="${CACHE_DIR}/rootfs"
BOOTSTRAP_CACHE="${CACHE_DIR}/bootstrap.tar"
LB_DIR="${CACHE_DIR}/lb-work"

echo "============================================"
echo "  阶段 1: build-rootfs"
echo "  版本: ${VERSION}"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

mkdir -p "${CACHE_DIR}"

# ========== Bootstrap ==========
if [ -f "${BOOTSTRAP_CACHE}" ] && [ "${SKIP_BOOTSTRAP:-0}" = "1" ]; then
    step "跳过 bootstrap（使用缓存）"
    mkdir -p "${ROOTFS_CACHE}"
    tar -xf "${BOOTSTRAP_CACHE}" -C "${ROOTFS_CACHE}"
else
    step "Bootstrap 阶段 (debootstrap)"
    source "${SCRIPT_DIR}/bootstrap.sh"
fi

# ========== Configure ==========
step "Configure 阶段 (chroot hooks)"
source "${SCRIPT_DIR}/configure.sh"

# ========== 阶段校验 ==========
step "校验 rootfs"
validate_file "${ROOTFS_CACHE}/bin/bash" "rootfs 基础" || exit 1

KERNEL=$(find "${ROOTFS_CACHE}/boot" -name "vmlinuz-*" -type f 2>/dev/null | head -1)
if [ -z "$KERNEL" ]; then
    error "rootfs 中未找到内核文件"
    exit 1
fi

# 保存 bootstrap 缓存（如果不存在）
if [ ! -f "${BOOTSTRAP_CACHE}" ]; then
    step "保存 bootstrap 缓存"
    tar -cf "${BOOTSTRAP_CACHE}" -C "${ROOTFS_CACHE}" .
fi

ok "阶段 1 完成: cache/rootfs/"
echo "  大小: $(du -sh "${ROOTFS_CACHE}" | cut -f1)"
echo "============================================"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-rootfs/entry
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-rootfs/entry
git commit -m "feat(iso-builder): 创建 build-rootfs 阶段入口脚本"
```

---

### Task 2.4: 创建 scripts/build-rootfs/bootstrap.sh

**Files:**
- Create: `iso-builder/scripts/build-rootfs/bootstrap.sh`

**职责:** 使用 live-build 的 `lb config` + `lb bootstrap` + `lb chroot` 构建基础 rootfs。

- [ ] **Step 1: 创建 bootstrap.sh**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-rootfs/bootstrap.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# live-build bootstrap + chroot 阶段
# 产出: cache/rootfs/ (完整 chroot 目录树)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

ROOTFS_DIR="${WORKSPACE}/rootfs"
CACHE_DIR="${WORKSPACE}/cache"
ROOTFS_CACHE="${CACHE_DIR}/rootfs"
LB_DIR="${CACHE_DIR}/lb-work"

# 清理旧构建
rm -rf "${LB_DIR}"
mkdir -p "${LB_DIR}"

# 复制 live-build 配置到工作目录
cd "${LB_DIR}"

step "lb config"
lb config noauto \
    --distribution jammy \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --bootloader syslinux \
    --debian-installer none \
    --memtest none \
    --iso-application "VDI Offline Deploy" \
    --iso-publisher "VDI" \
    --iso-volume "VDI-INSTALL" \
    --parent-distribution jammy \
    --parent-mirror-bootstrap "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-chroot "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-chroot-security "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-binary "http://mirrors.aliyun.com/ubuntu" \
    --parent-mirror-binary-security "http://mirrors.aliyun.com/ubuntu" \
    --mirror-bootstrap "http://mirrors.aliyun.com/ubuntu" \
    --mirror-chroot "http://mirrors.aliyun.com/ubuntu" \
    --mirror-chroot-security "http://mirrors.aliyun.com/ubuntu" \
    --mirror-binary "http://mirrors.aliyun.com/ubuntu" \
    --mirror-binary-security "http://mirrors.aliyun.com/ubuntu" \
    --archive-areas "main universe" \
    --security true \
    --backports false \
    --chroot-filesystem squashfs \
    --initramfs live-boot \
    --initsystem systemd \
    --bootappend-live "boot=live live-media-path=/casper console=ttyS0,115200 console=tty0"
ok "lb config 完成"

# 同步项目配置到 config/ 目录
step "同步配置到 config/"
# Package lists
if [ -d "${ROOTFS_DIR}/package-lists" ]; then
    mkdir -p config/package-lists
    cp "${ROOTFS_DIR}"/package-lists/*.chroot config/package-lists/ 2>/dev/null || true
    ok "Package lists 已同步"
fi
# Includes（不复制 TUI，由 symlink 代替）
if [ -d "${ROOTFS_DIR}/includes.chroot" ]; then
    mkdir -p config/includes.chroot
    rsync -a "${ROOTFS_DIR}/includes.chroot/" config/includes.chroot/
    ok "Includes 已同步"
fi

# Bootstrap 阶段
step "lb bootstrap"
lb bootstrap

# Chroot 阶段（安装包列表中的所有包）
step "lb chroot"
lb chroot

# 将 chroot 产物复制到缓存目录
step "复制 rootfs 到缓存"
rm -rf "${ROOTFS_CACHE}"
cp -a "${LB_DIR}/chroot" "${ROOTFS_CACHE}"

# 清理 lb 工作目录（保留 chroot 产物在缓存中）
rm -rf "${LB_DIR}"

ok "Bootstrap + chroot 完成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-rootfs/bootstrap.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-rootfs/bootstrap.sh
git commit -m "feat(iso-builder): 创建 bootstrap.sh 使用 live-build 构建 rootfs"
```

---

### Task 2.5: 创建 scripts/build-rootfs/configure.sh

**Files:**
- Create: `iso-builder/scripts/build-rootfs/configure.sh`

**职责:** 在 chroot 环境中执行 hooks（系统配置、服务设置、TUI 欢迎脚本）。

- [ ] **Step 1: 创建 configure.sh**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-rootfs/configure.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 在 chroot 中执行 hooks
# 从 rootfs/hooks/ 读取所有 .chroot hooks 并在 cache/rootfs/ 中执行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

ROOTFS_DIR="${WORKSPACE}/rootfs"
ROOTFS_CACHE="${WORKSPACE}/cache/rootfs"
HOOKS_DIR="${ROOTFS_DIR}/hooks"

if [ ! -d "${HOOKS_DIR}" ]; then
    info "无 chroot hooks 目录"
    exit 0
fi

CHROOT_DIR="${ROOTFS_CACHE}"
validate_dir "${CHROOT_DIR}" "rootfs 缓存" || exit 1

step "执行 chroot hooks"

for hook in "${HOOKS_DIR}"/*.chroot; do
    [ -f "$hook" ] || continue
    hook_name="$(basename "$hook")"
    info "执行 hook: ${hook_name}"

    # 复制 hook 到 chroot /tmp/
    cp "$hook" "${CHROOT_DIR}/tmp/${hook_name}"
    chmod +x "${CHROOT_DIR}/tmp/${hook_name}"

    # 在 chroot 中执行
    if chroot "${CHROOT_DIR}" "/tmp/${hook_name}"; then
        ok "Hook 成功: ${hook_name}"
    else
        error "Hook 失败: ${hook_name}"
        exit 1
    fi

    rm -f "${CHROOT_DIR}/tmp/${hook_name}"
done

ok "所有 chroot hooks 执行完成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-rootfs/configure.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-rootfs/configure.sh
git commit -m "feat(iso-builder): 创建 configure.sh 执行 chroot hooks"
```

---

## P2 完成标准

- [ ] `rootfs/` 目录包含所有从 `lb-config/` 迁移的配置
- [ ] `rootfs/hooks/0300-tui-welcome.hook.chroot` 使用 symlink 模式
- [ ] `scripts/build-rootfs/entry` 可被 Makefile 正确调用
- [ ] `scripts/build-rootfs/bootstrap.sh` 使用 live-build 构建 rootfs
- [ ] `scripts/build-rootfs/configure.sh` 执行 chroot hooks
- [ ] `SKIP_BOOTSTRAP=1 make build-rootfs` 支持增量构建（使用 bootstrap 缓存）
- [ ] 产出 `cache/rootfs/` 包含完整 chroot 目录树和内核文件
