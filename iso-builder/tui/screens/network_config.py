"""网络配置界面"""
import logging
from utils.whiptail_wrapper import Whiptail
from utils.validator import validate_ip, validate_cidr, validate_hostname

logger = logging.getLogger("vdi-installer")


class NetworkConfigScreen:
    """网络配置界面（所有模式共用）"""

    def show(self):
        """收集网络配置参数

        返回: dict 或 None（用户取消）
        """
        wt = Whiptail(title="Network Configuration", height=20, width=60)
        config = {}

        # 尝试自动检测当前 IP
        default_ip = self._detect_ip()

        # 本机 IP 地址
        while True:
            ip = wt.inputbox(
                "Enter this node IP address:\n\n"
                "This IP will be used for cluster communication\n"
                "and API Server access.",
                default=default_ip
            )
            if ip is None:
                return None
            valid, msg = validate_ip(ip)
            if valid:
                config["node_ip"] = ip
                break
            wt.msgbox(f"Invalid IP address: {msg}\n\nPlease try again.")

        # 子网掩码/前缀
        netmask = wt.inputbox(
            "Enter subnet mask (CIDR prefix length):\n\n"
            "Example: 24 means 255.255.255.0",
            default="24"
        )
        if netmask is None:
            return None
        config["netmask"] = netmask

        # 网关
        default_gw = self._detect_gateway()
        gateway = wt.inputbox(
            "Enter gateway address:",
            default=default_gw
        )
        if gateway is None:
            return None
        valid, msg = validate_ip(gateway)
        if not valid:
            wt.msgbox(f"Invalid gateway: {msg}")
            # 允许继续，网关可能在后续配置
        config["gateway"] = gateway

        # DNS
        dns = wt.inputbox(
            "Enter DNS server address:\n\n"
            "In offline mode, use gateway or internal DNS.",
            default=gateway
        )
        if dns is None:
            return None
        config["dns"] = dns

        # 主机名
        hostname = wt.inputbox(
            "Enter hostname:",
            default="vdi-node-01"
        )
        if hostname is None:
            return None
        valid, msg = validate_hostname(hostname)
        if not valid:
            wt.msgbox(f"Invalid hostname: {msg}\nUsing default: vdi-node-01")
            hostname = "vdi-node-01"
        config["hostname"] = hostname

        logger.info(f"网络配置: {config}")
        return config

    def _detect_ip(self):
        """自动检测本机 IP"""
        import subprocess
        try:
            result = subprocess.run(
                ["ip", "-json", "route", "get", "1.1.1.1"],
                capture_output=True, text=True
            )
            import json
            data = json.loads(result.stdout)
            return data[0].get("prefsrc", "")
        except Exception:
            return ""

    def _detect_gateway(self):
        """自动检测默认网关"""
        import subprocess
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True
            )
            # default via 192.168.220.2 dev ens160
            parts = result.stdout.strip().split()
            if "via" in parts:
                return parts[parts.index("via") + 1]
        except Exception:
            pass
        return ""
