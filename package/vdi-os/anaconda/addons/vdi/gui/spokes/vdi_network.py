"""VDI 管理网络 GUI Spoke（严格参考 com_redhat_kdump/gui/spokes/kdump.py 架构）"""
import logging

from gi.repository import Gtk
from pyanaconda.modules.common.util import is_module_available
from pyanaconda.ui.categories.system import SystemCategory
from pyanaconda.ui.gui.spokes import NormalSpoke

from vdi.constants import VDI

log = logging.getLogger(__name__)

__all__ = ["VdiNetworkSpoke"]


class WindowWrapper(Gtk.Box):
    """GTK 窗口包裹代理。

    直接继承自 Gtk.Box 以通过 Gtk.Stack C 语言底层的类型安全校验，
    并在顶部动态组装包含“完成”按钮的导航条，实现退出并保存配置。
    """

    def __init__(self, real_box, spoke_instance):
        # 初始化基类 Gtk.Box 容器
        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(6)
        self._real_box = real_box
        self._spoke = spoke_instance

        # 1. 创建顶栏水平容器
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(12)
        header_box.set_margin_start(18)
        header_box.set_margin_end(18)

        # 2. 创建“完成 (Done)”退出确认按钮，并应用 suggested-action（蓝色高亮样式）
        done_button = Gtk.Button.new_with_mnemonic("完成 (_D)")
        done_button.get_style_context().add_class("suggested-action")
        done_button.set_size_request(80, 36)
        done_button.connect("clicked", self._on_done_clicked)
        header_box.pack_start(done_button, False, False, 0)

        # 3. 标题标签
        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold'>VDI 管理网络配置</span>")
        title_label.set_margin_start(18)
        header_box.pack_start(title_label, False, False, 0)

        # 4. 按顺序组装：顶栏 -> 水平分割线 -> 真实表单内容
        self.pack_start(header_box, False, False, 0)
        
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(separator, False, False, 0)

        self.pack_start(self._real_box, True, True, 0)
        self.show_all()

    def _on_done_clicked(self, button):
        # 触发 Spoke 绑定的退出回调，Anaconda 会自动调用 apply() 并切回主 Hub
        if self._spoke:
            self._spoke.on_back_clicked(button)

    def set_beta(self, beta):
        # 屏蔽 Hub 水印设置
        pass

    def set_property(self, name, value):
        # 拦截 GtkBox 不支持的 Anaconda 专有属性，避免 GTK 抛出 TypeError
        if name in ("distribution", "window-name", "window_name"):
            return
        return Gtk.Box.set_property(self, name, value)

    def get_property(self, name):
        # 提供默认的安全属性回包
        if name in ("distribution", "window-name", "window_name"):
            return ""
        return Gtk.Box.get_property(self, name)

    def connect_after(self, signal, callback):
        # 屏蔽 NormalSpoke 的帮助信号绑定
        if signal == "help-button-clicked":
            return
        return Gtk.Box.connect_after(self, signal, callback)


