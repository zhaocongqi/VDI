"""VDI Addon DBus 常量定义（参考 com_redhat_kdump/constants.py）"""
from dasbus.identifier import DBusServiceIdentifier

from pyanaconda.core.dbus import DBus
from pyanaconda.modules.common.constants.namespaces import ADDONS_NAMESPACE

VDI_NAMESPACE = (
    *ADDONS_NAMESPACE,
    "Vdi",
)

VDI = DBusServiceIdentifier(
    namespace=VDI_NAMESPACE,
    message_bus=DBus,
)
