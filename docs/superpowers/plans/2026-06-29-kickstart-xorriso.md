# Kickstart + xorriso 迁移实施计划

- 分支：`feat/kickstart-xorriso`（基于 `main`，main 的 elemental Live 型保留不动）
- 日期：2026-06-29
- 决策：Kickstart + xorriso 做定制化 ISO（BCLinux 母语路）；保留 gocui TUI 作 kickstart 生成器；不要不可变回滚（节点坏了重装即可）

## 1. 背景

main 分支用 SUSE elemental 做 ISO 构建 + 落地，但 BCLinux 是 RHEL 系，elemental 是为 SUSE MicroOS 设计的，跨生态导致一长串踩坑（cos-img dracut 模块、grubx64.efi 字节级注入、kernel 复制到 COS_STATE、分区三常量配套、selinux=0……）。kickstart + xorriso 是 BCLinux 的母语路，删除上述整条 hack 链。

## 2. 目标架构

介质形态：BCLinux DVD ISO（xorriso 重建），嵌入 ks 模板 + vdi-installer 二进制 + RKE2/组件 bundle。是"安装型"介质（含 anaconda + 安装树），不是自建 squashfs Live。

TUI 运行模型（kickstart 地道用法）：用 `%pre` 段跑 gocui TUI。
1. ISO 引导 → `inst.ks=hd:LABEL=...:/ks-template.cfg` → anaconda 启动
2. anaconda 执行 `%pre` → 调 `vdi-installer`（gocui TUI 在 tty1）收集配置（模式/网络/磁盘/VIP/密码）
3. TUI 退出前把动态配置写到 `/tmp/ks-include.cfg`（网络、磁盘、分区、密码、RKE2 role）
4. ks-template 用 `%include /tmp/ks-include.cfg` 吸收动态段
5. anaconda 按 ks 装机（分区/装包）→ `%post` 装 RKE2 + 预置镜像 + 写 manifests
6. 重启 → RKE2 首启自动导入 `agent/images/` 镜像 → HelmChart CRD 部署组件栈

TUI 退化为"配置收集 + ks 片段生成器"，落地全交 anaconda。

数据流：BCLinux DVD ISO → xorriso 重建（嵌入 ks + vdi-installer + bundle）→ 安装型 ISO → `%pre` TUI 生成 ks → anaconda 装盘 → `%post` 装 RKE2 → 首启 RKE2 自导镜像 → 组件栈起。

## 3. 核心简化点（vs elemental）

| 当前 elemental 链 | kickstart 链 | 收益 |
|---|---|---|
| `elemental build-iso` 从 Docker 镜像提 rootfs 打 squashfs | xorriso 重建 DVD ISO（复用自带 stage2） | 删 elemental + 自建 Live rootfs |
| `elemental install` + active/passive/recovery.img 模型 | anaconda 按 ks 分区（普通 ext4/lvm） | 删 active.img loop 挂载整条 |
| 自写 `90cos-img` dracut 模块（pre-pivot loop 挂 active.img 覆盖 /sysroot） | 无（anaconda 标准引导） | 整模块删除 |
| `dmsquash-live` 注入 + `dracut --add cos-img` 重建 initrd | 无（DVD ISO 自带 stage2） | 删 dracut 重建段 |
| 字节级注入 grubx64.efi（BCLinux shim 硬编码）+ `fix_efi_grubx64` | DVD ISO 自带正确 EFI 引导 | 删两处 grubx64 hack |
| `copy_kernel_to_state`（避 grub loopback OOM） | 无（无 active.img loopback） | 删除 |
| wharfie 从 `system-agent-installer-rke2` 提取 RKE2 二进制+containerd | RKE2 官方 `rke2.linux-amd64.tar.gz` 解压 | 删 wharfie + rancherd bootstrap |
| chroot 启临时 containerd + `ctr import --no-unpack` + `rm -f $i` | 镜像 tar.zst 放 `agent/images/`，RKE2 首启自动导入 | 删 chroot 导入整段 |
| yip（ConvertToCOS）首启配置 | `%post` 直接写文件 | 删 yip 依赖 |
| 分区三常量配套（COS_STATE/RECOVERY/SystemImage） | ks `part` 指令 | 删 4 个常量 + 配套验算 |
| grub2 EFI 模块从 debian bookworm 提取 | DVD ISO 自带 grub2-efi | 删 grub-efi-modules 阶段 |
| `selinux=0`（ext2 xattr 权限） | 标准 selinux（permissive/可选） | 删内核参数 hack |

