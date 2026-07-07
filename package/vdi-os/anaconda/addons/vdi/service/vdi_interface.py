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
        self.watch_property("Mode", self.implementation.mode_changed)
        self.watch_property("Interface", self.implementation.interface_changed)
        self.watch_property("Interface2", self.implementation.interface2_changed)
        self.watch_property("BondMode", self.implementation.bond_mode_changed)
        self.watch_property("Ip", self.implementation.ip_changed)
        self.watch_property("Vip", self.implementation.vip_changed)
        self.watch_property("NetworkMode", self.implementation.network_mode_changed)

    @property
    def Mode(self) -> Str:
        """配置模式 (single / bond)。"""
        return self.implementation.mode

    @Mode.setter
    def Mode(self, value: Str):
        self.implementation.mode = value

    @property
    def Interface(self) -> Str:
        """主物理网卡名称。"""
        return self.implementation.interface

    @Interface.setter
    def Interface(self, value: Str):
        self.implementation.interface = value

    @property
    def Interface2(self) -> Str:
        """备物理网卡名称。"""
        return self.implementation.interface2

    @Interface2.setter
    def Interface2(self, value: Str):
        self.implementation.interface2 = value

    @property
    def BondMode(self) -> Str:
        """网卡绑定模式 (active-backup / 802.3ad)。"""
        return self.implementation.bond_mode

    @BondMode.setter
    def BondMode(self, value: Str):
        self.implementation.bond_mode = value

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

    @property
    def NetworkMode(self) -> Str:
        """网络配置模式 (dhcp / static)。"""
        return self.implementation.network_mode

    @NetworkMode.setter
    @emits_properties_changed
    def NetworkMode(self, value: Str):
        self.implementation.network_mode = value

