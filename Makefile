PROJECT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
IMAGE ?= vdi-builder

DOCKER_RUN = docker run --rm \
    -v $(PROJECT_DIR):/work \
    -e LOCAL_PKG_DIR=$(LOCAL_PKG_DIR) \
    -w /work \
    $(IMAGE)

DOCKER_RUN_PRIV = docker run --rm \
    --privileged \
    -v $(PROJECT_DIR):/work \
    -e LOCAL_PKG_DIR=$(LOCAL_PKG_DIR) \
    -w /work \
    $(IMAGE)

$(IMAGE):
	docker build -t $(IMAGE) -f Dockerfile --build-arg DAPPER_HOST_ARCH=$(shell uname -m) .

build: $(IMAGE)
	$(DOCKER_RUN) ./scripts/build

build-bundle: $(IMAGE)
	$(DOCKER_RUN) ./scripts/build-bundle

package-vdi-iso: $(IMAGE)
	$(DOCKER_RUN_PRIV) ./scripts/package-vdi-iso

shell: $(IMAGE)
	docker run --rm -it -v $(PROJECT_DIR):/work -w /work $(IMAGE) bash

default: $(IMAGE)
	$(DOCKER_RUN_PRIV) bash -c "./scripts/build && ./scripts/build-bundle && ./scripts/package-vdi-iso"

.PHONY: build build-bundle package-vdi-iso shell default $(IMAGE)
