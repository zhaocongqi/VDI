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
    同时在 Python 层面屏蔽 Anaconda 专有信号和属性写入。
    """

    def __init__(self, real_box):
        # 初始化基类 Gtk.Box 容器
        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(0)
        self._real_box = real_box

        # 将从 Glade 加载出的真实内容组件添加为子控件并显示
        self.pack_start(self._real_box, True, True, 0)
        self.show_all()

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
    提供 IPv4 地址和集群虚拟 IP 的配置入口。
    """

    builderObjects = ["vdi_network_box"]
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
        # 显式调用父类原始的 lazy-load 属性读取方法，获取真实的 GTK 控件
        raw_win = GUIObject.window.fget(self)
        if self._wrapped_window is None or self._wrapped_window._real_box != raw_win:
            self._wrapped_window = WindowWrapper(raw_win)
        return self._wrapped_window

    def __init__(self, data, storage, payload):
        self._wrapped_window = None
        # 正常跑基类初始化，内部的所有 self.window 读写都会被上面的 property 接管
        NormalSpoke.__init__(self, data, storage, payload)
        self._proxy = VDI.get_proxy()
        self._ip_entry = None
        self._vip_entry = None
        log.debug("VdiNetworkSpoke 已初始化, proxy=%s", self._proxy)

    def initialize(self):
        """初始化 GTK 控件引用。"""
        NormalSpoke.initialize(self)
        self._ip_entry = self.builder.get_object("ip_entry")
        self._vip_entry = self.builder.get_object("vip_entry")
        log.debug("VdiNetworkSpoke 控件初始化完成")

    def refresh(self):
        """刷新界面，从 DBus 代理读取数据并填充控件。"""
        self._ip_entry.set_text(self._proxy.Ip)
        self._vip_entry.set_text(self._proxy.Vip)

    def apply(self):
        """将界面数据写回 DBus 代理。"""
        self._proxy.Ip = self._ip_entry.get_text()
        self._proxy.Vip = self._vip_entry.get_text()

    @property
    def ready(self):
        """Spoke 是否已就绪可以被访问。"""
        return True

    @property
    def completed(self):
        """配置是否已完成。"""
        return True

    @property
    def mandatory(self):
        """该 Spoke 是否为强制必填。"""
        return False

    @property
    def status(self):
        """在 Hub 主界面上显示的一行状态摘要文字。"""
        return "IP: %s  VIP: %s" % (self._proxy.Ip, self._proxy.Vip)
