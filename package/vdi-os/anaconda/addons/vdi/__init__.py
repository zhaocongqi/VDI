import ipaddress

from pyanaconda.addons import AnacondaAddon


class VdiAddon(AnacondaAddon):
    """VDI 平台定制化参数注册模型"""
    def __init__(self):
        super().__init__()
        self.interface = ""
        self.method = "static"
        self.ip = "192.168.10.10"
        self.netmask = "255.255.255.0"
        self.gateway = "192.168.10.1"
        self.dns = "8.8.8.8"
        self.vip = "192.168.10.100"

    def execute(self, storage, ksdata, instClass):
        if self.method == "static":
            try:
                ipaddress.ip_address(self.ip)
                ipaddress.ip_address(self.gateway)
                ipaddress.ip_address(self.vip)
            except ValueError as e:
                raise ValueError(f"Invalid IP address configuration: {e}")