## 4. 受影响文件清单

### 删除
- `package/vdi-os/files/usr/lib/dracut/modules.d/90cos-img/` — 整个自写模块
- `package/vdi-os/files/usr/lib/dracut/modules.d/90dmsquash-live/`、`90livenet/`、`99img-lib/` — 自注入 live 模块（DVD 自带）
- `package/vdi-os/files/usr/sbin/vdi-install` — elemental 落地脚本（逻辑拆进 ks `%post`）
- `package/vdi-os/files/etc/cos/grub.cfg` + `bootargs.cfg` — active.img 引导模板
- `package/vdi-os/files/usr/bin/elemental`、`wharfie`、`yip` — fetch-deps 不再下载
- `pkg/config/cos.go` 的 ElementalConfig/ElementalInstallSpec/ElementalSystem/ElementalDefaultPartition/ConvertToElementalConfig/CreateRootPartitioningLayout*/ConvertToCOS（yip）
- `pkg/config/constants.go:56-62` 的 `DefaultCos*SizeMiB`/`DefaultSystemImageSizeMiB`
- `scripts/fetch-deps` 的 elemental/wharfie/yip 下载段
- `scripts/build-bundle` 的 rancherd bootstrap images 段（wharfie 提取源）

### 改造
- `scripts/package-vdi-os` — 从 `elemental build-iso` + grubx64 注入，改为 xorriso 重建 BCLinux DVD ISO（嵌入 ks + vdi-installer + bundle + 改 isolinux/grub 加 `inst.ks`）
- `package/vdi-os/Dockerfile` — 删 dracut 重建、grub-efi-modules 阶段、elemental/wharfie/yip chmod；角色从"构建 elemental rootfs 镜像"变为"构建 vdi-installer 二进制 + 打包 bundle 的辅助镜像"
- `pkg/console/auto_install.go` + `pkg/console/util.go` doInstall() — 从"生成 elemental env + exec vdi-install"改为"生成 ks 片段写到 `/tmp/ks-include.cfg` 后退出"（落地交 anaconda）
- `scripts/build-bundle` — 新增 `rke2.linux-amd64.tar.gz`（RKE2 二进制）下载；保留 rke2-images + 组件 images + charts + lists 打包

### 新增
- `package/vdi-os/ks/ks-template.cfg` — kickstart 模板（`%pre` include TUI + 安装段 + `%post`）
- `package/vdi-os/ks/post-install.sh` — `%post` 脚本（装 RKE2 + 放镜像 + 写 manifests，从 vdi-install 迁移）
- `pkg/config/kickstart.go` — `VDIConfig` → ks 动态片段渲染（替代 ConvertToElementalConfig），复用现有 `RenderRKE2Config`/`RenderRKE2Manifests`（`cos.go:341-357`，不依赖 elemental，直接复用）
- `scripts/package-vdi-iso`（或重构 package-vdi-os）— xorriso 重建逻辑

## 5. ks.cfg 结构

```ks
# ks-template.cfg
%pre --interpreter=/bin/bash
# 挂载 ISO 拿 vdi-installer + bundle，跑 TUI 生成 /tmp/ks-include.cfg
mount CD LABEL → /run/install/repo
/run/install/repo/vdi/vdi-installer   # gocui TUI 收集配置
# TUI 退出前写 /tmp/ks-include.cfg（network/partition/rootpw/rke2-role）
%end

%include /tmp/ks-include.cfg

%packages
@core <RKE2 运行依赖: container-selinux, iptables, socat, conntrack...>
%end

%post --interpreter=/bin/bash
# 装 RKE2 二进制（官方 tar.gz 解压 /usr/local）
# 放 rke2-images + 组件 tar.zst → /var/lib/rancher/rke2/agent/images/
# 写 config.yaml + manifests + charts（复用 RenderRKE2Config/Manifests 产物）
# enable rke2-server/agent + mask vdi-setup-installer
# 格式化数据盘 VDI_LH_DEFAULT
%end
```

## 6. %post RKE2 安装逻辑（复用 vdi-install）

