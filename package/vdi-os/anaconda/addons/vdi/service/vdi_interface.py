"""VDI Addon DBus 接口定义（参考 com_redhat_kdump/service/kdump_interface.py）"""
from dasbus.server.interface import dbus_interface
from dasbus.server.property import emits_properties_changed
from dasbus.typing import Str
from pyanaconda.modules.common.base import KickstartModuleInterface

from vdi.constants import VDI


@dbus_interface(VDI.interface_name)
class VdiInterface(KickstartModuleInterface):
    """VDI Addon 的 DBus 接口。"""

    def connect_signals(self):
        super().connect_signals()
        self.watch_property("Ip", self.implementation.ip_changed)
        self.watch_property("Vip", self.implementation.vip_changed)

    @property
    def Ip(self) -> Str:
        """管理网络 IPv4 地址。"""
        return self.implementation.ip

    @Ip.setter
    @emits_properties_changed
    def Ip(self, value: Str):
        self.implementation.ip = value

    @property
    def Vip(self) -> Str:
        """集群虚拟 IP 地址。"""
        return self.implementation.vip

    @Vip.setter
    @emits_properties_changed
    def Vip(self, value: Str):
        self.implementation.vip = value