class VdiNetworkSpoke(NormalSpoke):
    """VDI 管理网络图形配置 Spoke。

    在 Anaconda 安装器主界面（Hub）的 SYSTEM 分类下显示，
    提供配置模式（单网卡/绑定）、物理网卡选择、IPv4 地址和集群虚拟 IP 的配置入口。
    """

    builderObjects = [
        "vdi_network_box",
        "network_mode_combo",
        "mode_combo",
        "interface_combo",
        "interface2_label",
        "interface2_combo",
        "bond_mode_label",
        "bond_mode_combo",
        "ip_label",
        "ip_entry",
        "vip_label",
        "vip_entry"
    ]
    mainWidgetName = "vdi_network_box"
    uiFile = "vdi_network.glade"

    icon = "network-wired-symbolic"
    title = "VDI _Network"
    category = SystemCategory

    @classmethod
    def should_run(cls, environment, data):
        """判断该 Spoke 是否应该在当前环境中显示。"""
        return is_module_available(VDI)

    @property
    def window(self):
        """覆盖基类的 window 实例读取，动态返回包装代理类。"""
        from pyanaconda.ui.gui import GUIObject
        raw_win = GUIObject.window.fget(self)
        if self._wrapped_window is None or self._wrapped_window._real_box != raw_win:
            self._wrapped_window = WindowWrapper(raw_win, self)
        return self._wrapped_window

    def __init__(self, data, storage, payload):
        self._wrapped_window = None
        # 必须在 NormalSpoke.__init__ 之前初始化控件占位，因为父类 __init__
        # 可能访问 self.window property，触发 show_all 后的显隐同步代码。
        self._network_mode_combo = None
        self._mode_combo = None
        self._interface_combo = None
        self._interface2_label = None
        self._interface2_combo = None
        self._bond_mode_label = None
        self._bond_mode_combo = None
        self._ip_label = None
        self._ip_entry = None
        self._vip_label = None
        self._vip_entry = None
        NormalSpoke.__init__(self, data, storage, payload)
        self._proxy = VDI.get_proxy()

        # 获取 Anaconda 官方网络服务代理，用于获取可用网卡
        from pyanaconda.modules.common.constants.services import NETWORK
        try:
            self.network_proxy = NETWORK.get_proxy()
        except Exception as e:
            log.error("无法获取 NetworkManager D-Bus 代理: %s", e)
            self.network_proxy = None

        # 用户是否已在 Spoke 内确认配置（点完成触发 apply）。
        # 驱动 completed：未确认前 Hub 视为未完成，强制用户进 Spoke 配置后才允许开装。
        self._configured = False
        log.debug("VdiNetworkSpoke 已初始化, proxy=%s", self._proxy)

    def initialize(self):
        """初始化 GTK 控件引用并绑定交互信号。"""
        NormalSpoke.initialize(self)
        self._network_mode_combo = self.builder.get_object("network_mode_combo")
        self._mode_combo = self.builder.get_object("mode_combo")
        self._interface_combo = self.builder.get_object("interface_combo")
        self._interface2_label = self.builder.get_object("interface2_label")
        self._interface2_combo = self.builder.get_object("interface2_combo")
        self._bond_mode_label = self.builder.get_object("bond_mode_label")
        self._bond_mode_combo = self.builder.get_object("bond_mode_combo")
        self._ip_label = self.builder.get_object("ip_label")
        self._ip_entry = self.builder.get_object("ip_entry")
        self._vip_label = self.builder.get_object("vip_label")
        self._vip_entry = self.builder.get_object("vip_entry")

        # 监听网络模式下拉框改变事件，以动态启用/禁用 IP/VIP 输入框
        self._network_mode_combo.connect("changed", self._on_network_mode_changed)
        # 监听模式下拉框改变事件，以动态展示/隐藏备网卡及 Bond 模式选项
        self._mode_combo.connect("changed", self._on_mode_changed)

        # initialize 时控件已全部绑定，执行一次显隐同步，覆盖 glade 默认值 + show_all 副作用
        self._sync_visibility()

        log.debug("VdiNetworkSpoke 控件初始化完成")

    def _sync_visibility(self):
        """根据 D-Bus proxy 的实际值同步控件显隐。不依赖 combo 的 get_active_id。"""
        network_mode = self._proxy.NetworkMode or "dhcp"
        mode = self._proxy.Mode or "single"

        is_static = (network_mode == "static")
        self._ip_label.set_visible(is_static)
        self._ip_entry.set_visible(is_static)
        self._vip_label.set_visible(is_static)
        self._vip_entry.set_visible(is_static)
        if not is_static:
            self._ip_entry.set_text("")
            self._vip_entry.set_text("")

        is_bond = (mode == "bond")
        self._interface2_label.set_visible(is_bond)
        self._interface2_combo.set_visible(is_bond)
        self._bond_mode_label.set_visible(is_bond)
        self._bond_mode_combo.set_visible(is_bond)

    def _on_network_mode_changed(self, combo):
        """当网络模式在 DHCP 与静态之间切换时的响应。"""
        active_id = combo.get_active_id()
        if active_id is None:
            active_id = "dhcp"
        self._proxy.NetworkMode = active_id
        self._sync_visibility()

    def _on_mode_changed(self, combo):
        """当网络配置模式在单网卡与网卡绑定之间切换时的响应。"""
        active_id = combo.get_active_id()
        if active_id is None:
            active_id = "single"
        self._proxy.Mode = active_id
        self._sync_visibility()

    def _fill_network_interfaces(self):
        """扫描系统的物理网卡列表并填充到界面下拉栏中。"""
        if not self.network_proxy:
            return
        
        try:
            devices = self.network_proxy.GetDevices()
        except Exception as e:
            log.error("D-Bus 获取网卡列表失败: %s", e)
            devices = ["ens33", "ens34"] # 降级默认备选

        # 过滤掉本地环回
        physical_devs = [d for d in devices if d != "lo"]

        self._interface_combo.remove_all()
        self._interface2_combo.remove_all()

        for dev in physical_devs:
            self._interface_combo.append(dev, dev)
            self._interface2_combo.append(dev, dev)

    def refresh(self):
        """刷新界面，从 DBus 代理读取数据并填充控件。"""
        # 1. 扫描网卡列表
        self._fill_network_interfaces()

        # 2. 从 DBus 回显数据状态
        network_mode_val = self._proxy.NetworkMode or "dhcp"
        self._network_mode_combo.set_active_id(network_mode_val)

        mode_val = self._proxy.Mode or "single"
        self._mode_combo.set_active_id(mode_val)

        if self._proxy.Interface:
            self._interface_combo.set_active_id(self._proxy.Interface)
        else:
            self._interface_combo.set_active(0) # 默认选第一块

        if self._proxy.Interface2:
            self._interface2_combo.set_active_id(self._proxy.Interface2)
        else:
            self._interface2_combo.set_active(0)

        bond_mode_val = self._proxy.BondMode or "active-backup"
        self._bond_mode_combo.set_active_id(bond_mode_val)

        self._ip_entry.set_text(self._proxy.Ip)
        self._vip_entry.set_text(self._proxy.Vip)

        # 3. 强制触发显隐同步
        self._sync_visibility()

    def apply(self):
        """将界面数据写回 DBus 代理。"""
        self._proxy.NetworkMode = self._network_mode_combo.get_active_id() or "dhcp"
        self._proxy.Mode = self._mode_combo.get_active_id() or "single"
        self._proxy.Interface = self._interface_combo.get_active_id() or ""

        # 若是 Bonding 模式，对主/备网卡重合执行防御性校验
        if self._proxy.Mode == "bond":
            dev1 = self._interface_combo.get_active_id()
            dev2 = self._interface2_combo.get_active_id()
            if dev1 == dev2:
                # 冲突时备用网卡置空或提示
                self._proxy.Interface2 = ""
                log.warning("主备物理网卡选择重合，已静默将备网卡置空。")
            else:
                self._proxy.Interface2 = dev2 or ""
            self._proxy.BondMode = self._bond_mode_combo.get_active_id() or "active-backup"
        else:
            self._proxy.Interface2 = ""
            self._proxy.BondMode = "active-backup"

        # 静态模式下写 IP/VIP，DHCP 模式下写空串
        if self._proxy.NetworkMode == "static":
            self._proxy.Ip = self._ip_entry.get_text()
            self._proxy.Vip = self._vip_entry.get_text()
        else:
            self._proxy.Ip = ""
            self._proxy.Vip = ""

        # 用户点完成触发 apply，标记配置已确认，驱动 completed 让 Hub 放行开装。
        self._configured = True

    @property
    def ready(self):
        """Spoke 是否已就绪。"""
        return True

    @property
    def completed(self):
        """配置是否已完成。DHCP 模式只需选网卡，静态模式需要网卡 + IP。"""
        if not self._configured:
            return False
        if self._proxy.NetworkMode == "dhcp":
            return bool(self._proxy.Interface)
        else:
            return bool(self._proxy.Interface and self._proxy.Ip)

    @property
    def mandatory(self):
        """该 Spoke 是否为强制必填。mandatory=True 使 Hub 在未完成时不自动开装。"""
        return True

    @property
    def status(self):
        """在 Hub 主界面上显示的一行状态摘要文字。"""
        if not self._configured:
            return "未配置，请点击进入配置管理网络"
        if self._proxy.NetworkMode == "dhcp":
            return "DHCP: %s" % self._proxy.Interface
        if self._proxy.Mode == "bond":
            return "Static Bonding[%s]: %s,%s  IP: %s" % (
                self._proxy.BondMode,
                self._proxy.Interface,
                self._proxy.Interface2 or "未配置",
                self._proxy.Ip
            )
        return "Static: %s  IP: %s" % (self._proxy.Interface, self._proxy.Ip)