复用 vdi-install 的：写 RKE2 config.yaml（`/etc/rancher/rke2/`）、manifests（`server/manifests/`）、charts tgz（`server/charts/`）、mask `vdi-setup-installer.service`、数据盘格式化（`do_data_disk_format`）。

删除 vdi-install 的：`elemental install`、`do_mount`（losetup active.img）、`preload_rke2_images` 的 chroot containerd + wharfie + ctr import + `rm -f $i`、`fix_efi_grubx64`、`copy_kernel_to_state`、`update_grub_settings`（cos bootargs）。

镜像导入简化：`rke2-images.linux-amd64.tar.zst` + `kubevirt/longhorn/kubeovn-*.tar.zst` 全部放 `/var/lib/rancher/rke2/agent/images/`，RKE2 首启自动导入（RKE2 标准离线机制），删手动 chroot 导入。

RKE2 二进制：`rke2.linux-amd64.tar.gz` 解压到 `/usr/local`（含 `bin/rke2`、`bin/containerd`、`share/`、`lib/systemd/system/rke2-*.service`），`systemctl enable rke2-server`（首节点）或 `rke2-agent`（加入节点）。删 wharfie。

## 7. TUI（vdi-installer）改造

auto_install.go/doInstall() 当前编排：ConvertToCOS → ConvertToElementalConfig → CreateRootPartitioningLayout* → 渲染 RKE2 config/manifests → exec `/usr/sbin/vdi-install`。

改为：收集配置 → 渲染 ks 动态片段（kickstart.go）+ RKE2 config/manifests（复用 RenderRKE2Config/RenderRKE2Manifests）→ 写 `/tmp/ks-include.cfg` + RKE2 配置产物写到 ISO 挂载点约定路径供 `%post` 读取 → 退出 TUI（anaconda 接管）。删 exec vdi-install 子进程链 + Setsid/tty1 断开 hack。

`pkg/console/helper.go` 的 yipSchema 用法删除。

## 8. 关键风险与缓解

1. **`%pre` 跑 gocui TUI 可行性**（最大不确定）：anaconda `%pre` 在 tty1 跑，gocui/termbox 需 tty + winsize。MVP1 验证。备选：TUI 跑在 rescue 环境，生成 ks 后 `anaconda --kickstart` 装机；或 TUI 离线生成 ks 嵌入 ISO（纯无人值守）。
2. **xorriso 重建 BCLinux DVD ISO**：标准 RHEL 定制 ISO 操作，但 DVD 体积大（4-6G），需确认 EFI+BIOS 双引导重建成功（elemental 踩的 ~3174MB 容量失败是 squashfs live ISO 的 EFI 重建问题，标准 DVD ISO 重建应无此限）。MVP1 验证。
3. **RKE2 首启自动导入大镜像耗时**：rke2 + 组件 ~5G，首启导入数分钟。首启 ready 延迟纳入验证。
4. **`%post` 环境与目标路径**：`%post` 默认 chroot 到目标根，直接写 `/etc/rancher/...` 即目标盘路径。注意 `--nochroot` vs chroot 模式选择（放镜像到目标盘用 chroot 模式）。
5. **数据盘分区**：Longhorn 数据盘（第二块盘）用 `%post` `mkfs.ext4 -L VDI_LH_DEFAULT`，不用 ks `part`（ks part 针对主盘）。
6. **qemu `--auto-install` 适配**：auto_install.go 改为生成 ks 片段后，qemu 验证链路改为 ISO 引导 → `%pre`（环境变量预置配置绕过 TUI 交互）→ anaconda 装机。

## 9. 分阶段实施

### MVP1 — 介质构建 + 无人值守装机骨架 ✅ 已完成
- xorriso 重建 BCLinux DVD ISO，嵌入 ks.cfg + 改 isolinux.cfg/grub.cfg 加 `inst.ks` + `console=ttyS0`
- qemu UEFI 无人值守装机到 /dev/vda 成功启动到 BCLinux 登录，SSH 验证系统完好
- 验证结果：BigCloud 21.10 U5 LTS / 内核 5.10.0-200 / LVM(boot+efi+root+swap+home) / enp0s2 DHCP / SELinux Permissive / iptables+ebtables+ipset 就绪
- 产出：`scripts/package-vdi-iso` + `package/vdi-os/ks/ks.cfg` + `scripts/qemu-test-ks`

