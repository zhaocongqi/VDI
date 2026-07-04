# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

本仓库是 VDI (Virtual Desktop Infrastructure) 离线安装器，使用 RKE2 + HelmChart CRD 声明式部署 KubeVirt/Longhorn/Kube-OVN/kagent 组件栈。安装交互由 Anaconda Addon (Python + Gtk3 + D-Bus) 驱动，ISO 通过 BCLinux DVD + kickstart + xorriso 构建。

**技术栈**：
- **语言**：Go 1.26（版本 CLI）+ Python 3（Anaconda Addon）
- **K8s 运行时**：RKE2
- **addon 管理**：HelmChart CRD (helm.cattle.io/v1)
- **ISO 构建**：kickstart + xorriso（复用 BCLinux DVD anaconda stage2）
- **基础 OS**：BCLinux 21.10 U5
- **安装 GUI**：基于 Anaconda Addon 规范的多 Spoke 图形扩展（Python + Gtk3 + D-Bus）

## 目录结构

```
VDI/
├── main.go              # Go 版本输出 CLI（ldflags 注入 Version + GitCommit）
├── Makefile             # 构建系统（docker run 驱动，宿主机仅需 docker）
├── Dockerfile           # 构建容器（Go + helm + yq + xorriso + skopeo）
├── go.mod / go.sum      # Go module (vdi-installer，无外部依赖)
├── pkg/
│   └── version/         # FriendlyVersion（ldflags 注入）
├── scripts/             # 构建脚本
│   ├── version          # VERSION=git-commit[-dirty]
│   ├── version-*        # 组件版本（RKE2/KubeVirt/Longhorn/Kube-OVN/kagent）
│   ├── build            # 编译 Go 版本 CLI（ldflags 注入）
│   ├── build-bundle     # 下载离线资源（RKE2 二进制/镜像/charts）
│   ├── package-vdi-iso  # xorriso 重建 BCLinux DVD ISO（注入 ks + addon + bundle）
│   ├── default          # build + build-bundle + package-vdi-iso 全链路
│   ├── hot-reload-addon # 开发期热重载 Anaconda Addon 到运行中的安装器
│   ├── qemu-test-ks     # qemu 无人值守装机验证
│   ├── package-minimal-addon-iso  # 极简 Addon 验证 ISO
│   └── lib/             # 脚本公共库（http 下载/镜像处理）
├── package/
│   └── vdi-os/
│       ├── ks/ks.cfg                    # 静态 kickstart 模板（装机入口）
│       ├── iso/bundle/                  # 离线资源（binaries/images/charts/manifests，.gitignore 忽略）
│       └── anaconda/addons/vdi/         # Anaconda Addon Python 插件
│           ├── __init__.py              # VdiAddon（execute 生命周期：全量写盘持久化）
│           ├── constants.py             # D-Bus 常量
│           ├── gui/spokes/vdi_network.py # VdiNetworkSpoke + WindowWrapper
│           ├── gui/spokes/vdi_network.glade
│           ├── service/vdi.py           # VdiService（D-Bus 服务，管理配置状态）
│           ├── service/vdi_interface.py # D-Bus 接口声明
│           ├── service/kickstart.py     # VdiKickstartData + VdiKickstartSpecification
│           └── dbus/                    # D-Bus .service/.conf 文件
└── docs/                # 设计文档 + 实施计划
```

## 构建命令

```bash
make build              # 编译 Go 版本 CLI
make build-bundle       # 下载离线资源（RKE2 二进制/镜像/charts）
make package-vdi-iso    # 构建 VDI 安装型 ISO（BCLinux DVD + kickstart + xorriso）
make shell              # 进入构建容器调试
make default            # build + build-bundle + package-vdi-iso 全链路
```

### 构建容器

构建在 Docker 容器内执行（`docker run --rm`），构建者**只需宿主机装 docker**：
- **Dockerfile** 定义构建环境（Go + helm + yq + xorriso + skopeo + squashfs-tools）
- **volume mount**：项目目录挂载到容器 `/work`，产物直写宿主机
- **skopeo**：替代 docker pull/save 下载组件镜像，无需 Docker daemon
- **Go 模块**：容器内 `go build` 自动下载（需网络）

