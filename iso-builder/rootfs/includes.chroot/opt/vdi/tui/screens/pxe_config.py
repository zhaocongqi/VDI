"""PXE 配置界面（模式 4：PXE 服务）"""
import logging
from utils.whiptail_wrapper import Whiptail
from utils.validator import validate_ip

logger = logging.getLogger("vdi-installer")


class PXEConfigScreen:
    """PXE 服务器配置界面"""

    def show(self):
        """收集 PXE 配置参数

        返回: dict 或 None（用户取消）
        """
        wt = Whiptail(title="PXE Service Configuration", height=20, width=60)
        config = {}

        wt.msgbox(
            "PXE Network Install Mode\n\n"
            "This node will be configured as a PXE server:\n"
            "  - DHCP: Assign IPs to Worker nodes\n"
            "  - TFTP: Provide network boot files\n"
            "  - HTTP: Serve ISO content and install config\n\n"
            "Master node must be deployed first."
        )

        # DHCP 起始 IP
        dhcp_start = wt.inputbox(
            "Enter DHCP start IP:\n\n"
            "Worker nodes will get IPs starting from this address.",
            default="192.168.220.200"
        )
        if dhcp_start is None:
            return None
        config["dhcp_start"] = dhcp_start

        # DHCP 结束 IP
        dhcp_end = wt.inputbox(
            "Enter DHCP end IP:\n\n"
            "DHCP address pool range.",
            default="192.168.220.250"
        )
        if dhcp_end is None:
            return None
        config["dhcp_end"] = dhcp_end

        # 预期 Worker 数量
        worker_count = wt.inputbox(
            "Enter expected number of Worker nodes:\n\n"
            "Used to pre-allocate DHCP addresses and generate configs.",
            default="3"
        )
        if worker_count is None:
            return None
        config["worker_count"] = int(worker_count)

        # Worker 主机名前缀
        hostname_prefix = wt.inputbox(
            "Enter Worker hostname prefix:\n\n"
            "Nodes will be named: vdi-worker-01, vdi-worker-02, ...",
            default="vdi-worker"
        )
        if hostname_prefix is None:
            return None
        config["hostname_prefix"] = hostname_prefix

        logger.info(f"PXE 配置: dhcp={dhcp_start}-{dhcp_end}, workers={worker_count}")
        return config
