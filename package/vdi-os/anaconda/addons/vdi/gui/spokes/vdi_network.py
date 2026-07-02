"""VDI 管理网络 GUI Spoke（严格参考 com_redhat_kdump/gui/spokes/kdump.py 架构）"""
import logging

from pyanaconda.modules.common.util import is_module_available
from pyanaconda.ui.categories.system import SystemCategory
from pyanaconda.ui.gui.spokes import NormalSpoke

from vdi.constants import VDI

log = logging.getLogger(__name__)

__all__ = ["VdiNetworkSpoke"]


class WindowWrapper(object):
    """GTK 窗口包裹代理。

    专门用于在不使用 Anaconda 专有窗口组件的情况下，
    屏蔽 connect_after('help-button-clicked') 以及 set_beta()
    等仅在 AnacondaWidgets 中存在的信号和方法。
    """

    def __init__(self, gtk_widget):
        self._widget = gtk_widget

    def __getattr__(self, name):
        # 动态转发所有其它常规 GObject 属性与方法
        return getattr(self._widget, name)

    def set_beta(self, beta):
        # 屏蔽 Hub 调用
        pass

    def connect_after(self, signal, callback):
        # 屏蔽 NormalSpoke 的帮助信号绑定
        if signal == "help-button-clicked":
            return
        return self._widget.connect_after(signal, callback)


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
        if self._wrapped_window is None or self._wrapped_window._widget != self._raw_window:
            self._wrapped_window = WindowWrapper(self._raw_window)
        return self._wrapped_window

    @window.setter
    def window(self, val):
        """捕获基类的 window 实例写入，保存在内部私有变量中。"""
        self._raw_window = val

    def __init__(self, data, storage, payload):
        self._raw_window = None
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