#### 外部输入

- **BCLinux ISO**（客户提供）：放至 `dist/iso/BCLinux-21.10U5-dvd-x86_64-260610.iso`（`.gitignore` 忽略）

#### 本地包缓存

`make build-bundle` 支持环境变量 `LOCAL_PKG_DIR`（如 `export LOCAL_PKG_DIR=/opt/vdi-pkgs`）指定本地离线包检索路径。优先本地拷贝，未命中则无代理 `curl` 下载。未设置时默认检索 `cache/downloads`。

## 安装流程（Addon 驱动链路）

1. **ISO 引导** — BCLinux DVD ISO 引导，`inst.ks=hd:LABEL=BCLinux.x86_64:/ks.cfg` 加载静态 ks 模板
2. **anaconda 图形化安装** — ks.cfg 触发 `graphical` 模式，Anaconda 加载 VDI Addon：
   - `VdiNetworkSpoke` 在安装器 Hub 的 SYSTEM 分类下提供网卡/Bond/IP/VIP 配置 GUI
   - `VdiService` 通过 D-Bus 私有总线管理配置状态
   - `VdiKickstartData` 解析/回写 `%addon vdi` 段
3. **`execute` 阶段全量写盘**（`__init__.py` → `VdiAddon.execute`）— Anaconda 在写入目标系统配置的最后阶段自动调用，依次完成：
   - 从 D-Bus 代理读取网络配置 → 写 NetworkManager `.nmconnection` 文件
   - shadow 密码覆写 + SSH root 登录配置
   - 数据盘自动探测/格式化/fstab 挂载（`mkfs.ext4 -L VDI_LH_DEFAULT`）
   - 从 ISO `/run/install/repo/bundle/vdi` 复制离线镜像/charts/manifests 到 `$sysroot`
   - 解压 RKE2 二进制到 `$sysroot/usr/local`
   - 写 `config.yaml`（server/agent 按角色）
   - 创建 systemd wants 链接（sshd/iscsid/rke2-server 或 rke2-agent）
4. **首次启动** — RKE2 server/agent 启动，首启自动导入 `agent/images/*.tar.zst`，HelmChart 控制器 apply `server/manifests/` 部署组件

## Anaconda Addon 架构

VDI Addon 遵循 Anaconda Addon 规范（参考 `com_redhat_kdump`），三层分离：

| 层 | 文件 | 职责 |
|---|---|---|
| **GUI Spoke** | `gui/spokes/vdi_network.py` | Gtk3 图形界面，`VdiNetworkSpoke` 继承 `NormalSpoke`，通过 `.glade` 布局 |
| **D-Bus Service** | `service/vdi.py` + `service/vdi_interface.py` | 配置状态管理 + D-Bus 属性/信号发布 |
| **Kickstart Data** | `service/kickstart.py` | `%addon vdi` 段的解析与序列化 |
| **执行入口** | `__init__.py` | `VdiAddon.execute()` — anaconda 生命周期钩子，全量写盘 |

**D-Bus 通信**：Spoke GUI → D-Bus 属性读写 → Service 状态 → execute 读取 D-Bus 代理写入目标盘。所有组件间通过 `org.fedoraproject.Anaconda.Addons.Vdi` 私有总线通信。

### Anaconda 33+ Addon 兼容性与 GtkBox 限制（致命红线）

系统在 SummaryHub 渲染和 Spoke 进入阶段，会强制调用 `spoke.window.set_beta`、`set_property("distribution")` 并绑定 `help-button-clicked` 信号。若使用常规 `GtkBox` 作 Spoke 顶层窗口会触发 C 语言层和 GTK 底层崩溃。**必须通过继承 `Gtk.Box` 的 `WindowWrapper` 并在 Python 层对属性和信号进行静默代理**（通过 `GUIObject.window.fget(self)` 显式读取父类懒加载 Widget 并 pack_start 作为子树）。

### `install.img` 嵌套 ext4 注入与原生界面隐藏

