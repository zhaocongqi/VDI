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
        # bond1/bond2 业务网络绑定（可选，默认不启用）
        self.bond1_enabled = "false"
        self.bond1_interface = ""
        self.bond1_interface2 = ""
        self.bond1_bond_mode = "active-backup"
        self.bond1_network_mode = "static"
        self.bond1_ip = ""
        self.bond1_netmask = "255.255.255.0"
        self.bond1_gateway = ""
        self.bond2_enabled = "false"
        self.bond2_interface = ""
        self.bond2_interface2 = ""
        self.bond2_bond_mode = "active-backup"
        self.bond2_network_mode = "static"
        self.bond2_ip = ""
        self.bond2_netmask = "255.255.255.0"
        self.bond2_gateway = ""
        self.default_route_iface = ""
        self.ip = "192.168.10.10"
        self.netmask = "255.255.255.0"
        self.gateway = "192.168.10.1"
        self.dns = "8.8.8.8"
        self.vip = "192.168.10.100"
        self.network_mode = "dhcp"
        self.pod_cidr = "10.16.0.0/16"
        self.service_cidr = "10.96.0.0/12"
        self.role = "first-master"
        self.server_url = ""
        self.token = ""
        self.apps_disk = "auto"
        self.longhorn_disk = "auto"

    def __str__(self):
        """生成 Kickstart 文本表示。"""
        addon_str = "%addon vdi"
        addon_str += " --mode='%s'" % self.mode
        addon_str += " --interface='%s'" % self.interface
        if self.interface2:
            addon_str += " --interface2='%s'" % self.interface2
        addon_str += " --bond-mode='%s'" % self.bond_mode
        # bond1（仅在启用时输出，保证旧 ks.cfg 向后兼容）
        if self.bond1_enabled == "true":
            addon_str += " --bond1-enabled='true'"
            addon_str += " --bond1-interface='%s'" % self.bond1_interface
            if self.bond1_interface2:
                addon_str += " --bond1-interface2='%s'" % self.bond1_interface2
            addon_str += " --bond1-bond-mode='%s'" % self.bond1_bond_mode
            addon_str += " --bond1-network-mode='%s'" % self.bond1_network_mode
            addon_str += " --bond1-ip='%s'" % self.bond1_ip
            addon_str += " --bond1-netmask='%s'" % self.bond1_netmask
            if self.bond1_gateway:
                addon_str += " --bond1-gateway='%s'" % self.bond1_gateway
        if self.bond2_enabled == "true":
            addon_str += " --bond2-enabled='true'"
            addon_str += " --bond2-interface='%s'" % self.bond2_interface
            if self.bond2_interface2:
                addon_str += " --bond2-interface2='%s'" % self.bond2_interface2
            addon_str += " --bond2-bond-mode='%s'" % self.bond2_bond_mode
            addon_str += " --bond2-network-mode='%s'" % self.bond2_network_mode
            addon_str += " --bond2-ip='%s'" % self.bond2_ip
            addon_str += " --bond2-netmask='%s'" % self.bond2_netmask
            if self.bond2_gateway:
                addon_str += " --bond2-gateway='%s'" % self.bond2_gateway
        if self.default_route_iface:
            addon_str += " --default-route-iface='%s'" % self.default_route_iface
        addon_str += " --ip='%s'" % self.ip
        addon_str += " --netmask='%s'" % self.netmask
        addon_str += " --gateway='%s'" % self.gateway
        addon_str += " --dns='%s'" % self.dns
        addon_str += " --vip='%s'" % self.vip
        addon_str += " --network-mode='%s'" % self.network_mode
        addon_str += " --pod-cidr='%s'" % self.pod_cidr
        addon_str += " --service-cidr='%s'" % self.service_cidr
        addon_str += " --role='%s'" % self.role
        if self.server_url:
            addon_str += " --server-url='%s'" % self.server_url
        if self.token:
            addon_str += " --token='%s'" % self.token
        if self.apps_disk and self.apps_disk != "auto":
            addon_str += " --apps-disk='%s'" % self.apps_disk
        if self.longhorn_disk and self.longhorn_disk != "auto":
            addon_str += " --longhorn-disk='%s'" % self.longhorn_disk
        addon_str += "\n\n%end\n"
        return addon_str

    def handle_header(self, args, line_number=None):
        """处理 %addon vdi 行的参数。"""
        import argparse
        parser = argparse.ArgumentParser(conflict_handler='resolve')
        parser.add_argument("--mode", default="single")
        parser.add_argument("--interface", default="ens33")
        parser.add_argument("--interface2", default="")
        parser.add_argument("--bond-mode", default="active-backup")
        parser.add_argument("--bond1-enabled", default="false")
        parser.add_argument("--bond1-interface", default="")
        parser.add_argument("--bond1-interface2", default="")
        parser.add_argument("--bond1-bond-mode", default="active-backup")
        parser.add_argument("--bond1-network-mode", default="static")
        parser.add_argument("--bond1-ip", default="")
        parser.add_argument("--bond1-netmask", default="255.255.255.0")
        parser.add_argument("--bond1-gateway", default="")
        parser.add_argument("--bond2-enabled", default="false")
        parser.add_argument("--bond2-interface", default="")
        parser.add_argument("--bond2-interface2", default="")
        parser.add_argument("--bond2-bond-mode", default="active-backup")
        parser.add_argument("--bond2-network-mode", default="static")
        parser.add_argument("--bond2-ip", default="")
        parser.add_argument("--bond2-netmask", default="255.255.255.0")
        parser.add_argument("--bond2-gateway", default="")
        parser.add_argument("--default-route-iface", default="")
        parser.add_argument("--bond1-enabled", default="false")
        parser.add_argument("--bond1-interface", default="")
        parser.add_argument("--bond1-interface2", default="")
        parser.add_argument("--bond1-bond-mode", default="active-backup")
        parser.add_argument("--bond1-network-mode", default="static")
        parser.add_argument("--bond1-ip", default="")
        parser.add_argument("--bond1-netmask", default="255.255.255.0")
        parser.add_argument("--bond1-gateway", default="")
        parser.add_argument("--bond2-enabled", default="false")
        parser.add_argument("--bond2-interface", default="")
        parser.add_argument("--bond2-interface2", default="")
        parser.add_argument("--bond2-bond-mode", default="active-backup")
        parser.add_argument("--bond2-network-mode", default="static")
        parser.add_argument("--bond2-ip", default="")
        parser.add_argument("--bond2-netmask", default="255.255.255.0")
        parser.add_argument("--bond2-gateway", default="")
        parser.add_argument("--default-route-iface", default="")
        parser.add_argument("--ip", default="192.168.10.10")
        parser.add_argument("--netmask", default="255.255.255.0")
        parser.add_argument("--gateway", default="192.168.10.1")
        parser.add_argument("--dns", default="8.8.8.8")
        parser.add_argument("--vip", default="192.168.10.100")
        parser.add_argument("--network-mode", default="dhcp")
        parser.add_argument("--pod-cidr", default="10.16.0.0/16")
        parser.add_argument("--service-cidr", default="10.96.0.0/12")
        parser.add_argument("--role", default="first-master")
        parser.add_argument("--server-url", default="")
        parser.add_argument("--token", default="")
        parser.add_argument("--apps-disk", default="auto")
        parser.add_argument("--longhorn-disk", default="auto")

        parsed, _ = parser.parse_known_args(args)
        self.mode = parsed.mode
        self.interface = parsed.interface
        self.interface2 = parsed.interface2
        self.bond_mode = parsed.bond_mode
        self.bond1_enabled = parsed.bond1_enabled
        self.bond1_interface = parsed.bond1_interface
        self.bond1_interface2 = parsed.bond1_interface2
        self.bond1_bond_mode = parsed.bond1_bond_mode
        self.bond1_network_mode = parsed.bond1_network_mode
        self.bond1_ip = parsed.bond1_ip
        self.bond1_netmask = parsed.bond1_netmask
        self.bond1_gateway = parsed.bond1_gateway
        self.bond2_enabled = parsed.bond2_enabled
        self.bond2_interface = parsed.bond2_interface
        self.bond2_interface2 = parsed.bond2_interface2
        self.bond2_bond_mode = parsed.bond2_bond_mode
        self.bond2_network_mode = parsed.bond2_network_mode
        self.bond2_ip = parsed.bond2_ip
        self.bond2_netmask = parsed.bond2_netmask
        self.bond2_gateway = parsed.bond2_gateway
        self.default_route_iface = parsed.default_route_iface
        self.ip = parsed.ip
        self.netmask = parsed.netmask
        self.gateway = parsed.gateway
        self.dns = parsed.dns
        self.vip = parsed.vip
        self.network_mode = parsed.network_mode
        self.pod_cidr = parsed.pod_cidr
        self.service_cidr = parsed.service_cidr
        self.role = parsed.role
        self.server_url = parsed.server_url
        self.token = parsed.token
        self.apps_disk = parsed.apps_disk
        self.longhorn_disk = parsed.longhorn_disk

    def handle_line(self, line, line_number=None):
        """处理 %addon 段内部的行。"""
        pass


class VdiKickstartSpecification(KickstartSpecification):
    """VDI 服务的 Kickstart 规格声明。"""

    addons = {
        "vdi": VdiKickstartData,
    }
