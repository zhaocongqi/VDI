# ISO Builder 架构重构设计文档

> 日期: 2026-06-11
> 状态: 已确认
> 参考: Harvester (`harvester/harvester` + `harvester/harvester-installer`) ISO 构建架构

## 1. 背景

当前 `iso-builder` 存在以下核心问题：

1. **两套构建路径并存**：遗留的 `build-iso` (debootstrap 手工模式) 和当前的 `build-iso-lb` (live-build 混合模式) 共存，维护负担大
2. **live-build 被绕过**：`build-iso-lb` 虽然使用 `lb bootstrap` + `lb chroot`，但手动执行 hooks 并完全跳过 `lb binary` 阶段
3. **OCI 镜像导入不稳定**：`skopeo → OCI 目录格式` 的 `ctr import` 支持有限
4. **TUI 和 deploy 脚本冗余**：squashfs 内和 ISO 根目录各有一份，浪费空间
5. **bootloader 配置硬编码**：GRUB/isolinux 配置内联在构建脚本中
6. **缺乏增量构建**：每次 `make iso` 都从零开始，debootstrap 阶段耗时 10-15 分钟
7. **PXE 模板替换不可靠**：使用 `sed` 做简单字符串替换
8. **目录结构扁平**：所有脚本平铺在 `scripts/` 下，难以区分职责

## 2. 设计目标

参考 Harvester 的 `build → build-bundle → package-os` 三阶段分层架构，重构为：

- **清晰的阶段边界**：build-rootfs → build-bundle → package-iso
- **每阶段独立可调试**：可单独执行、单独缓存
- **离线资源索引化**：metadata.yaml 作为 bundle 的结构化索引
- **镜像格式可靠**：docker-archive + zstd 压缩
- **模板化配置**：bootloader 和 PXE 配置从脚本中抽离为模板文件
- **消除冗余**：清理所有遗留脚本和重复资源

## 3. 约束

- **不引入 Elemental Toolkit**：Elemental 是为 SLE Micro 设计的，Ubuntu 不原生支持
- **保持 Ubuntu 22.04 基础**：live-build 的 bootstrap + chroot 能力仍然有用
- **单仓库**：不拆分为双仓库（和 Harvester 不同），在 `scripts/` 下按阶段分子目录
- **保持 TUI 安装器不变**：TUI 代码不改动，仅改变其在 ISO 中的部署位置
- **仅 amd64**：暂不引入 arm64 支持

## 4. 目录结构

```
iso-builder/
├── Makefile                          # 入口：编排三阶段调用
├── Dockerfile.dapper                 # 构建环境（增加 zstd, yq, envsubst）
├── manifest.yaml                     # 唯一真相来源（从 offline/ 提升到顶层）
│
├── scripts/
│   ├── common.sh                     # 共享函数库 (step/ok/error/warn)
│   ├── lib/                          # 共享函数模块
│   │   ├── iso.sh                    # xorriso 封装函数
│   │   ├── image.sh                  # 镜像拉取/保存/过滤
│   │   └── template.sh              # 模板渲染函数
│   │
│   ├── build-rootfs/                 # 阶段 1: rootfs 构建
│   │   ├── entry                     # 阶段入口
│   │   ├── bootstrap.sh             # debootstrap / lb bootstrap
│   │   ├── configure.sh             # chroot hooks 执行
│   │   └── cache.sh                 # bootstrap 缓存管理
│   │
│   ├── build-bundle/                 # 阶段 2: 离线资源打包
│   │   ├── entry                     # 阶段入口
│   │   ├── images.sh                # skopeo → docker-archive + zstd
│   │   ├── binaries.sh              # 二进制下载
│   │   ├── charts.sh                # Helm chart 打包
│   │   ├── manifests.sh             # K8s YAML 下载
│   │   ├── packages.sh              # deb 包下载
│   │   └── metadata.sh              # metadata.yaml 索引生成
│   │
│   └── package-iso/                  # 阶段 3: ISO 打包
│       ├── entry                     # 阶段入口
│       ├── squashfs.sh              # mksquashfs 打包
│       ├── bootloader.sh            # isolinux + GRUB 配置生成
│       ├── iso.sh                   # xorriso 打包
│       ├── pxe.sh                   # PXE 产物生成
│       └── checksum.sh              # sha256sum + version.yaml
│
├── rootfs/                           # rootfs 配置 (原 lb-config/)
│   ├── package-lists/                # apt 包列表
│   │   ├── base.list.chroot
│   │   ├── network.list.chroot
│   │   ├── tui.list.chroot
│   │   ├── k8s.list.chroot
│   │   └── pxe.list.chroot
│   ├── hooks/                        # chroot hooks
│   │   ├── 0100-system-setup.chroot
│   │   ├── 0200-services-setup.chroot
│   │   └── 0300-tui-welcome.chroot
│   └── includes.chroot/              # 额外文件
│
├── iso/                              # ISO 结构配置模板
│   ├── boot/
│   │   └── grub/
│   │       └── grub.cfg             # GRUB 配置模板
│   └── isolinux/
│       └── isolinux.cfg             # isolinux 配置模板
│
├── pxe/                              # PXE 配置模板
│   ├── start-pxe.sh
│   ├── dnsmasq.conf.template
│   ├── preseed.cfg.template
│   └── worker-setup.sh.template
│
├── tui/                              # TUI 安装器 (不变)
├── configs/                          # 部署配置模板 (不变)
└── cache/                            # 构建缓存 (gitignore)
    ├── bootstrap.tar                 # debootstrap 产物
    ├── rootfs/                       # 完整 chroot
    └── bundle/                       # 离线资源
```

