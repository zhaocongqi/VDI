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

    def publish(self):
        """发布 DBus 对象。"""
        TaskContainer.set_namespace(VDI.namespace)
        DBus.publish_object(VDI.object_path, VdiInterface(self))
        DBus.register_service(VDI.service_name)

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
    def kickstart_specification(self):
        return VdiKickstartSpecification

    def process_kickstart(self, data):
        """从 Kickstart 数据中读取配置。"""
        addon_data = data.addons.vdi
        self.mode = addon_data.mode
        self.interface = addon_data.interface
        self.interface2 = addon_data.interface2
        self.bond_mode = addon_data.bond_mode
        self.ip = addon_data.ip
        self.netmask = addon_data.netmask
        self.gateway = addon_data.gateway
        self.dns = addon_data.dns
        self.vip = addon_data.vip
        self.network_mode = addon_data.network_mode

    def setup_kickstart(self, data):
        """将当前配置写回 Kickstart 数据。"""
        data.addons.vdi.mode = self.mode
        data.addons.vdi.interface = self.interface
        data.addons.vdi.interface2 = self.interface2
        data.addons.vdi.bond_mode = self.bond_mode
        data.addons.vdi.ip = self.ip
        data.addons.vdi.netmask = self.netmask
        data.addons.vdi.gateway = self.gateway
        data.addons.vdi.dns = self.dns
        data.addons.vdi.vip = self.vip
        data.addons.vdi.network_mode = self.network_mode

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
                vip=self.vip,
                network_mode=self.network_mode,
            )
        ]