#### MVP1 踩坑（BCLinux anaconda 36 兼容性）
- `install` 指令已移除（line 10 报错 "install has been removed"）→ 删除
- `autostep` 已废弃（warning）→ 删除
- `%packages` 缺包即失败（`conntrack-tools/container-selinux/ipvsadm/socat/iptables-services` 仓库无）→ 精简到仓库内有的包，缺失留 MVP2 补
- `rootpw --iscrypted` 偶发不生效 → `%post` 用 `echo "root:vdi123" | chpasswd` 兜底
- xorriso 解包文件 0444 只读 → 解包后 `chmod -R u+w`，删旧目录前同
- BCLinux ISO 自带 `/ks/ks.cfg` 示例 → 删除避免与根 `/ks.cfg` 混淆
- `%post` 输出到 `/dev/console` 不通串口 → 用 `/dev/ttyS0` 诊断（已清理）
- qemu 验证：须 `sg kvm -c`（usermod -aG kvm 后会话未刷新）；多并发 qemu 争磁盘锁导致密码登录假失败，须单实例 + nohup

### MVP2 — RKE2 离线安装 + 单节点起来 ✅ 已完成
- `build-bundle` 加 `rke2.linux-amd64.tar.gz`（RKE2 二进制+containerd+systemd unit）下载到 `bundle/vdi/binaries/`
- `package-vdi-iso` 打包 `iso/bundle/` 整个进 ISO（images 2.3G + binaries + charts）
- ks 双 %post：`--nochroot` 从 `/run/install/repo/bundle` 复制镜像→`agent/images/`、二进制→`/tmp`、charts→`server/charts/`；chroot 解压 rke2→`/usr/local`、写 config.yaml、enable rke2-server
- qemu 装机后 RKE2 server active，`kubectl get nodes` Ready（control-plane/etcd/master），etcd/apiserver/controller-manager/proxy/cloud-controller Running，canal/coredns/metrics-server helm-install Completed
- 验证：装机（11min，磁盘 15.4G）→ 引导 → RKE2 首启（~3min 导入镜像+etcd）→ node Ready
- 产出：build-bundle 加 binaries 下载 + package-vdi-iso 打包 bundle + ks.cfg 双 %post

#### MVP2 踩坑
- `%post --nochroot` 访问 ISO 用 `/run/install/repo`（非 chroot），目标盘用 `/mnt/sysroot`；chroot %post 访问目标盘用正常路径
- RKE2 tar.gz 无独立 containerd（rke2 二进制内嵌），解压到 `/usr/local` 即可，省 wharfie 提取
- RKE2 首启自动导入 `agent/images/*.tar.zst`（标准离线机制），删 chroot containerd + ctr import 整段
- ISO 5.6G（DVD 3.3G + bundle 2.3G），xorriso 重建无 ~3174MB 限制（那是 elemental squashfs live 的问题）
- 镜像导入 + etcd 初始化首启约 3 分钟，kubectl 验证需等足

### MVP3 — TUI 作 ks 生成器
- `pkg/config/kickstart.go`：VDIConfig → ks 动态片段
- `auto_install.go`/`doInstall()` 改造：生成 ks 片段而非 elemental env
- ks `%pre` 调 vdi-installer TUI（验证 `%pre` gocui 可行性，不行走 rescue 备选）
- 验证：TUI 配置 → 生成 ks → anaconda 装机 → RKE2 起来
- 产出：kickstart.go + TUI 改造 + `%pre` 集成

### MVP4 — 组件栈 + 多节点 + 数据盘
- HelmChart 组件栈（kube-ovn/longhorn/kubevirt/kagent）端到端
- 多节点（首节点 + 加入节点，rke2-agent）
- Longhorn 数据盘格式化 + 持久化
- 验证：3 节点集群 + 组件 Running + PV 动态供给

## 10. 验证方式（qemu 端到端）
- 构建安装型 ISO
- qemu 引导 ISO（UEFI + BIOS 双验证），`%pre`/无人值守装机到 /dev/vda
- 重启从盘引导 → RKE2 ready → `kubectl get nodes/pods`
- auto_install qemu 自动化：`%pre` 用预置配置绕过 TUI 交互（环境变量/预置 ks-include）
