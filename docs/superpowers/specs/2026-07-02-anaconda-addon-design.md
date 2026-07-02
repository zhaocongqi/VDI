# 设计规范：VDI 定制 ISO 采用原生 Anaconda GUI Addon 架构

本文档定义了 VDI 离线安装器迁移至官方原生 Anaconda GUI Addon 架构的设计规范，旨在消灭当前 `%pre` 阶段利用 tmux/TUI 进行终端抢占的临时性 workaround，实现丝滑的操作系统原生配置与装机体验。

## 1. 架构总览
迁移后的 VDI 安装器由“操作系统原生安装器插件 (Anaconda Addon)”与“后台核心集群初始化模块”两部分构成。
Anaconda 在引导装机时，将自动加载并运行我们的 DBus Addon 服务，并在主界面（SummaryHub）SYSTEM 分类下呈现 VDI 配置页。

```
[原生 BCLinux DVD ISO 启动]
       │
       ▼
[Boss 扫描并启动 VDI Addon 服务] (通过 /usr/share/anaconda/dbus/)
       │
       ▼
[自动加载 VDI Spoke GUI 界面] (vdi_network.py)
       │
       ▼
[用户在原生 GUI 界面配置网络和 VIP] (DBus 总线更新配置状态)
       │
       ▼
[Anaconda 自动分区并装包]
       │
       ▼
[%post --nochroot 收尾阶段] (写入 RKE2 config / 拷贝离线 RKE2 镜像与包)
       │
       ▼
[物理机重启 -> RKE2 自动首启与 HelmChart CRD 部署]
```

## 2. 目录规划与文件定义
我们在 `package/vdi-os/` 目录下定义并编写了完整的 10 个 Python 源码、DBus 服务与配置声明：

* `package/vdi-os/anaconda/addons/vdi/__init__.py`
  Python 包标记（保持空内容）。
* `package/vdi-os/anaconda/addons/vdi/constants.py`
  定义 VDI Addon 的 DBus 服务标识符（`org.fedoraproject.Anaconda.Addons.Vdi`）。
* `package/vdi-os/anaconda/addons/vdi/service/vdi.py`
  核心 Python DBus 服务类，用于存储和接收用户配置的网络参数，并处理 Kickstart 状态。
* `package/vdi-os/anaconda/addons/vdi/service/vdi_interface.py`
  基于 `dasbus` 的 DBus 对象公开接口，暴露 `Ip`/`Vip` 读写属性。
* `package/vdi-os/anaconda/addons/vdi/service/kickstart.py`
  解析 ks.cfg 中 `%addon vdi` 参数的 Kickstart 模块定义。
* `package/vdi-os/anaconda/addons/vdi/service/__main__.py`
  VDI 后台服务的启动入口。
* `package/vdi-os/anaconda/addons/vdi/gui/spokes/vdi_network.py`
  GUI 交互控制器类。继承自 `pyanaconda.ui.gui.spokes.NormalSpoke`。
* `package/vdi-os/anaconda/addons/vdi/gui/spokes/vdi_network.glade`
  Glade 绘制的 GtkBox 表单参数布局 XML 文件。
* `package/vdi-os/anaconda/addons/vdi/dbus/org.fedoraproject.Anaconda.Addons.Vdi.service`
  DBus 激活配置文件。告诉 Boss 模块如何拉起服务。
* `package/vdi-os/anaconda/addons/vdi/dbus/org.fedoraproject.Anaconda.Addons.Vdi.conf`
  DBus 总线权限控制配置文件。

## 3. 技术实现细节

### 3.1 Gtk.Box 继承与 WindowWrapper 属性拦截代理
Anaconda 的 Hub 会对每个 Spoke 调用 `connect_after('help-button-clicked')`、`set_beta()` 和 `set_property('distribution')` 等专有信号和属性。因为我们使用轻量化的常规 `GtkBox` 构建表单，直接被基类处理会触发崩溃。

为此，在 `vdi_network.py` 中我们通过定义 `WindowWrapper` 拦截它们：
1. **类型安全通过**：`WindowWrapper` 直接继承自 `Gtk.Box`，使其在 C 层面具有完整的 GObject 指针，无缝通过 C 层的 `Gtk.Stack.add` 类型校验。
2. **挂载真实子树**：在其构造中执行 `self.pack_start(real_box, True, True, 0)` 将真实表单挂为子控件并 `show_all()`。
3. **安全过滤**：在 Python 层覆写并屏蔽 `set_property`、`get_property` 和 `connect_after`。
4. **Done 按钮组装**：动态在顶部包装一个 Gtk.Box 顶栏（包含建议动作样式的 "完成" 按钮），连接并触发 Spoke 的 `on_back_clicked(button)` 实现退出并保存。

### 3.2 ISO 镜像的嵌套 rootfs.img 注入机制
BCLinux 的 `install.img` 为嵌套架构：SquashFS (install.img) ➜ LiveOS/rootfs.img (ext4 运行根)。必须采用循环设备 mount 挂载注入：
1. 解压外层 SquashFS：`unsquashfs -d CACHE/install-rootfs ISO_ROOTFS/images/install.img`。
2. 挂载 ext4：`mount -o loop CACHE/install-rootfs/LiveOS/rootfs.img MNT_DIR`。
3. 将 Python 源码包拷贝至 `MNT_DIR/usr/share/anaconda/addons/vdi`。
4. 将 DBus 激活声明和配置分别拷贝至 `MNT_DIR/usr/share/anaconda/dbus/services/` 和 `MNT_DIR/usr/share/anaconda/dbus/confs/` 目录。
5. 声明式隐藏原生界面：在挂载期，通过 `sed` 修改 `MNT_DIR/etc/anaconda/profile.d/bclinux.conf` 在 `[User Interface]` 插入 `hidden_spokes = NetworkSpoke`（可空格分隔追加 `KeyboardSpoke` / `DatetimeSpoke` 等隐藏其它原生界面）以避免与自定义 Spoke 配置冲突。
6. 卸载并重新封装 SquashFS：`umount` ➜ `mksquashfs`。


### 3.3 极速热重载开发调试
为了解决装机环境下反复打包 3.4G ISO 验证导致的极低调试效率：
1. 引导参数追加 `inst.sshd` 允许装机期 SSH 直连虚机。
2. 开发了 `scripts/hot-reload-addon` 脚本，通过 `tar | ssh` 管道将本地修改的代码瞬间覆盖到虚机的 `/usr/share/anaconda/addons/`，并执行 `systemctl restart anaconda`，仅需 2 秒即可看到图形界面的热载入。

## 4. 残留资产清理计划
本分支已彻底清理了以下旧版交互残留：
1. **ks.cfg 前台劫持注销**：彻底删去了其中的 tmux 劫持窗口逻辑、`grabTTY` 键盘强占逻辑、以及 `%pre` 内阻塞 anaconda 运行的死循环等待。
2. **废弃 ISO 二进制拷贝**：不再将 `vdi-installer` 拷贝至 ISO 根目录 `/vdi/`。
3. **TUI 控制台废弃**：`pkg/console/console.go` 中的 `RunConsole()` 已经被重构为直接 `return nil`。

## 5. 自检自查与验证方法
* **热重载测试**：运行 `./scripts/hot-reload-addon 192.168.220.138`，在虚拟机图形界面中点击“VDI Network”，配置并点击左上角“完成”，观察其是否写回 DBus 并顺利退出。
* **完整 ISO 构建**：运行 `make package-vdi-iso`，最终生成的 VDI ISO 会自带上述完整的挂载注入逻辑。
