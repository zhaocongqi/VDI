# VDI 构建流程

VDI 离线安装器从源码到可引导 ISO 的完整构建链路。

## 总览

构建直接在宿主机执行，`make <target>` 调用 `scripts/<target>`，前置工具自动检查。最终产物是 BIOS+UEFI 双引导的安装型 ISO。

```
make default
  ├─ scripts/build              编译 Go 版本输出 CLI
  ├─ scripts/build-bundle       下载离线镜像 + Helm chart + RKE2 二进制
  └─ scripts/package-vdi-iso    xorriso 解包 BCLinux DVD → 注入 ks/addon/bundle → 重建 ISO
```

产物：`dist/artifacts/vdi-$VERSION-$ARCH.iso`

## 一、Makefile 编排

`Makefile` 显式声明构建 target，`check-deps` 自动检查工具依赖：

```makefile
REQUIRED_TOOLS := go xorriso unsquashfs mksquashfs mtools skopeo zstd curl
build: check-deps
	./scripts/build
```

构建者需安装宿主机工具：`apt install golang xorriso squashfs-tools mtools skopeo zstd curl`

## 二、scripts 脚本职责

| 脚本 | 职责 | 产物 |
|------|------|------|
| `version` / `version-*` | 定义 VERSION + RKE2/KubeVirt/Longhorn/Kube-OVN/kagent 版本号 | shell 变量 |
| `build` | `go build` 编译版本输出 CLI，ldflags 注入版本号 | `bin/vdi-installer` |
| `build-bundle` | 下载组件镜像 tar.zst + Helm chart + RKE2 二进制 | `package/vdi-os/iso/bundle/` |
| `package-vdi-iso` | xorriso 解包 BCLinux DVD → 注入 ks.cfg + Addon + bundle → 重建 ISO | `dist/artifacts/vdi-$VERSION-$ARCH.iso` |
| `hot-reload-addon` | 开发期热重载 Anaconda Addon 到运行中的安装器 | — |
| `qemu-test-ks` | QEMU 无人值守装机验证 | — |
| `package-minimal-addon-iso` | 构建极简 Addon 验证 ISO | — |

### build

`CGO_ENABLED=0 go build`，通过 `-ldflags` 把版本号注入 `pkg/version.Version` + `pkg/version.GitCommit`。

### build-bundle

为每个组件拉取镜像 tar.zst + Helm chart + RKE2 二进制，落盘到 `package/vdi-os/iso/bundle/vdi/`：

| 组件 | 下载内容 |
|------|---------|
| RKE2 | rke2-images.linux-amd64.tar.zst + rke2-images-multus tar.zst + rke2.linux-amd64.tar.gz（二进制） |
| Longhorn | longhorn chart tgz + 镜像 tar.zst |
| KubeVirt | kubevirt-operator.yaml manifest + 镜像 tar.zst |
| Kube-OVN | kube-ovn chart tgz + 镜像 tar.zst |
| kagent | 暂不部署（chart 无 release 资产 + ghcr 需认证） |

公共函数：`scripts/lib/http`（`get_url` — 支持本地缓存 + curl 下载）、`scripts/lib/image`（`save_image` — skopeo copy + zst 压缩，无需 Docker daemon）。

Helm chart 中转目录：`cache/charts/`（下载后 copy 到 `bundle/vdi/charts/`）。

### package-vdi-iso

1. 校验 BCLinux ISO + xorriso
2. xorriso 解包 DVD ISO 到临时目录（osirrox，保留 Rock Ridge + Eltorito + EFI）
3. `chmod -R u+w` 解除 ISO 9660 只读
4. 注入 `ks.cfg` 到 ISO 根（`inst.ks=hd:LABEL=BCLinux.x86_64:/ks.cfg` 寻址）
5. 注入 Anaconda Addon（`package/vdi-os/anaconda/addons/vdi/`）到 `install.img` 内部 ext4
6. 改写 `install.img` 内 `bclinux.conf` 隐藏原生 NetworkSpoke
7. 改 `isolinux.cfg`(BIOS) + `grub.cfg`(UEFI) 加 `inst.ks` + 设默认装机项 + 缩短 timeout
8. 复制 `bundle/vdi/` 离线资源到 ISO 内 `/bundle/vdi/`
9. xorriso 重建 ISO（`-isohybrid-mbr` 保留双引导，卷标 `BCLinux.x86_64`）
10. 验证 + SHA512

## 三、版本注入

`pkg/version/version.go`：
```go
var (
    Version   = "dev"   // ldflags 注入
    GitCommit = "HEAD"  // ldflags 注入
)
```

`scripts/build` 的 LINKFLAGS 注入 `version.Version` + `version.GitCommit`。

## 四、构建产物依赖关系

```
Go 源码 ──build──→ bin/vdi-installer
                         ↓ (仅版本输出，不参与 ISO 构建)

BCLinux ISO ──package-vdi-iso──→ xorriso 解包 ──┐
                                                 ├─→ 注入 ks.cfg + Addon + bundle
离线资源 ──build-bundle──→ bundle/vdi/ ──────────┘    │
                                                       ↓
                                                xorriso 重建 ISO
                                                       │
                                                dist/artifacts/vdi-$VER-$ARCH.iso
```

## 五、构建命令速查

```bash
make default            # 完整构建（build + build-bundle + package-vdi-iso）
make build              # 仅编译 Go 版本 CLI
make build-bundle       # 仅下载离线资源
make package-vdi-iso    # 仅构建 ISO
```

验证 ISO：
```bash
# UEFI 模式（需 OVMF 固件）
./scripts/qemu-test-ks dist/artifacts/vdi-*.iso uefi

# BIOS 模式
./scripts/qemu-test-ks dist/artifacts/vdi-*.iso bios
```

## 六、已知缺口

1. kagent 组件无法部署：镜像未打包（ghcr.io 需认证）；chart 拉取 404；manifest 引用的 chart/镜像在 ISO 里缺失。启用需配 GHCR 认证 + 确认 chart 来源。