## 5. 三阶段 Pipeline

### 5.1 阶段 1: build-rootfs

**职责**：构建可启动的 Ubuntu Live rootfs。

```
输入: rootfs/package-lists/, rootfs/hooks/, rootfs/includes.chroot/
输出: cache/rootfs/ (完整 chroot 目录树)
缓存: cache/bootstrap.tar (可跨构建复用)
```

**流程**：

1. 检查 `cache/bootstrap.tar` 是否存在
   - 存在 → 解压到 `cache/rootfs/`
   - 不存在 → `lb bootstrap`（使用阿里云镜像源）
2. 执行 `lb chroot` 安装包列表中的所有软件包
3. 复制 `rootfs/hooks/` 到 `cache/rootfs/` 并 chroot 执行
4. 复制 `rootfs/includes.chroot/` 到 `cache/rootfs/`
5. 创建 symlink: `/opt/vdi/tui → /cdrom/tui`（TUI 不再复制到 squashfs 内）
6. 创建 symlink: `/opt/vdi/deploy → /cdrom/scripts/deploy`

**缓存策略**：
- `SKIP_BOOTSTRAP=1` 跳过 bootstrap，直接使用缓存
- `make clean-rootfs` 清除 rootfs 缓存
- `make clean` 清除所有缓存

**阶段校验**：验证 `cache/rootfs/bin/bash` 和 `cache/rootfs/boot/vmlinuz-*` 存在

### 5.2 阶段 2: build-bundle

**职责**：下载并打包所有离线资源，生成结构化索引。

```
输入: manifest.yaml (顶层唯一真相来源)
输出: cache/bundle/
```

**bundle 目录结构**：

```
cache/bundle/
├── metadata.yaml                     # 结构化索引
├── checksums.sha256                  # 完整性校验
├── images/
│   ├── kubernetes/
│   │   └── kube-apiserver_v1.34.3.tar.zst
│   ├── kube-ovn/
│   │   └── kube-ovn_v1.12.0.tar.zst
│   ├── longhorn/
│   │   └── longhorn-manager_v1.7.2.tar.zst
│   ├── kubevirt/
│   ├── cdi/
│   └── kagent/
├── binaries/
│   ├── kk
│   ├── kubectl
│   ├── helm
│   └── virtctl
├── charts/
│   ├── kube-ovn-*.tgz
│   ├── longhorn-*.tgz
│   └── kagent-*.tgz
├── k8s-manifests/
│   ├── kubevirt-operator.yaml
│   ├── kubevirt-cr.yaml
│   ├── cdi-operator.yaml
│   └── cdi-cr.yaml
└── packages/
    └── deb/
        ├── *.deb
        └── Packages.gz
```

**metadata.yaml 格式**：

