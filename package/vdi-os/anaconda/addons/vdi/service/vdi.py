"""VDI Addon 服务实现（参考 com_redhat_kdump/service/kdump.py）"""
import logging

from pyanaconda.core.dbus import DBus
from pyanaconda.core.signal import Signal
from pyanaconda.modules.common.base import KickstartService
from pyanaconda.modules.common.containers import TaskContainer

from vdi.constants import VDI
from vdi.service.vdi_interface import VdiInterface
from vdi.service.kickstart import VdiKickstartSpecification

log = logging.getLogger(__name__)

__all__ = ["VdiService"]


class VdiService(KickstartService):
    """VDI Addon 服务：管理 VDI 管理网络配置状态。"""

    def __init__(self):
        super().__init__()
        self._ip = "192.168.10.10"
        self.ip_changed = Signal()

        self._vip = "192.168.10.100"
        self.vip_changed = Signal()

    def publish(self):
        """发布 DBus 对象。"""
        TaskContainer.set_namespace(VDI.namespace)
        DBus.publish_object(VDI.object_path, VdiInterface(self))
        DBus.register_service(VDI.service_name)

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
    def kickstart_specification(self):
        return VdiKickstartSpecification

    def process_kickstart(self, data):
        """从 Kickstart 数据中读取配置。"""
        addon_data = data.addons.vdi
        self.ip = addon_data.ip
        self.vip = addon_data.vip

    def setup_kickstart(self, data):
        """将当前配置写回 Kickstart 数据。"""
        data.addons.vdi.ip = self.ip
        data.addons.vdi.vip = self.vip
