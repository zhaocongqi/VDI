"""VDI Addon 服务实现（参考 com_redhat_kdump/service/kdump.py）"""
import logging

from pyanaconda.core.configuration.anaconda import conf
from pyanaconda.core.dbus import DBus
from pyanaconda.core.signal import Signal
from pyanaconda.modules.common.base import KickstartService
from pyanaconda.modules.common.containers import TaskContainer

from vdi.constants import VDI
from vdi.service.vdi_interface import VdiInterface
from vdi.service.kickstart import VdiKickstartSpecification
from vdi.service.installation import VdiInstallationTask

log = logging.getLogger(__name__)

__all__ = ["VdiService"]


class VdiService(KickstartService):
    """VDI Addon 服务：管理 VDI 管理网络配置状态。"""

    def __init__(self):
        super().__init__()
        self._mode = "single"
        self.mode_changed = Signal()

        self._interface = "ens33"
        self.interface_changed = Signal()

        self._interface2 = ""
        self.interface2_changed = Signal()

        self._bond_mode = "active-backup"
        self.bond_mode_changed = Signal()

        # bond1/bond2 业务网络绑定（可选）
        self._bond1_enabled = False
        self.bond1_enabled_changed = Signal()
        self._bond1_interface = ""
        self.bond1_interface_changed = Signal()
        self._bond1_interface2 = ""
        self.bond1_interface2_changed = Signal()
        self._bond1_bond_mode = "active-backup"
        self.bond1_bond_mode_changed = Signal()
        self._bond1_network_mode = "static"
        self.bond1_network_mode_changed = Signal()
        self._bond1_ip = ""
        self.bond1_ip_changed = Signal()
        self._bond1_netmask = "255.255.255.0"
        self.bond1_netmask_changed = Signal()
        self._bond1_gateway = ""
        self.bond1_gateway_changed = Signal()

        self._bond2_enabled = False
        self.bond2_enabled_changed = Signal()
        self._bond2_interface = ""
        self.bond2_interface_changed = Signal()
        self._bond2_interface2 = ""
        self.bond2_interface2_changed = Signal()
        self._bond2_bond_mode = "active-backup"
        self.bond2_bond_mode_changed = Signal()
        self._bond2_network_mode = "static"
        self.bond2_network_mode_changed = Signal()
        self._bond2_ip = ""
        self.bond2_ip_changed = Signal()
        self._bond2_netmask = "255.255.255.0"
        self.bond2_netmask_changed = Signal()
        self._bond2_gateway = ""
        self.bond2_gateway_changed = Signal()

        self._default_route_iface = ""
        self.default_route_iface_changed = Signal()

        self._ip = "192.168.10.10"
        self.ip_changed = Signal()

        self._vip = "192.168.10.100"
        self.vip_changed = Signal()

        self._network_mode = "dhcp"
        self.network_mode_changed = Signal()

        self._netmask = "255.255.255.0"
        self.netmask_changed = Signal()

        self._gateway = "192.168.10.1"
        self.gateway_changed = Signal()

        self._dns = "8.8.8.8"
        self.dns_changed = Signal()

        self._pod_cidr = "10.16.0.0/16"
        self.pod_cidr_changed = Signal()

        self._service_cidr = "10.96.0.0/12"
        self.service_cidr_changed = Signal()

        self._join_cidr = "100.64.0.0/16"
        self.join_cidr_changed = Signal()

        self._role = "server"
        self.role_changed = Signal()

        self._server_url = ""
        self.server_url_changed = Signal()

        self._token = ""
        self.token_changed = Signal()

        self._data_disk = "auto"
        self.data_disk_changed = Signal()

    def publish(self):
        """发布 DBus 对象。"""
        TaskContainer.set_namespace(VDI.namespace)
        DBus.publish_object(VDI.object_path, VdiInterface(self))
        DBus.register_service(VDI.service_name)

    @staticmethod
    def _coerce_bool(value):
        """将 D-Bus/kickstart 传入的布尔值统一为 Python bool。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "on")
        return bool(value)

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        self._mode = value
        self.mode_changed.emit()
        log.debug("VDI Network Mode is set to '%s'.", value)

    @property
    def interface(self):
        return self._interface

    @interface.setter
    def interface(self, value):
        self._interface = value
        self.interface_changed.emit()
        log.debug("VDI Network Interface is set to '%s'.", value)

    @property
    def interface2(self):
        return self._interface2

    @interface2.setter
    def interface2(self, value):
        self._interface2 = value
        self.interface2_changed.emit()
        log.debug("VDI Network Interface2 is set to '%s'.", value)

    @property
    def bond_mode(self):
        return self._bond_mode

    @bond_mode.setter
    def bond_mode(self, value):
        self._bond_mode = value
        self.bond_mode_changed.emit()
        log.debug("VDI Network Bond Mode is set to '%s'.", value)

    # ---- bond1 ----
    @property
    def bond1_enabled(self):
        return self._bond1_enabled

    @bond1_enabled.setter
    def bond1_enabled(self, value):
        self._bond1_enabled = self._coerce_bool(value)
        self.bond1_enabled_changed.emit()
        log.debug("VDI Bond1 Enabled is set to '%s'.", self._bond1_enabled)

    @property
    def bond1_interface(self):
        return self._bond1_interface

    @bond1_interface.setter
    def bond1_interface(self, value):
        self._bond1_interface = value
        self.bond1_interface_changed.emit()
        log.debug("VDI Bond1 Interface is set to '%s'.", value)

    @property
    def bond1_interface2(self):
        return self._bond1_interface2

    @bond1_interface2.setter
    def bond1_interface2(self, value):
        self._bond1_interface2 = value
        self.bond1_interface2_changed.emit()
        log.debug("VDI Bond1 Interface2 is set to '%s'.", value)

    @property
    def bond1_bond_mode(self):
        return self._bond1_bond_mode

    @bond1_bond_mode.setter
    def bond1_bond_mode(self, value):
        self._bond1_bond_mode = value
        self.bond1_bond_mode_changed.emit()
        log.debug("VDI Bond1 BondMode is set to '%s'.", value)

    @property
    def bond1_network_mode(self):
        return self._bond1_network_mode

    @bond1_network_mode.setter
    def bond1_network_mode(self, value):
        self._bond1_network_mode = value
        self.bond1_network_mode_changed.emit()
        log.debug("VDI Bond1 NetworkMode is set to '%s'.", value)

    @property
    def bond1_ip(self):
        return self._bond1_ip

    @bond1_ip.setter
    def bond1_ip(self, value):
        self._bond1_ip = value
        self.bond1_ip_changed.emit()
        log.debug("VDI Bond1 IP is set to '%s'.", value)

    @property
    def bond1_netmask(self):
        return self._bond1_netmask

    @bond1_netmask.setter
    def bond1_netmask(self, value):
        self._bond1_netmask = value
        self.bond1_netmask_changed.emit()
        log.debug("VDI Bond1 Netmask is set to '%s'.", value)

    @property
    def bond1_gateway(self):
        return self._bond1_gateway

    @bond1_gateway.setter
    def bond1_gateway(self, value):
        self._bond1_gateway = value
        self.bond1_gateway_changed.emit()
        log.debug("VDI Bond1 Gateway is set to '%s'.", value)

    # ---- bond2 ----
    @property
    def bond2_enabled(self):
        return self._bond2_enabled

    @bond2_enabled.setter
    def bond2_enabled(self, value):
        self._bond2_enabled = self._coerce_bool(value)
        self.bond2_enabled_changed.emit()
        log.debug("VDI Bond2 Enabled is set to '%s'.", self._bond2_enabled)

    @property
    def bond2_interface(self):
        return self._bond2_interface

    @bond2_interface.setter
    def bond2_interface(self, value):
        self._bond2_interface = value
        self.bond2_interface_changed.emit()
        log.debug("VDI Bond2 Interface is set to '%s'.", value)

    @property
    def bond2_interface2(self):
        return self._bond2_interface2

    @bond2_interface2.setter
    def bond2_interface2(self, value):
        self._bond2_interface2 = value
        self.bond2_interface2_changed.emit()
        log.debug("VDI Bond2 Interface2 is set to '%s'.", value)

    @property
    def bond2_bond_mode(self):
        return self._bond2_bond_mode

    @bond2_bond_mode.setter
    def bond2_bond_mode(self, value):
        self._bond2_bond_mode = value
        self.bond2_bond_mode_changed.emit()
        log.debug("VDI Bond2 BondMode is set to '%s'.", value)

    @property
    def bond2_network_mode(self):
        return self._bond2_network_mode

    @bond2_network_mode.setter
    def bond2_network_mode(self, value):
        self._bond2_network_mode = value
        self.bond2_network_mode_changed.emit()
        log.debug("VDI Bond2 NetworkMode is set to '%s'.", value)

    @property
    def bond2_ip(self):
        return self._bond2_ip

    @bond2_ip.setter
    def bond2_ip(self, value):
        self._bond2_ip = value
        self.bond2_ip_changed.emit()
        log.debug("VDI Bond2 IP is set to '%s'.", value)

    @property
    def bond2_netmask(self):
        return self._bond2_netmask

    @bond2_netmask.setter
    def bond2_netmask(self, value):
        self._bond2_netmask = value
        self.bond2_netmask_changed.emit()
        log.debug("VDI Bond2 Netmask is set to '%s'.", value)

    @property
    def bond2_gateway(self):
        return self._bond2_gateway

    @bond2_gateway.setter
    def bond2_gateway(self, value):
        self._bond2_gateway = value
        self.bond2_gateway_changed.emit()
        log.debug("VDI Bond2 Gateway is set to '%s'.", value)

    @property
    def default_route_iface(self):
        return self._default_route_iface

    @default_route_iface.setter
    def default_route_iface(self, value):
        self._default_route_iface = value
        self.default_route_iface_changed.emit()
        log.debug("VDI DefaultRouteIface is set to '%s'.", value)

    @property
    def ip(self):
        return self._ip

    @ip.setter
    def ip(self, value):
        self._ip = value
        self.ip_changed.emit()
        log.debug("VDI IP is set to '%s'.", value)

    @property
    def vip(self):
        return self._vip

    @vip.setter
    def vip(self, value):
        self._vip = value
        self.vip_changed.emit()
        log.debug("VDI VIP is set to '%s'.", value)

    @property
    def network_mode(self):
        return self._network_mode

    @network_mode.setter
    def network_mode(self, value):
        self._network_mode = value
        self.network_mode_changed.emit()
        log.debug("VDI Network Mode is set to '%s'.", value)

    @property
    def netmask(self):
        return self._netmask

    @netmask.setter
    def netmask(self, value):
        self._netmask = value
        self.netmask_changed.emit()
        log.debug("VDI Netmask is set to '%s'.", value)

    @property
    def gateway(self):
        return self._gateway

    @gateway.setter
    def gateway(self, value):
        self._gateway = value
        self.gateway_changed.emit()
        log.debug("VDI Gateway is set to '%s'.", value)

    @property
    def dns(self):
        return self._dns

    @dns.setter
    def dns(self, value):
        self._dns = value
        self.dns_changed.emit()
        log.debug("VDI DNS is set to '%s'.", value)

    @property
    def pod_cidr(self):
        return self._pod_cidr

    @pod_cidr.setter
    def pod_cidr(self, value):
        self._pod_cidr = value
        self.pod_cidr_changed.emit()
        log.debug("VDI PodCidr is set to '%s'.", value)

    @property
    def service_cidr(self):
        return self._service_cidr

    @service_cidr.setter
    def service_cidr(self, value):
        self._service_cidr = value
        self.service_cidr_changed.emit()
        log.debug("VDI ServiceCidr is set to '%s'.", value)

    @property
    def join_cidr(self):
        return self._join_cidr

    @join_cidr.setter
    def join_cidr(self, value):
        self._join_cidr = value
        self.join_cidr_changed.emit()
        log.debug("VDI JoinCidr is set to '%s'.", value)

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, value):
        self._role = value
        self.role_changed.emit()
        log.debug("VDI Role is set to '%s'.", value)

    @property
    def server_url(self):
        return self._server_url

    @server_url.setter
    def server_url(self, value):
        self._server_url = value
        self.server_url_changed.emit()
        log.debug("VDI ServerUrl is set to '%s'.", value)

    @property
    def token(self):
        return self._token

    @token.setter
    def token(self, value):
        self._token = value
        self.token_changed.emit()
        log.debug("VDI Token is set to '%s'.", value)

    @property
    def data_disk(self):
        return self._data_disk

    @data_disk.setter
    def data_disk(self, value):
        self._data_disk = value
        self.data_disk_changed.emit()
        log.debug("VDI DataDisk is set to '%s'.", value)

    @property
    def kickstart_specification(self):
        return VdiKickstartSpecification

    def process_kickstart(self, data):
        """从 Kickstart 数据中读取配置。"""
        addon_data = data.addons.vdi
        self.mode = addon_data.mode
        self.interface = addon_data.interface
        self.interface2 = addon_data.interface2
        self.bond_mode = addon_data.bond_mode
        self.bond1_enabled = addon_data.bond1_enabled
        self.bond1_interface = addon_data.bond1_interface
        self.bond1_interface2 = addon_data.bond1_interface2
        self.bond1_bond_mode = addon_data.bond1_bond_mode
        self.bond1_network_mode = addon_data.bond1_network_mode
        self.bond1_ip = addon_data.bond1_ip
        self.bond1_netmask = addon_data.bond1_netmask
        self.bond1_gateway = addon_data.bond1_gateway
        self.bond2_enabled = addon_data.bond2_enabled
        self.bond2_interface = addon_data.bond2_interface
        self.bond2_interface2 = addon_data.bond2_interface2
        self.bond2_bond_mode = addon_data.bond2_bond_mode
        self.bond2_network_mode = addon_data.bond2_network_mode
        self.bond2_ip = addon_data.bond2_ip
        self.bond2_netmask = addon_data.bond2_netmask
        self.bond2_gateway = addon_data.bond2_gateway
        self.default_route_iface = addon_data.default_route_iface
        self.ip = addon_data.ip
        self.netmask = addon_data.netmask
        self.gateway = addon_data.gateway
        self.dns = addon_data.dns
        self.vip = addon_data.vip
        self.network_mode = addon_data.network_mode
        self.pod_cidr = addon_data.pod_cidr
        self.service_cidr = addon_data.service_cidr
        self.join_cidr = addon_data.join_cidr
        self.role = addon_data.role
        self.server_url = addon_data.server_url
        self.token = addon_data.token
        self.data_disk = addon_data.data_disk

    def setup_kickstart(self, data):
        """将当前配置写回 Kickstart 数据。"""
        data.addons.vdi.mode = self.mode
        data.addons.vdi.interface = self.interface
        data.addons.vdi.interface2 = self.interface2
        data.addons.vdi.bond_mode = self.bond_mode
        data.addons.vdi.bond1_enabled = self.bond1_enabled
        data.addons.vdi.bond1_interface = self.bond1_interface
        data.addons.vdi.bond1_interface2 = self.bond1_interface2
        data.addons.vdi.bond1_bond_mode = self.bond1_bond_mode
        data.addons.vdi.bond1_network_mode = self.bond1_network_mode
        data.addons.vdi.bond1_ip = self.bond1_ip
        data.addons.vdi.bond1_netmask = self.bond1_netmask
        data.addons.vdi.bond1_gateway = self.bond1_gateway
        data.addons.vdi.bond2_enabled = self.bond2_enabled
        data.addons.vdi.bond2_interface = self.bond2_interface
        data.addons.vdi.bond2_interface2 = self.bond2_interface2
        data.addons.vdi.bond2_bond_mode = self.bond2_bond_mode
        data.addons.vdi.bond2_network_mode = self.bond2_network_mode
        data.addons.vdi.bond2_ip = self.bond2_ip
        data.addons.vdi.bond2_netmask = self.bond2_netmask
        data.addons.vdi.bond2_gateway = self.bond2_gateway
        data.addons.vdi.default_route_iface = self.default_route_iface
        data.addons.vdi.ip = self.ip
        data.addons.vdi.netmask = self.netmask
        data.addons.vdi.gateway = self.gateway
        data.addons.vdi.dns = self.dns
        data.addons.vdi.vip = self.vip
        data.addons.vdi.network_mode = self.network_mode
        data.addons.vdi.pod_cidr = self.pod_cidr
        data.addons.vdi.service_cidr = self.service_cidr
        data.addons.vdi.join_cidr = self.join_cidr
        data.addons.vdi.role = self.role
        data.addons.vdi.server_url = self.server_url
        data.addons.vdi.token = self.token
        data.addons.vdi.data_disk = self.data_disk

    def install_with_tasks(self):
        """返回安装任务列表。

        Anaconda 36 使用 task queue 机制驱动安装流程，
        addon 必须通过此方法注册 Task 对象，否则 task queue 为空，execute() 不会被调用。

        :return: 安装任务列表
        """
        return [
            VdiInstallationTask(
                sysroot=conf.target.system_root,
                mode=self.mode,
                interface=self.interface,
                interface2=self.interface2,
                bond_mode=self.bond_mode,
                ip=self.ip,
                netmask=self.netmask,
                gateway=self.gateway,
                dns=self.dns,
                pod_cidr=self.pod_cidr,
                service_cidr=self.service_cidr,
                join_cidr=self.join_cidr,
                vip=self.vip,
                network_mode=self.network_mode,
                role=self.role,
                server_url=self.server_url,
                token=self.token,
                data_disk=self.data_disk,
                bond1_enabled=self.bond1_enabled,
                bond1_interface=self.bond1_interface,
                bond1_interface2=self.bond1_interface2,
                bond1_bond_mode=self.bond1_bond_mode,
                bond1_network_mode=self.bond1_network_mode,
                bond1_ip=self.bond1_ip,
                bond1_netmask=self.bond1_netmask,
                bond1_gateway=self.bond1_gateway,
                bond2_enabled=self.bond2_enabled,
                bond2_interface=self.bond2_interface,
                bond2_interface2=self.bond2_interface2,
                bond2_bond_mode=self.bond2_bond_mode,
                bond2_network_mode=self.bond2_network_mode,
                bond2_ip=self.bond2_ip,
                bond2_netmask=self.bond2_netmask,
                bond2_gateway=self.bond2_gateway,
                default_route_iface=self.default_route_iface,
            )
        ]
