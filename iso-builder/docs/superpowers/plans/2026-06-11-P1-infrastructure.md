# P1: 基础设施 — 目录结构、共享函数库、Dockerfile、Makefile 框架

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立三阶段 pipeline 的目录骨架和基础设施，使 `make shell` 可用。

**Architecture:** 参考 Harvester 的 `scripts/lib/` 模式，创建共享函数库。重写 Makefile 为三阶段编排入口。更新 Dockerfile.dapper 增加新工具依赖。

**Tech Stack:** Bash, Docker, Makefile, live-build

---

### Task 1.1: 创建目录结构骨架

**Files:**
- Create: `iso-builder/scripts/lib/` (目录)
- Create: `iso-builder/scripts/build-rootfs/` (目录)
- Create: `iso-builder/scripts/build-bundle/` (目录)
- Create: `iso-builder/scripts/package-iso/` (目录)
- Create: `iso-builder/rootfs/` (目录)
- Create: `iso-builder/iso/` (目录)
- Create: `iso-builder/cache/` (目录，加入 .gitignore)

- [ ] **Step 1: 创建所有新目录**

```bash
cd /home/zcq/Github/VDI/iso-builder

# 三阶段脚本目录
mkdir -p scripts/lib
mkdir -p scripts/build-rootfs
mkdir -p scripts/build-bundle
mkdir -p scripts/package-iso

# rootfs 配置目录（先创建，后续 P2 迁移内容）
mkdir -p rootfs/package-lists
mkdir -p rootfs/hooks
mkdir -p rootfs/includes.chroot

# ISO 模板目录（先创建，后续 P4 迁移内容）
mkdir -p iso/boot/grub
mkdir -p iso/isolinux

# 构建缓存目录
mkdir -p cache
```

