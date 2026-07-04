PROJECT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# 构建所需工具前置检查
REQUIRED_TOOLS := go xorriso unsquashfs mksquashfs mtools skopeo zstd curl
check-deps:
	@for tool in $(REQUIRED_TOOLS); do \
		if ! command -v $$tool >/dev/null 2>&1; then \
			echo "ERROR: 缺少 $$tool"; \
			echo "  Debian/Ubuntu: apt install golang xorriso squashfs-tools mtools skopeo zstd curl"; \
			echo "  RHEL/CentOS:   yum install golang xorriso squashfs-tools mtools skopeo zstd curl"; \
			exit 1; \
		fi; \
	done

build: check-deps
	./scripts/build

build-bundle: check-deps
	./scripts/build-bundle

package-vdi-iso: check-deps
	./scripts/package-vdi-iso

shell:
	@echo "无需构建容器，直接在宿主机执行脚本即可"

default: build build-bundle package-vdi-iso

.PHONY: build build-bundle package-vdi-iso shell default check-deps
