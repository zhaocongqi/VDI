# VDI 构建环境前置条件

从零构建 VDI 安装型 ISO 的前置条件清单。满足后 `make default` 一条命令跑通。

## 一、必须提供

### BCLinux ISO（客户提供，无法自动下载）

放至：
```
dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso
```

`package-vdi-iso` 脚本从中解包 anaconda 安装树，注入 kickstart + Addon + 离线资源后 xorriso 重建 ISO。全程离线，不联网。

### 宿主机工具

- **docker**：构建容器运行环境。首次 `make` 自动构建 `vdi-builder` 镜像，后续复用。

其余工具（helm、yq、xorriso、skopeo、Go 模块）由 `Dockerfile` 容器内安装/下载，宿主机无需预装。

## 二、网络访问要求

构建需访问以下站点（网络受限环境需配代理或 registry mirror）：

| 站点 | 用途 |
|------|------|
| `docker.io` | `golang:1.26-bookworm`（构建容器基础镜像）、组件镜像（build-bundle `skopeo copy`） |
| `proxy.golang.org` | Go 模块下载（无 vendor 目录，`go build` 联网拉取） |
| `github.com` / `raw.githubusercontent.com` | RKE2 二进制/镜像列表、KubeVirt operator manifest |
| `charts.longhorn.io` | Longhorn Helm chart（build-bundle `helm pull`） |

## 三、资源要求

| 资源 | 要求 | 原因 |
|------|------|------|
| 内存 | ≥4G | kickstart 装机无 squashfs/active.img，4G 足够 |
| 磁盘 | ≥30G | Docker 层 + BCLinux ISO 输入 + 离线镜像 + ISO 产物临时空间 |

## 四、本地包缓存

`make build-bundle` 支持环境变量 `LOCAL_PKG_DIR`（如 `export LOCAL_PKG_DIR=/opt/vdi-pkgs`）指定本地离线包检索路径。优先本地拷贝，未命中则无代理 `curl` 下载。未设置时默认检索 `cache/downloads`。

## 五、一条命令构建

前置条件就绪后：

```bash
make default    # build → build-bundle → package-vdi-iso
```

产物：`dist/artifacts/vdi-$VERSION-amd64.iso`（BIOS+UEFI 双引导）。

也可分步：
```bash
make build              # 编译 Go 版本 CLI
make build-bundle       # 下载离线镜像 + Helm chart
make package-vdi-iso    # 构建 VDI 安装型 ISO（BCLinux DVD + kickstart + xorriso）
```

## 六、常见问题

- **docker.io TLS handshake timeout**：网络受限，配 registry mirror 或 skopeo 代理。
- **产物文件属主为 root**：容器默认 root 运行，volume mount 写入的文件属 root。不影响构建，清理时需 `sudo rm`。
- **QEMU 端到端验证**：`./scripts/qemu-test-ks dist/artifacts/vdi-*.iso [uefi|bios]`。KVM 需 `/dev/kvm` 权限。
