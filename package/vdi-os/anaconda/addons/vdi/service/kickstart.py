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
        self.mode = "single"
        self.interface = "ens33"
        self.interface2 = ""
        self.bond_mode = "active-backup"
        self.ip = "192.168.10.10"
        self.netmask = "255.255.255.0"
        self.gateway = "192.168.10.1"
        self.dns = "8.8.8.8"
        self.vip = "192.168.10.100"
        self.network_mode = "dhcp"

    def __str__(self):
        """生成 Kickstart 文本表示。"""
        addon_str = "%addon vdi"
        addon_str += " --mode='%s'" % self.mode
        addon_str += " --interface='%s'" % self.interface
        if self.interface2:
            addon_str += " --interface2='%s'" % self.interface2
        addon_str += " --bond-mode='%s'" % self.bond_mode
        addon_str += " --ip='%s'" % self.ip
        addon_str += " --netmask='%s'" % self.netmask
        addon_str += " --gateway='%s'" % self.gateway
        addon_str += " --dns='%s'" % self.dns
        addon_str += " --vip='%s'" % self.vip
        addon_str += " --network-mode='%s'" % self.network_mode
        addon_str += "\n\n%end\n"
        return addon_str

    def handle_header(self, args, line_number=None):
        """处理 %addon vdi 行的参数。"""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", default="single")
        parser.add_argument("--interface", default="ens33")
        parser.add_argument("--interface2", default="")
        parser.add_argument("--bond-mode", default="active-backup")
        parser.add_argument("--ip", default="192.168.10.10")
        parser.add_argument("--netmask", default="255.255.255.0")
        parser.add_argument("--gateway", default="192.168.10.1")
        parser.add_argument("--dns", default="8.8.8.8")
        parser.add_argument("--vip", default="192.168.10.100")
        parser.add_argument("--network-mode", default="dhcp")

        parsed, _ = parser.parse_known_args(args)
        self.mode = parsed.mode
        self.interface = parsed.interface
        self.interface2 = parsed.interface2
        self.bond_mode = parsed.bond_mode
        self.ip = parsed.ip
        self.netmask = parsed.netmask
        self.gateway = parsed.gateway
        self.dns = parsed.dns
        self.vip = parsed.vip
        self.network_mode = parsed.network_mode

    def handle_line(self, line, line_number=None):
        """处理 %addon 段内部的行。"""
        pass


class VdiKickstartSpecification(KickstartSpecification):
    """VDI 服务的 Kickstart 规格声明。"""

    addons = {
        "vdi": VdiKickstartData,
    }