```yaml
version: v1.0.0
created: "2026-06-11T12:00:00Z"
platform: amd64
images:
  - name: registry.k8s.io/kube-apiserver
    tag: v1.34.3
    file: images/kubernetes/kube-apiserver_v1.34.3.tar.zst
    digest: sha256:abc123...
  # ... 所有镜像
binaries:
  - name: kk
    version: v4.0.0
    file: binaries/kk
    digest: sha256:789...
  # ... 所有二进制
charts:
  - name: kube-ovn
    version: 1.12.0
    file: charts/kube-ovn-1.12.0.tgz
    digest: sha256:def...
  # ... 所有 chart
```

**镜像下载流程**：

```bash
skopeo copy --override-os linux --override-arch amd64 \
  docker://registry.k8s.io/kube-apiserver:v1.34.3 \
  docker-archive:${BUNDLE_DIR}/images/kubernetes/kube-apiserver_v1.34.3.tar

zstd -19 "${BUNDLE_DIR}/images/kubernetes/kube-apiserver_v1.34.3.tar" \
  -o "${BUNDLE_DIR}/images/kubernetes/kube-apiserver_v1.34.3.tar.zst"

rm "${BUNDLE_DIR}/images/kubernetes/kube-apiserver_v1.34.3.tar"
```

**阶段校验**：验证 `cache/bundle/metadata.yaml` 存在且 `sha256sum -c checksums.sha256` 通过

### 5.3 阶段 3: package-iso

**职责**：将 rootfs 和 bundle 组装为最终 ISO + PXE 产物。

```
输入: cache/rootfs/ + cache/bundle/
输出: dist/
```

**输出结构**：

```
dist/
├── vdi-v1.0.0-amd64.iso              # 最终 ISO
├── vdi-v1.0.0-amd64.iso.sha256       # 校验和
├── version.yaml                       # 构建元数据
└── pxe/                               # PXE 启动产物
    ├── vmlinuz
    ├── initrd
    └── rootfs.squashfs
```

**ISO 内部目录**：

```
ISO_ROOT/
├── boot/grub/grub.cfg
├── efi/boot/efiboot.img
├── isolinux/{isolinux.bin, isolinux.cfg, *.c32}
├── casper/{vmlinuz, initrd, filesystem.squashfs}
├── bundle/                            # 离线资源（目录名从 offline/ 改为 bundle/）
│   ├── metadata.yaml
│   ├── checksums.sha256
│   ├── images/
│   ├── binaries/
│   ├── charts/
│   ├── k8s-manifests/
│   └── packages/
├── scripts/{deploy/, load-offline-images, setup-local-repo, verify-offline-pack}
├── configs/
├── tui/                               # TUI 仅此一份
└── .disk/info
```

**xorriso 打包参数**（参考 Harvester 的 `pack_iso` 函数）：

```bash
xorriso -volid "VDI-INSTALL" \
  -joliet on -padding 0 \
  -outdev "dist/vdi-v1.0.0-amd64.iso" \
  -map "dist/iso/" / -chmod 0755 -- \
  -append_partition 2 0xef "dist/iso/efi/boot/efiboot.img" \
  -boot_image any cat_path="boot/boot.catalog" \
  -boot_image any cat_hidden=on \
  -boot_image any efi_path=--interval:appended_partition_2:all:: \
  -boot_image any platform_id=0xef \
  -boot_image any appended_part_as=gpt \
  -boot_image any partition_offset=16
```

**阶段校验**：验证 ISO 文件存在且大小 > 100MB

## 6. Makefile 设计

```makefile
VERSION ?= v1.0.0

# 主入口
iso: package-iso

# 阶段 1
build-rootfs:
	./scripts/build-rootfs/entry $(VERSION)

# 阶段 2
build-bundle:
	./scripts/build-bundle/entry $(VERSION)

download: build-bundle

# 阶段 3（依赖前两阶段）
package-iso: build-rootfs build-bundle
	./scripts/package-iso/entry $(VERSION)

# 增量构建
package-iso-only:
	./scripts/package-iso/entry $(VERSION)

build-bundle-only:
	./scripts/build-bundle/entry $(VERSION)

# 清理
clean: clean-rootfs clean-bundle clean-iso
	rm -rf dist/

clean-rootfs:
	rm -rf cache/rootfs/ cache/bootstrap.tar

clean-bundle:
	rm -rf cache/bundle/

clean-iso:
	rm -rf dist/

# 校验
verify:
	sha256sum -c cache/bundle/checksums.sha256

# 调试
shell:
	docker run --rm -it -v $(PWD):/src vdi-iso-builder bash
```