- [ ] **Step 2: 更新 .gitignore，添加 cache/ 和 dist/**

文件: `iso-builder/.gitignore`（如不存在则创建）

```
# 构建缓存和产物
cache/
dist/

# live-build 工作目录
config/
chroot/
binary/
build.log

# 临时文件
*.tar
*.tar.zst
tmp/
```

- [ ] **Step 3: 提交**

```bash
git add .gitignore scripts/lib/ scripts/build-rootfs/ scripts/build-bundle/ scripts/package-iso/ rootfs/ iso/ cache/
git commit -m "chore(iso-builder): 创建三阶段 pipeline 目录骨架"
```

---

### Task 1.2: 创建共享函数库 scripts/lib/image.sh

**Files:**
- Create: `iso-builder/scripts/lib/image.sh`

**职责:** 镜像拉取/保存/校验函数（参考 Harvester 的 `scripts/lib/image`）

- [ ] **Step 1: 创建 image.sh**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/lib/image.sh << 'SCRIPT'
#!/bin/bash
# 镜像拉取/保存/校验函数库
# 参考 Harvester scripts/lib/image 的设计模式

# 生成安全文件名：将 registry/path/image:tag 转换为 registry_path_image_tag
image_safe_name() {
    local image="$1"
    echo "$image" | sed 's|[/:]|_|g'
}

# 从 manifest.yaml 提取所有组件的所有镜像列表
# 输出格式: 每行一个 "component image_url"
image_list_all() {
    local manifest="$1"
    local components
    components=$(yq '.components | keys | .[]' "$manifest")

    for comp in $components; do
        local images
        images=$(yq ".components.${comp}.images[]" "$manifest" 2>/dev/null || true)
        [ -z "$images" ] && continue
        while IFS= read -r img; do
            echo "${comp} ${img}"
        done <<< "$images"
    done
}

# 下载单个镜像为 docker-archive + zstd 压缩
# 用法: image_pull_and_compress "registry.k8s.io/kube-apiserver:v1.34.3" "/path/to/output" "component"
image_pull_and_compress() {
    local image="$1"
    local output_dir="$2"
    local component="$3"

    local safe_name
    safe_name=$(image_safe_name "$image")
    local tar_file="${output_dir}/${component}/${safe_name}.tar"
    local zst_file="${tar_file}.zst"

    # 跳过已存在的文件
    if [ -f "$zst_file" ]; then
        echo "  [SKIP] ${image} (已存在)"
        return 0
    fi

    mkdir -p "${output_dir}/${component}"

    echo "  [PULL] ${image}"
    if ! skopeo copy --override-os linux --override-arch amd64 \
        "docker://${image}" "docker-archive:${tar_file}" 2>&1; then
        echo "  [FAIL] ${image}" >&2
        rm -f "$tar_file"
        return 1
    fi

    echo "  [COMPRESS] ${safe_name}.tar -> ${safe_name}.tar.zst"
    zstd -19 "$tar_file" -o "$zst_file" --rm -q

    echo "  [OK] ${image}"
    return 0
}

# 解压并导入单个镜像到 containerd
# 用法: image_decompress_and_import "/path/to/file.tar.zst"
image_decompress_and_import() {
    local zst_file="$1"
    local tar_file="${zst_file%.zst}"

    if [ ! -f "$zst_file" ]; then
        echo "[FAIL] 文件不存在: ${zst_file}" >&2
        return 1
    fi

    echo "  [DECOMPRESS] $(basename "$zst_file")"
    zstd -d "$zst_file" -o "$tar_file" -f -q

    echo "  [IMPORT] ${tar_file}"
    if ctr -n k8s.io images import "$tar_file" 2>/dev/null; then
        rm -f "$tar_file"
        return 0
    else
        rm -f "$tar_file"
        echo "  [FAIL] ctr import 失败" >&2
        return 1
    fi
}
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/lib/image.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/lib/image.sh
git commit -m "feat(iso-builder): 添加镜像拉取/保存共享函数库"
```

---

### Task 1.3: 创建共享函数库 scripts/lib/iso.sh

**Files:**
- Create: `iso-builder/scripts/lib/iso.sh`

**职责:** xorriso 封装函数（参考 Harvester 的 `scripts/lib/iso` 的 `pack_iso`）

- [ ] **Step 1: 创建 iso.sh**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/lib/iso.sh << 'SCRIPT'
#!/bin/bash
# ISO 打包封装函数库
# 参考 Harvester scripts/lib/iso 的 pack_iso 函数

# 使用 xorriso 打包 ISO
# 用法: pack_iso <iso_output> <iso_root> <efi_img> <vol_id>
pack_iso() {
    local iso_output="$1"
    local iso_root="$2"
    local efi_img="$3"
    local vol_id="${4:-VDI-INSTALL}"

    require_cmds xorriso || return 1

    echo ">>> 打包 ISO: $(basename "$iso_output")"

    xorriso -volid "$vol_id" \
        -joliet on -padding 0 \
        -outdev "$iso_output" \
        -map "$iso_root" / -chmod 0755 -- \
        -append_partition 2 0xef "$efi_img" \
        -boot_image any cat_path="boot/boot.catalog" \
        -boot_image any cat_hidden=on \
        -boot_image any efi_path=--interval:appended_partition_2:all:: \
        -boot_image any platform_id=0xef \
        -boot_image any appended_part_as=gpt \
        -boot_image any partition_offset=16

    echo "    ISO 大小: $(du -sh "$iso_output" | cut -f1)"
}

# 创建 EFI 引导镜像
# 用法: create_efi_image <output_img> <grub_cfg_dir>
create_efi_image() {
    local output_img="$1"
    local grub_cfg_dir="$2"

    require_cmds grub-mkimage mkfs.vfat mmd mcopy || return 1

    local efi_tmp
    efi_tmp="$(mktemp -d)"
    mkdir -p "${efi_tmp}/EFI/BOOT"

    # 生成 standalone GRUB EFI 二进制
    grub-mkimage -O x86_64-efi \
        -o "${efi_tmp}/EFI/BOOT/BOOTX64.EFI" \
        -p "/boot/grub" \
        -d /usr/lib/grub/x86_64-efi \
        linux normal iso9660 part_msdos part_gpt fat \
        search search_fs_file search_fs_uuid search_label \
        serial terminal gfxterm gfxterm_background gfxterm_menu \
        halt reboot configfile echo ls cat chain loadenv

    # 创建 FAT12 镜像
    dd if=/dev/zero of="$output_img" bs=1M count=8 2>/dev/null
    mkfs.vfat -F 12 "$output_img"
    mmd -i "$output_img" ::EFI ::EFI/BOOT
    mcopy -i "$output_img" \
        "${efi_tmp}/EFI/BOOT/BOOTX64.EFI" "::EFI/BOOT/BOOTX64.EFI"

    rm -rf "$efi_tmp"
    echo "    EFI 镜像已创建: $(basename "$output_img")"
}

# 复制 isolinux 引导文件
# 用法: copy_isolinux_files <isolinux_dir>
copy_isolinux_files() {
    local isolinux_dir="$1"
    mkdir -p "$isolinux_dir"

    if [ -d /usr/lib/ISOLINUX ]; then
        cp /usr/lib/ISOLINUX/isolinux.bin "${isolinux_dir}/"
        cp /usr/lib/syslinux/modules/bios/ldlinux.c32 "${isolinux_dir}/" 2>/dev/null || true
        cp /usr/lib/syslinux/modules/bios/libcom32.c32 "${isolinux_dir}/" 2>/dev/null || true
        cp /usr/lib/syslinux/modules/bios/libutil.c32 "${isolinux_dir}/" 2>/dev/null || true
    elif [ -d /usr/lib/syslinux ]; then
        cp /usr/lib/syslinux/isolinux.bin "${isolinux_dir}/"
        cp /usr/lib/syslinux/ldlinux.c32 "${isolinux_dir}/" 2>/dev/null || true
    fi

    echo "    isolinux 文件已复制"
}

# 查找 isohdpfx.bin 路径
find_isohdpfx() {
    for path in /usr/lib/ISOLINUX/isohdpfx.bin /usr/lib/syslinux/mbr/isohdpfx.bin /usr/lib/syslinux/isohdpfx.bin; do
        [ -f "$path" ] && echo "$path" && return 0
    done
    return 1
}
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/lib/iso.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/lib/iso.sh
git commit -m "feat(iso-builder): 添加 xorriso/EFI 打包共享函数库"
```

---

### Task 1.4: 创建共享函数库 scripts/lib/template.sh

**Files:**
- Create: `iso-builder/scripts/lib/template.sh`

**职责:** 模板渲染函数（替代 sed 替换，支持 envsubst）

- [ ] **Step 1: 创建 template.sh**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/lib/template.sh << 'SCRIPT'
#!/bin/bash
# 模板渲染函数库
# 替代不安全的 sed 字符串替换，支持 envsubst 和 sed 变量注入

# 使用 sed 渲染简单模板（仅替换 ${VAR} 格式的变量）
# 用法: render_template <template_file> <output_file> VAR1=val1 VAR2=val2 ...
render_template() {
    local template="$1"
    local output="$2"
    shift 2

    cp "$template" "$output"

    # 逐个替换变量
    for pair in "$@"; do
        local key="${pair%%=*}"
        local val="${pair#*=}"
        sed -i "s|\${${key}}|${val}|g" "$output"
    done
}

# 使用 envsubst 渲染模板（支持所有环境变量）
# 用法: render_template_env <template_file> <output_file> [VAR1] [VAR2] ...
# 如果指定了变量名列表，仅替换这些变量；否则替换所有
render_template_env() {
    local template="$1"
    local output="$2"
    shift 2

    if [ $# -gt 0 ]; then
        # 仅替换指定的变量
        envsubst "$(printf '${%s} ' "$@")" < "$template" > "$output"
    else
        # 替换所有 ${VAR} 格式的变量
        envsubst < "$template" > "$output"
    fi
}
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/lib/template.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/lib/template.sh
git commit -m "feat(iso-builder): 添加模板渲染共享函数库"
```

---

### Task 1.5: 更新 Dockerfile.dapper

**Files:**
- Modify: `iso-builder/Dockerfile.dapper`

**变更:** 增加 `zstd`、`gettext-base`（提供 envsubst）包。yq 和 helm 已存在无需改动。

- [ ] **Step 1: 在构建工具安装段增加 zstd 和 gettext-base**

在 Dockerfile.dapper 的 `# ISO 构建工具` RUN 指令中（第 16 行附近），在包列表末尾增加：

将第 16-54 行的 RUN 指令中，在 `apt-utils` 行之后、`&& rm -rf /var/lib/apt/lists/*` 之前增加：

```
    # 新增：镜像压缩和模板渲染
    zstd \
    gettext-base \
```

完整修改后的 RUN 指令包列表段：

```dockerfile
# ISO 构建工具
RUN apt-get install -y -f --no-install-recommends \
    xorriso \
    squashfs-tools \
    isolinux \
    syslinux-common \
    grub-pc-bin \
    grub-efi-amd64-bin \
    grub2-common \
    mtools \
    dosfstools \
    # UEFI 签名引导
    grub-efi-amd64-signed \
    shim-signed \
    # PXE 引导
    pxelinux \
    # 运行时工具
    python3 \
    python3-yaml \
    whiptail \
    dialog \
    # 网络与下载
    wget \
    curl \
    jq \
    gpg \
    ca-certificates \
    gnupg \
    lsb-release \
    # PXE 服务组件
    dnsmasq \
    nginx \
    # 部署工具
    openssh-client \
    rsync \
    # 容器运行时
    containerd \
    # 其他工具
    apt-utils \
    # 新增：镜像压缩和模板渲染
    zstd \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: 验证 Dockerfile 语法**

```bash
cd /home/zcq/Github/VDI/iso-builder
docker build --check -f Dockerfile.dapper . 2>&1 || echo "如 --check 不支持，手动检查语法即可"
```

- [ ] **Step 3: 提交**

```bash
git add Dockerfile.dapper
git commit -m "feat(iso-builder): Dockerfile.dapper 增加 zstd 和 gettext-base 工具"
```

---

### Task 1.6: 重写 Makefile 为三阶段框架

**Files:**
- Modify: `iso-builder/Makefile`

**变更:** 保持 Dapper 容器化构建模式，重写内部 targets 为三阶段编排。

- [ ] **Step 1: 重写 Makefile**

```makefile
# VDI 离线 ISO 构建系统
# 三阶段 pipeline: build-rootfs → build-bundle → package-iso
# 参考 Harvester 的分层构建架构

# 版本信息
VERSION ?= v1.0.0
ISO_NAME ?= vdi-offline-$(VERSION)
DIST_DIR ?= dist

# 构建镜像名称
BUILDER_IMAGE ?= vdi-iso-builder

# Docker 网络模式（解决桥接网络 DNS 问题）
DOCKER_NET ?= --network host

# 构建环境挂载
DOCKER_RUN = docker run --rm \
	$(DOCKER_NET) \
	-v $(shell pwd):/workspace \
	-v /var/run/docker.sock:/var/run/docker.sock \
	--privileged \
	--cap-add SYS_ADMIN

# ========== 构建环境 ==========

.PHONY: build-builder
build-builder:
	docker build $(DOCKER_NET) -f Dockerfile.dapper -t $(BUILDER_IMAGE) .

.PHONY: shell
shell: build-builder
	docker run --rm -it \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		--privileged \
		$(BUILDER_IMAGE) \
		bash

# ========== 三阶段 pipeline ==========

# 完整构建
.PHONY: iso
iso: build-builder
	@echo "=== 开始构建 VDI 离线 ISO $(VERSION) ==="
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-rootfs/entry "$(VERSION)" && \
		          ./scripts/build-bundle/entry "$(VERSION)" && \
		          ./scripts/package-iso/entry "$(VERSION)"'
	@echo "=== 构建完成: $(DIST_DIR)/$(ISO_NAME).iso ==="

# 阶段 1: 构建 rootfs
.PHONY: build-rootfs
build-rootfs: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-rootfs/entry "$(VERSION)"'

# 阶段 2: 下载并打包离线资源
.PHONY: build-bundle
build-bundle: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-bundle/entry "$(VERSION)"'

.PHONY: download
download: build-bundle

# 阶段 3: 打包 ISO（依赖前两阶段）
.PHONY: package-iso
package-iso: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/package-iso/entry "$(VERSION)"'

# ========== 增量构建 ==========

# 仅重新打包 ISO（跳过 rootfs 和 bundle）
.PHONY: package-iso-only
package-iso-only: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/package-iso/entry "$(VERSION)"'

# 仅更新 bundle（跳过 rootfs）
.PHONY: build-bundle-only
build-bundle-only: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-bundle/entry "$(VERSION)"'

# ========== 资源下载（细粒度）==========

.PHONY: download-images
download-images: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) bash -c 'source scripts/common.sh && source scripts/lib/image.sh && echo "TODO: implement in P3"'

.PHONY: download-binaries
download-binaries: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) bash -c 'echo "TODO: implement in P3"'

.PHONY: download-packages
download-packages: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) bash -c 'echo "TODO: implement in P3"'

.PHONY: download-charts
download-charts: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) bash -c 'echo "TODO: implement in P3"'

.PHONY: download-manifests
download-manifests: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) bash -c 'echo "TODO: implement in P3"'

# ========== 校验 ==========

.PHONY: verify
verify:
	@if [ -f cache/bundle/checksums.sha256 ]; then \
		sha256sum -c cache/bundle/checksums.sha256 --quiet && echo "OK" || echo "FAIL"; \
	elif [ -f offline/checksums.sha256 ]; then \
		sha256sum -c offline/checksums.sha256 --quiet && echo "OK" || echo "FAIL"; \
	else \
		echo "checksums.sha256 not found"; \
	fi

# ========== 测试 ==========

.PHONY: test-iso
test-iso:
	@if [ ! -f $(DIST_DIR)/$(ISO_NAME).iso ]; then echo "ISO not found"; exit 1; fi
	@echo "=== 启动 QEMU 测试 $(ISO_NAME).iso ==="
	@if [ -n "$$DISPLAY" ] || [ -n "$$WAYLAND_DISPLAY" ]; then \
		qemu-system-x86_64 $$(test -w /dev/kvm && echo -enable-kvm) \
			-m 2048 -smp 2 -cdrom $(DIST_DIR)/$(ISO_NAME).iso -boot d \
			-net nic -net user; \
	else \
		echo "  模式: VNC | 连接: vncviewer localhost:5900"; \
		qemu-system-x86_64 $$(test -w /dev/kvm && echo -enable-kvm) \
			-m 2048 -smp 2 -cdrom $(DIST_DIR)/$(ISO_NAME).iso -boot d \
			-net nic -net user -vnc :0; \
	fi

.PHONY: test-iso-console
test-iso-console:
	@if [ ! -f $(DIST_DIR)/$(ISO_NAME).iso ]; then echo "ISO not found"; exit 1; fi
	@echo "=== 启动 QEMU 串口控制台测试 (Ctrl+A 然后 X 退出) ==="
	qemu-system-x86_64 $$(test -w /dev/kvm && echo -enable-kvm) \
		-m 2048 -smp 2 -cdrom $(DIST_DIR)/$(ISO_NAME).iso -boot d \
		-nographic -net nic -net user

# ========== 截图 ==========

SCREENSHOT_NAME ?=
QEMU_MONITOR_SOCK ?= /tmp/vdi-qemu-monitor.sock

.PHONY: test-iso-screenshot
test-iso-screenshot:
	@bash scripts/qemu-screenshot.sh start "$(DIST_DIR)/$(ISO_NAME).iso"

.PHONY: screenshot
screenshot:
	@bash scripts/qemu-screenshot.sh capture "$(SCREENSHOT_NAME)"

.PHONY: stop-qemu
stop-qemu:
	@bash scripts/qemu-screenshot.sh stop

# ========== 清理 ==========

.PHONY: clean
clean:
	rm -rf $(DIST_DIR)
	rm -rf cache/rootfs/ cache/bootstrap.tar
	@echo "clean done"

.PHONY: clean-rootfs
clean-rootfs:
	rm -rf cache/rootfs/ cache/bootstrap.tar
	@echo "clean-rootfs done"

.PHONY: clean-bundle
clean-bundle:
	rm -rf cache/bundle/
	@echo "clean-bundle done"

.PHONY: clean-iso
clean-iso:
	rm -rf $(DIST_DIR)
	@echo "clean-iso done"

.PHONY: distclean
distclean: clean
	rm -rf cache/
	@echo "distclean done"

# ========== 帮助 ==========

.PHONY: help
help:
	@echo "VDI 离线 ISO 构建系统（三阶段 pipeline）"
	@echo ""
	@echo "构建目标:"
	@echo "  make iso               完整构建离线 ISO"
	@echo "  make build-rootfs      阶段 1: 构建 rootfs"
	@echo "  make build-bundle      阶段 2: 下载离线资源"
	@echo "  make package-iso       阶段 3: 打包 ISO"
	@echo ""
	@echo "增量构建:"
	@echo "  make package-iso-only  仅重新打包 ISO"
	@echo "  make build-bundle-only 仅更新离线资源"
	@echo ""
	@echo "资源下载（需要互联网）:"
	@echo "  make download          下载全部离线资源"
	@echo "  make download-images   仅下载容器镜像"
	@echo "  make download-binaries 仅下载二进制工具"
	@echo "  make download-packages 仅下载系统包"
	@echo "  make download-charts   仅下载 Helm Chart"
	@echo "  make download-manifests 仅下载 K8s Manifest"
	@echo ""
	@echo "开发调试:"
	@echo "  make shell             进入构建容器交互 shell"
	@echo "  make verify            校验离线资源完整性"
	@echo "  make clean             清理构建产物 (保留 bundle)"
	@echo "  make clean-rootfs      仅清理 rootfs 缓存"
	@echo "  make clean-bundle      仅清理离线资源"
	@echo "  make distclean         清理全部（含缓存）"
	@echo ""
	@echo "ISO 测试（需要 qemu-system-x86）:"
	@echo "  make test-iso          QEMU 图形模式启动 ISO"
	@echo "  make test-iso-console  QEMU 串口控制台模式启动 ISO"
	@echo ""
	@echo "变量:"
	@echo "  VERSION=$(VERSION)     ISO 版本号"
```

- [ ] **Step 2: 提交**

```bash
git add Makefile
git commit -m "refactor(iso-builder): 重写 Makefile 为三阶段 pipeline 框架"
```

---

### Task 1.7: 更新 scripts/common.sh

**Files:**
- Modify: `iso-builder/scripts/common.sh`

**变更:** 增加 source lib/ 的便捷函数、增加阶段校验函数。

- [ ] **Step 1: 在 common.sh 末尾追加**

在现有 `sha256_file()` 函数之后追加：

```bash
# source 所有共享函数库
source_libs() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    local lib_dir="${script_dir}/lib"
    # 如果直接在 scripts/ 下执行，lib 是子目录；如果在子目录执行，lib 是兄弟目录
    if [ ! -d "$lib_dir" ] && [ -d "${script_dir}/../lib" ]; then
        lib_dir="${script_dir}/../lib"
    fi
    for lib in "${lib_dir}"/*.sh; do
        [ -f "$lib" ] && source "$lib"
    done
}

# 阶段校验：验证必需文件存在
validate_file() {
    local file="$1"
    local desc="${2:-文件}"
    if [ ! -f "$file" ]; then
        error "${desc}不存在: ${file}"
        return 1
    fi
}

# 阶段校验：验证必需目录存在
validate_dir() {
    local dir="$1"
    local desc="${2:-目录}"
    if [ ! -d "$dir" ]; then
        error "${desc}不存在: ${dir}"
        return 1
    fi
}

# 计算目录下所有文件的 sha256 并生成校验和文件
generate_checksums() {
    local base_dir="$1"
    local output="$2"
    (
        cd "$base_dir"
        find . -type f \
            ! -name 'checksums.sha256' \
            ! -name '.gitkeep' \
            ! -name 'metadata.yaml' \
            -exec sha256sum {} \;
    ) > "$output"
}
```

- [ ] **Step 2: 提交**

```bash
git add scripts/common.sh
git commit -m "feat(iso-builder): common.sh 增加函数库加载和阶段校验函数"
```

---

## P1 完成标准

- [ ] 所有新目录已创建
- [ ] `scripts/lib/image.sh`、`iso.sh`、`template.sh` 三个函数库就绪
- [ ] `Dockerfile.dapper` 包含 zstd 和 gettext-base
- [ ] `Makefile` 三阶段框架就绪，`make help` 输出正确
- [ ] `scripts/common.sh` 新增 source_libs、validate_file/dir、generate_checksums 函数
- [ ] `make shell` 可以成功进入构建容器
