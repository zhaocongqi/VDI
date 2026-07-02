"""VDI 管理网络 GUI Spoke（严格参考 com_redhat_kdump/gui/spokes/kdump.py 架构）"""
import logging

from pyanaconda.modules.common.util import is_module_available
from pyanaconda.ui.categories.system import SystemCategory
from pyanaconda.ui.gui.spokes import NormalSpoke

from vdi.constants import VDI

log = logging.getLogger(__name__)

__all__ = ["VdiNetworkSpoke"]


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

    def __init__(self, *args):
        NormalSpoke.__init__(self, *args)
        self._proxy = VDI.get_proxy()
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
