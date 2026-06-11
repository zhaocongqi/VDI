# VDI 离线 ISO 构建系统
# 三阶段 pipeline: build-rootfs → build-bundle → package-iso
# 参考 Harvester 的分层构建架构

# 版本信息
VERSION ?= v1.0.0
ISO_NAME ?= vdi-offline-$(VERSION)
DIST_DIR ?= dist

# 构建镜像名称
BUILDER_IMAGE ?= vdi-iso-builder

# Docker 网络模式
DOCKER_NET ?= --network host

# 通用 Docker 运行参数
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

.PHONY: iso
iso: build-builder
	@echo "=== 开始构建 VDI 离线 ISO $(VERSION) ==="
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-rootfs/entry "$(VERSION)" && \
		          ./scripts/build-bundle/entry "$(VERSION)" && \
		          ./scripts/package-iso/entry "$(VERSION)"'
	@echo "=== 构建完成: $(DIST_DIR)/$(ISO_NAME).iso ==="

.PHONY: build-rootfs
build-rootfs: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-rootfs/entry "$(VERSION)"'

.PHONY: build-bundle
build-bundle: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-bundle/entry "$(VERSION)"'

.PHONY: download
download: build-bundle

.PHONY: package-iso
package-iso: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/package-iso/entry "$(VERSION)"'

# ========== 增量构建 ==========

.PHONY: package-iso-only
package-iso-only: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/package-iso/entry "$(VERSION)"'

.PHONY: build-bundle-only
build-bundle-only: build-builder
	$(DOCKER_RUN) $(BUILDER_IMAGE) \
		bash -c './scripts/build-bundle/entry "$(VERSION)"'

# ========== 资源下载（细粒度，占位）==========

.PHONY: download-images download-binaries download-packages download-charts download-manifests
download-images download-binaries download-packages download-charts download-manifests: build-builder
	@echo "请使用 make build-bundle 下载全部资源"

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
	@echo "=== QEMU 串口控制台 (Ctrl+A X 退出) ==="
	qemu-system-x86_64 $$(test -w /dev/kvm && echo -enable-kvm) \
		-m 2048 -smp 2 -cdrom $(DIST_DIR)/$(ISO_NAME).iso -boot d \
		-nographic -net nic -net user

# ========== 截图 ==========

SCREENSHOT_NAME ?=

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
	@echo "开发调试:"
	@echo "  make shell             进入构建容器交互 shell"
	@echo "  make verify            校验离线资源完整性"
	@echo "  make clean             清理构建产物 (保留 bundle)"
	@echo "  make clean-rootfs      仅清理 rootfs 缓存"
	@echo "  make clean-bundle      仅清理离线资源"
	@echo "  make distclean         清理全部（含缓存）"
	@echo ""
	@echo "ISO 测试:"
	@echo "  make test-iso          QEMU 图形模式"
	@echo "  make test-iso-console  QEMU 串口控制台模式"
	@echo ""
	@echo "变量:"
	@echo "  VERSION=$(VERSION)     ISO 版本号"
