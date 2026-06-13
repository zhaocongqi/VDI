"""PXE 配置界面（模式 4：PXE 服务）"""
import curses
import logging
from widgets import inputbox, msgbox
from utils.validator import validate_ip

logger = logging.getLogger("vdi-installer")


class PXEConfigScreen:
    """PXE 服务器配置界面"""

    def show(self, stdscr):
        """收集 PXE 配置参数

        Args:
            stdscr: curses 标准屏幕

        Returns:
            dict 或 None（用户取消）
        """
        config = {}

        msgbox(stdscr,
               title="PXE Service Configuration",
               text="PXE Network Install Mode\n\n"
                    "This node will be configured as a PXE server:\n"
                    "  - DHCP: Assign IPs to Worker nodes\n"
                    "  - TFTP: Provide network boot files\n"
                    "  - HTTP: Serve ISO content and install config\n\n"
                    "Master node must be deployed first.")

        # DHCP 起始 IP
        dhcp_start = inputbox(stdscr,
                              title="PXE Service Configuration",
                              text="Enter DHCP start IP:\n\n"
                                   "Worker nodes will get IPs starting from this address.",
                              default="192.168.220.200")
        if dhcp_start is None:
            return None
        config["dhcp_start"] = dhcp_start

        # DHCP 结束 IP
        dhcp_end = inputbox(stdscr,
                            title="PXE Service Configuration",
                            text="Enter DHCP end IP:\n\n"
                                 "DHCP address pool range.",
                            default="192.168.220.250")
        if dhcp_end is None:
            return None
        config["dhcp_end"] = dhcp_end

        # 预期 Worker 数量
        worker_count = inputbox(stdscr,
                                title="PXE Service Configuration",
                                text="Enter expected number of Worker nodes:\n\n"
                                     "Used to pre-allocate DHCP addresses and generate configs.",
                                default="3")
        if worker_count is None:
            return None
        config["worker_count"] = int(worker_count)

        # Worker 主机名前缀
        hostname_prefix = inputbox(stdscr,
                                   title="PXE Service Configuration",
                                   text="Enter Worker hostname prefix:\n\n"
                                        "Nodes will be named: vdi-worker-01, vdi-worker-02, ...",
                                   default="vdi-worker")
        if hostname_prefix is None:
            return None
        config["hostname_prefix"] = hostname_prefix

        logger.info(f"PXE 配置: dhcp={dhcp_start}-{dhcp_end}, workers={worker_count}")
        return config
