# 设计规范：VDI 定制 ISO 采用原生 Anaconda GUI Addon 架构

本文档定义了 VDI 离线安装器迁移至官方原生 Anaconda GUI Addon 架构的设计规范，旨在消灭当前 `%pre` 阶段利用 tmux/TUI 进行终端抢占的临时性 workaround，实现丝滑的操作系统原生配置与装机体验。

## 1. 架构总览
迁移后的 VDI 安装器由“操作系统原生安装器插件 (Anaconda Addon)”与“后台核心集群初始化模块”两部分构成。
Anaconda 在引导装机时，将自动加载我们注入的 Python 插件，呈现 VDI 配置页。

```
[原生 BCLinux DVD ISO 启动]
       │
       ▼
[自动加载 Anaconda Addon (Python)]
       │
       ▼
[用户在原生 GUI 界面配置网络和 VIP] (DBus 即时激活网络)
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
我们将在 `package/vdi-os/` 目录下新增以下 Python 源码和 Glade XML 定义：

* `package/vdi-os/anaconda/addons/vdi/__init__.py`
  插件的核心入口。继承自 `pyanaconda.addons.AnacondaAddon`。负责将 `VdiAddon` 数据模型注册进 Anaconda 的 D-Bus 全局数据总线。
* `package/vdi-os/anaconda/addons/vdi/gui/__init__.py`
  GUI 插件包声明。
* `package/vdi-os/anaconda/addons/vdi/gui/spokes/__init__.py`
  GUI spokes 声明。
* `package/vdi-os/anaconda/addons/vdi/gui/spokes/vdi_network.py`
  GUI 交互控制器类。继承自 `pyanaconda.ui.gui.spokes.NormalSpoke`。主要负责网卡扫描、GTK 表单验证、以及调用后台 D-Bus 服务即时激活网络连接。
* `package/vdi-os/anaconda/addons/vdi/ui/vdi_network.glade`
  使用 Glade 绘制的 GTK 界面布局文件（标准的 XML 描述），包含网卡选择列表、Method 单选组（静态/动态）、IPv4 静态参数输入框及集群 VIP 输入框。

## 3. 技术实现细节

### 3.1 D-Bus 数据存取与网络激活
在 `gui/spokes/vdi_network.py` 中，插件初始化时通过 `pyanaconda.core.dbus.get_proxy` 获取 Anaconda 的网络代理，读取物理网卡：
```python
from pyanaconda.modules.common.constants.services import NETWORK
from pyanaconda.core.dbus import get_proxy

class VdiNetworkSpoke(NormalSpoke):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.network_proxy = get_proxy(NETWORK)
        
    def refresh(self):
        # 扫描并在界面展示物理网卡
        devices = self.network_proxy.GetDevices()
        # 填充 GTK TreeView ...
```
当用户填写静态配置并退出界面时，调用 `network_proxy.ConfigureDevice` 立即应用该配置，以保证装机过程中的网络联通性。

### 3.2 ISO 镜像的 SquashFS 注入机制
修改构建脚本 `scripts/package-vdi-iso`，在解包原生 ISO 后，增加对 `install.img` 的重构逻辑：
1. 运行 `unsquashfs -d cache/install-rootfs cache/iso-rootfs/images/install.img` 解开镜像。
2. 创建目标插件路径，将整个 `package/vdi-os/anaconda/addons/vdi` 拷贝至 `cache/install-rootfs/usr/share/anaconda/addons/` 下。
3. 运行 `mksquashfs cache/install-rootfs cache/iso-rootfs/images/install.img -comp xz` 重新打包。
4. 清理 `cache/install-rootfs` 临时目录，并继续执行 `xorriso` 构建 ISO。

## 4. 残留资产清理计划
本分支在功能开发并测试通过后，必须彻底移除以下与旧版 %pre TUI 交互相关的代码和配置，防止冗余垃圾腐蚀项目：
1. **精简主 ks 模板**：修改 `package/vdi-os/ks/ks.cfg`，彻底删去其中的 tmux 劫持窗口逻辑、`grabTTY` 逻辑、以及 `%pre` 里的死循环等待逻辑。
2. **废弃 ISO 二进制拷贝**：在 `scripts/package-vdi-iso` 脚本中，不再将 `vdi-installer` 二进制注入到 ISO 根目录 `/vdi` 下。
3. **清理 `vdi-installer` 过时 TUI**：在 Go 源码中，删除 `pkg/console/` 目录下多余的 gocui TUI 界面及其组件，将 Go 进程退化为一个只在后台负责配置解压、Manifest 渲染的集群引导守护进程。

## 5. 自检自查与验证方法
* **无 Placeholder 扫描**：所有模块细节及路径均已明确，不存在 TODO/TBD 等模糊表述。
* **虚拟机测试**：通过 `scripts/qemu-test-ks` 启动 QEMU，手动点击验证 Anaconda GUI 界面中是否成功渲染出 "VDI 插件" spoke 配置项。
