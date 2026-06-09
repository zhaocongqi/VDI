# VDI 离线 ISO 构建系统
# 使用 Dapper 在容器中构建，确保可重复性

# 版本信息
VERSION ?= v1.0.0
ISO_NAME ?= vdi-offline-$(VERSION)
DIST_DIR ?= dist

# 构建镜像名称
BUILDER_IMAGE ?= vdi-iso-builder

# Docker 网络模式（解决桥接网络 DNS 问题）
DOCKER_NET ?= --network host

# 默认目标：完整构建
.PHONY: all
all: iso

# ========== 构建环境 ==========

# 构建 Dapper 构建环境镜像
.PHONY: build-builder
build-builder:
	docker build $(DOCKER_NET) -f Dockerfile.dapper -t $(BUILDER_IMAGE) .

# 进入构建容器（调试用）
.PHONY: shell
shell: build-builder
	docker run --rm -it \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		-v /var/run/docker.sock:/var/run/docker.sock \
		--privileged \
		$(BUILDER_IMAGE) \
		bash

# ========== 资源下载 ==========

# 下载全部离线资源（需要互联网）
.PHONY: download
download: build-builder
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		$(BUILDER_IMAGE) \
		bash -c './scripts/download-resources'

# 仅下载容器镜像
.PHONY: download-images
download-images: build-builder
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		$(BUILDER_IMAGE) \
		bash -c './scripts/download-images'

# 仅下载二进制工具
.PHONY: download-binaries
download-binaries: build-builder
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		$(BUILDER_IMAGE) \
		bash -c './scripts/download-binaries'

# 仅下载系统包
.PHONY: download-packages
download-packages: build-builder
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		$(BUILDER_IMAGE) \
		bash -c './scripts/download-packages'

# 下载 Helm Chart
.PHONY: download-charts
download-charts: build-builder
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		$(BUILDER_IMAGE) \
		bash -c './scripts/download-charts'

# 下载 K8s Manifest
.PHONY: download-manifests
download-manifests: build-builder
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		$(BUILDER_IMAGE) \
		bash -c './scripts/download-manifests'

# ========== ISO 构建 ==========

# 完整 ISO 构建（下载资源 + 创建 Live 系统 + 集成离线资源 + 打包）
.PHONY: iso
iso: build-builder
	@echo "=== 开始构建 VDI 离线 ISO $(VERSION) ==="
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		--privileged \
		--cap-add SYS_ADMIN \
		$(BUILDER_IMAGE) \
		bash -c './scripts/build-iso "$(VERSION)"'
	@echo "=== 构建完成: $(DIST_DIR)/$(ISO_NAME).iso ==="

# 仅创建 Live 系统基础 ISO（不含离线资源）
.PHONY: live-only
live-only: build-builder
	docker run --rm \
		$(DOCKER_NET) \
		-v $(shell pwd):/workspace \
		--privileged \
		--cap-add SYS_ADMIN \
		$(BUILDER_IMAGE) \
		bash -c './scripts/create-live'

# ========== 校验 ==========

# 校验离线资源完整性
.PHONY: verify
verify:
	@if [ -f offline/checksums.sha256 ]; then \
		sha256sum -c offline/checksums.sha256 --quiet && echo "✓ 校验通过" || echo "✗ 校验失败"; \
	else \
		echo "checksums.sha256 不存在，请先执行 make download"; \
	fi

# ========== 测试 ==========

# 使用 QEMU 本地启动 ISO 测试（自动检测图形/VNC 模式）
.PHONY: test-iso
test-iso:
	@if [ ! -f $(DIST_DIR)/$(ISO_NAME).iso ]; then \
		echo "✗ ISO 不存在，请先执行 make iso"; \
		exit 1; \
	fi
	@echo "=== 启动 QEMU 测试 $(ISO_NAME).iso ==="
	@if [ -n "$$DISPLAY" ] || [ -n "$$WAYLAND_DISPLAY" ]; then \
		echo "  模式: 图形窗口 | 内存: 2GB | CPU: 2核"; \
		echo "  关闭: 直接关闭 QEMU 窗口"; \
		echo ""; \
		qemu-system-x86_64 \
			$$(test -w /dev/kvm && echo -enable-kvm) \
			-m 2048 -smp 2 \
			-cdrom $(DIST_DIR)/$(ISO_NAME).iso -boot d \
			-net nic -net user; \
	else \
		echo "  模式: VNC | 内存: 2GB | CPU: 2核"; \
		echo "  连接: vncviewer localhost:5900"; \
		echo "  关闭: Ctrl+C 停止 QEMU"; \
		echo ""; \
		qemu-system-x86_64 \
			$$(test -w /dev/kvm && echo -enable-kvm) \
			-m 2048 -smp 2 \
			-cdrom $(DIST_DIR)/$(ISO_NAME).iso -boot d \
			-net nic -net user \
			-vnc :0; \
	fi

# 使用 QEMU 启动 ISO 测试（串口控制台模式，无需图形界面）
.PHONY: test-iso-console
test-iso-console:
	@if [ ! -f $(DIST_DIR)/$(ISO_NAME).iso ]; then \
		echo "✗ ISO 不存在，请先执行 make iso"; \
		exit 1; \
	fi
	@echo "=== 启动 QEMU 串口控制台测试 ==="
	@echo "  退出: Ctrl+A 然后 X"
	@echo ""
	qemu-system-x86_64 \
		$$(test -w /dev/kvm && echo -enable-kvm) \
		-m 2048 \
		-smp 2 \
		-cdrom $(DIST_DIR)/$(ISO_NAME).iso \
		-boot d \
		-nographic \
		-net nic -net user

# ========== 清理 ==========

# 清理构建产物
.PHONY: clean
clean:
	rm -rf $(DIST_DIR)
	rm -rf rootfs iso_root tmp
	@echo "✓ 清理完成"

# 清理全部（包括下载的离线资源）
.PHONY: distclean
distclean: clean
	rm -rf offline/images/**/*.tar offline/images/**/*.oci
	rm -rf offline/binaries/*
	rm -rf offline/packages/deb/*.deb
	rm -rf offline/packages/repo
	rm -rf offline/checksums.sha256
	rm -rf offline/charts/longhorn/*.tgz
	rm -rf offline/charts/kagent/*.tgz
	rm -rf offline/k8s-manifests/*.yaml
	@echo "✓ 全量清理完成"

# ========== 帮助 ==========

.PHONY: help
help:
	@echo "VDI 离线 ISO 构建系统"
	@echo ""
	@echo "构建目标:"
	@echo "  make iso               完整构建离线 ISO（下载 + 打包）"
	@echo "  make live-only         仅创建 Live 系统基础 ISO"
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
	@echo "  make clean             清理构建产物"
	@echo "  make distclean         清理全部（含下载资源）"
	@echo ""
	@echo "ISO 测试（需要 qemu-system-x86）:"
	@echo "  make test-iso          QEMU 图形模式启动 ISO"
	@echo "  make test-iso-console  QEMU 串口控制台模式启动 ISO"
	@echo ""
	@echo "变量:"
	@echo "  VERSION=$(VERSION)     ISO 版本号"
