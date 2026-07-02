"""VDI Addon Kickstart 数据定义与规格声明（参考 com_redhat_kdump/service/kickstart.py）"""
import logging

from pyanaconda.core.kickstart import KickstartSpecification
from pyanaconda.core.kickstart.addon import AddonData

log = logging.getLogger(__name__)

__all__ = ["VdiKickstartSpecification"]


class VdiKickstartData(AddonData):
    """VDI Addon 的 Kickstart 数据模型。

    解析 ks.cfg 中的 %addon vdi 段，存储 VDI 管理网络参数。
    """

    def __init__(self):
        super().__init__()
        self.ip = "192.168.10.10"
        self.netmask = "255.255.255.0"
        self.gateway = "192.168.10.1"
        self.dns = "8.8.8.8"
        self.vip = "192.168.10.100"

    def __str__(self):
        """生成 Kickstart 文本表示。"""
        addon_str = "%addon vdi"
        addon_str += " --ip='%s'" % self.ip
        addon_str += " --netmask='%s'" % self.netmask
        addon_str += " --gateway='%s'" % self.gateway
        addon_str += " --dns='%s'" % self.dns
        addon_str += " --vip='%s'" % self.vip
        addon_str += "\n\n%end\n"
        return addon_str

    def handle_header(self, args, line_number=None):
        """处理 %addon vdi 行的参数。"""
        # 极简实现：暂不解析命令行参数，使用默认值
        pass

    def handle_line(self, line, line_number=None):
        """处理 %addon 段内部的行。"""
        pass


class VdiKickstartSpecification(KickstartSpecification):
    """VDI 服务的 Kickstart 规格声明。"""

    addons = {
        "vdi": VdiKickstartData,
    }
