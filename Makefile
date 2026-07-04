PROJECT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# 构建所需工具前置检查
REQUIRED_TOOLS := xorriso unsquashfs mksquashfs mtools skopeo zstd curl
check-deps:
	@for tool in $(REQUIRED_TOOLS); do \
		if ! command -v $$tool >/dev/null 2>&1; then \
			echo "ERROR: 缺少 $$tool"; \
			echo "  Debian/Ubuntu: apt install xorriso squashfs-tools mtools skopeo zstd curl"; \
			echo "  RHEL/CentOS:   yum install xorriso squashfs-tools mtools skopeo zstd curl"; \
			exit 1; \
		fi; \
	done

build-bundle: check-deps
	./scripts/build-bundle

package-vdi-iso: check-deps
	./scripts/package-vdi-iso

default: build-bundle package-vdi-iso

.PHONY: build-bundle package-vdi-iso default check-deps