BCLinux 的 `install.img` 包含嵌套 ext4 分区，必须通过 loop 挂载 `LiveOS/rootfs.img` 内部，才能成功注入插件和 D-Bus 配置。同时，必须通过改写 `etc/anaconda/profile.d/bclinux.conf` 在 `[User Interface]` 段下追加 `hidden_spokes = NetworkSpoke` 来屏蔽原生"网络与主机名"配置项，防止与 VDI 插件冲突。

## 安装型 ISO 构建红线（kickstart + xorriso）

构建链 `scripts/package-vdi-iso`：xorriso 解包 BCLinux DVD → 注入 `ks.cfg` + Addon + `bundle/` → 改 `isolinux.cfg`/`grub.cfg` 加 `inst.ks=hd:LABEL=BCLinux.x86_64:/ks.cfg` → xorriso 重建（`-isohybrid-mbr` 保留 BIOS+UEFI 双引导，卷标必须 `BCLinux.x86_64`）。

- **ISO 9660 文件 0444 只读**：xorriso 解包后 `chmod -R u+w`，改写 `isolinux.cfg`/`grub.cfg` 前再 `chmod u+w`，否则写失败。
- **BCLinux anaconda 36 兼容性**：`install`/`autostep` 指令已移除（报错）→ 删除；`%packages` 缺包即失败 → 只列仓库内有的包；`rootpw --iscrypted` 偶发不生效 → Addon execute 兜底。
- **`%pre` → `%include` 时序（极度重要）**：
  1. **`%include` 必须在 ks 最顶部（%pre 之前）**。ks-include 含全局指令，落到 %pre 之后违反 kickstart "全局指令必须在所有 section 之前"语法，导致 anaconda 解析异常，且 `%post` 全段不执行。
  2. **BCLinux anaconda 36 的 `%post` 不 chroot**。kickstart 标准 `%post`（不带 --nochroot）本应 chroot 到 /mnt/sysroot，但实测**不 chroot**。Python 侧 `execute` 通过 `storage.config.sysroot` 获取目标根路径。
  3. **多 %post section 不稳定**：BCLinux anaconda 36 对多个 `%post --nochroot` section 执行不稳定。Python 侧 `execute` 天然在单次调用中完成。
- **RKE2 离线**：`rke2.linux-amd64.tar.gz` 解压 `$SYSROOT/usr/local`（二进制内嵌 containerd）；镜像 `*.tar.zst` 放 `agent/images/`，RKE2 首启自动导入。
- **内存**：kickstart 装机无 squashfs/active.img，4G 够。

## 版本管理

版本号通过 `scripts/version-*` 脚本管理，Go 二进制通过 ldflags 注入到 `pkg/version/version.go`：

```bash
scripts/version-rke2      # RKE2_VERSION="v1.31.4+rke2r1"
scripts/version-kubevirt  # KUBEVIRT_VERSION="v1.5.0"
scripts/version-longhorn  # LONGHORN_VERSION="v1.8.1"
scripts/version-kubeovn   # KUBEOVN_VERSION="v1.16.2"
scripts/version-kagent    # KAGENT_VERSION="0.9.6"
```

## 添加新组件

1. 在 `scripts/version-<组件>` 中添加版本号脚本
2. 在 `scripts/build-bundle` 中添加下载逻辑
3. 在 `package/vdi-os/iso/bundle/vdi/charts/` 中放置 chart tgz
4. 在 `package/vdi-os/iso/bundle/vdi/manifests/` 中放置 manifest YAML
5. 若 Addon execute 需要处理新资源，在 `package/vdi-os/anaconda/addons/vdi/__init__.py` 的 `execute` 方法中补充

## 深入文档指针

- [构建流程](file:///home/zcq/Github/VDI/docs/build-pipeline.md)
- [构建环境前置条件](file:///home/zcq/Github/VDI/docs/build-env.md)
- [Anaconda Addon 设计规范](file:///home/zcq/Github/VDI/docs/superpowers/specs/2026-07-02-anaconda-addon-design.md)
- [Anaconda Addon 实施计划](file:///home/zcq/Github/VDI/docs/superpowers/plans/2026-07-02-anaconda-addon.md)
