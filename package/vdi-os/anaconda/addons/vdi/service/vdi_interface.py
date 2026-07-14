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
        self.watch_property("Netmask", self.implementation.netmask_changed)
        self.watch_property("Gateway", self.implementation.gateway_changed)
        self.watch_property("Dns", self.implementation.dns_changed)
        self.watch_property("PodCidr", self.implementation.pod_cidr_changed)
        self.watch_property("ServiceCidr", self.implementation.service_cidr_changed)
        self.watch_property("JoinCidr", self.implementation.join_cidr_changed)
        self.watch_property("Role", self.implementation.role_changed)
        self.watch_property("ServerUrl", self.implementation.server_url_changed)
        self.watch_property("Token", self.implementation.token_changed)
        self.watch_property("DataDisk", self.implementation.data_disk_changed)

    @property
    def Mode(self) -> Str:
        """配置模式 (single / bond)。"""
        return self.implementation.mode

    @Mode.setter
    @emits_properties_changed
    def Mode(self, value: Str):
        self.implementation.mode = value

    @property
    def Interface(self) -> Str:
        """主物理网卡名称。"""
        return self.implementation.interface

    @Interface.setter
    @emits_properties_changed
    def Interface(self, value: Str):
        self.implementation.interface = value

    @property
    def Interface2(self) -> Str:
        """备物理网卡名称。"""
        return self.implementation.interface2

    @Interface2.setter
    @emits_properties_changed
    def Interface2(self, value: Str):
        self.implementation.interface2 = value

    @property
    def BondMode(self) -> Str:
        """网卡绑定模式 (active-backup / 802.3ad)。"""
        return self.implementation.bond_mode

    @BondMode.setter
    @emits_properties_changed
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

    @property
    def Netmask(self) -> Str:
        """子网掩码。"""
        return self.implementation.netmask

    @Netmask.setter
    @emits_properties_changed
    def Netmask(self, value: Str):
        self.implementation.netmask = value

    @property
    def Gateway(self) -> Str:
        """默认网关。"""
        return self.implementation.gateway

    @Gateway.setter
    @emits_properties_changed
    def Gateway(self, value: Str):
        self.implementation.gateway = value

    @property
    def Dns(self) -> Str:
        """DNS 服务器地址。"""
        return self.implementation.dns

    @Dns.setter
    @emits_properties_changed
    def Dns(self, value: Str):
        self.implementation.dns = value

    @property
    def PodCidr(self) -> Str:
        """POD CIDR 地址段。"""
        return self.implementation.pod_cidr

    @PodCidr.setter
    @emits_properties_changed
    def PodCidr(self, value: Str):
        self.implementation.pod_cidr = value

    @property
    def ServiceCidr(self) -> Str:
        """SERVICE CIDR 地址段。"""
        return self.implementation.service_cidr

    @ServiceCidr.setter
    @emits_properties_changed
    def ServiceCidr(self, value: Str):
        self.implementation.service_cidr = value

    @property
    def JoinCidr(self) -> Str:
        """JOIN CIDR 地址段。"""
        return self.implementation.join_cidr

    @JoinCidr.setter
    @emits_properties_changed
    def JoinCidr(self, value: Str):
        self.implementation.join_cidr = value

    @property
    def Role(self) -> Str:
        """RKE2 角色 (server / agent)。"""
        return self.implementation.role

    @Role.setter
    @emits_properties_changed
    def Role(self, value: Str):
        self.implementation.role = value

    @property
    def ServerUrl(self) -> Str:
        """Agent 模式下 RKE2 Server 的 URL。"""
        return self.implementation.server_url

    @ServerUrl.setter
    @emits_properties_changed
    def ServerUrl(self, value: Str):
        self.implementation.server_url = value

    @property
    def Token(self) -> Str:
        """Agent 模式下加入集群的 Token。"""
        return self.implementation.token

    @Token.setter
    @emits_properties_changed
    def Token(self, value: Str):
        self.implementation.token = value

    @property
    def DataDisk(self) -> Str:
        """数据盘选择 (auto 或具体设备名)。"""
        return self.implementation.data_disk

    @DataDisk.setter
    @emits_properties_changed
    def DataDisk(self, value: Str):
        self.implementation.data_disk = value