## 7. Bootloader 模板化

GRUB 和 isolinux 配置从构建脚本中抽离为独立模板文件，存放在 `iso/` 目录。

**模板渲染**：`package-iso/bootloader.sh` 仅用 `sed` 注入 `${vdi_version}` 版本号。

**GRUB 模板** (`iso/boot/grub/grub.cfg`)：
- 3 个启动项：Install VDI Cluster、VDI Live Shell、Safe Mode
- 串口控制台：`serial --unit=0 --speed=115200`
- 统一内核参数：`boot=live live-media-path=/casper`

**isolinux 模板** (`iso/isolinux/isolinux.cfg`)：
- 相同 3 个启动项
- 统一内核参数

## 8. 路径兼容性

ISO 内离线资源目录从 `offline/` 重命名为 `bundle/`，需同步更新以下引用：

- `load-offline-images` 脚本：`OFFLINE_BASE` 从 `/cdrom/offline` 改为 `/cdrom/bundle`
- `setup-local-repo` 脚本：deb 包路径更新
- `verify-offline-pack` 脚本：校验路径更新
- TUI `utils/offline.py` 的 `OfflineManager`：检测路径从 `/cdrom/offline` 改为 `/cdrom/bundle`
- `rootfs/hooks/0300-tui-welcome.chroot` 中的 `vdi-offline.sh`：`OFFLINE_BASE` 默认值更新
- PXE `start-pxe.sh` 中的路径引用

## 9. 镜像导入改进

**下载阶段**（build-bundle/images.sh）：
- `skopeo copy docker:// → docker-archive:file.tar`（无需 Docker daemon）
- `zstd -19 file.tar → file.tar.zst`
- 删除中间 tar 文件
- 记录到 `metadata.yaml`

**导入阶段**（load-offline-images）：
- 从 `metadata.yaml` 读取镜像列表
- `zstd -d file.tar.zst -o /tmp/file.tar`
- `ctr -n k8s.io images import /tmp/file.tar`
- 按 metadata 索引逐条导入，失败即中断

## 10. PXE 改进

- **模板引擎**：`preseed.cfg.template` 和 `worker-setup.sh.template` 使用 `envsubst` 替代 `sed`
- **产物规范化**：构建输出 `dist/pxe/` 目录，包含 vmlinuz + initrd + rootfs.squashfs
- **start-pxe.sh**：从 `dist/pxe/` 复制到 TFTP/HTTP 目录

## 11. 遗留代码清理

以下文件/目录将被删除：

| 文件/目录 | 原因 |
|-----------|------|
| `scripts/build-iso` | 遗留构建脚本 |
| `scripts/build-iso-lb` | 合并到三阶段 scripts |
| `scripts/create-live` | 遗留 debootstrap 脚本 |
| `scripts/generate-iso` | 遗留 xorriso 脚本 |
| `scripts/integrate-offline` | 遗留离线整合脚本 |
| `scripts/integrate-tui` | 遗留 TUI 整合脚本 |
| `scripts/download-resources` | 合并到 `build-bundle/entry` |
| `scripts/download-images` | 合并到 `build-bundle/images.sh` |
| `scripts/download-binaries` | 合并到 `build-bundle/binaries.sh` |
| `scripts/download-charts` | 合并到 `build-bundle/charts.sh` |
| `scripts/download-manifests` | 合并到 `build-bundle/manifests.sh` |
| `scripts/download-packages` | 合并到 `build-bundle/packages.sh` |
| `lb-config/` | 迁移到 `rootfs/` |
| `offline/` | 迁移到 `cache/bundle/`（manifest.yaml 提升到顶层） |

## 12. Dockerfile.dapper 更新

新增工具：
- `zstd` — 镜像压缩
- `yq` — YAML 处理（metadata.yaml 读写）
- `envsubst`（`gettext-base` 包）— 模板渲染

## 13. 错误处理

- 所有脚本使用 `set -euo pipefail`
- 每阶段完成后执行校验步骤
- 构建日志输出到 `cache/build-<stage>.log`
- `common.sh` 提供 `step()`/`ok()`/`error()`/`warn()` 彩色输出

## 14. 不在范围内

以下内容**不包含**在本次重构中：
- TUI 安装器代码修改
- arm64 多架构支持
- CI/CD pipeline 建立
- UEFI Secure Boot 支持
- APT 包版本锁定
