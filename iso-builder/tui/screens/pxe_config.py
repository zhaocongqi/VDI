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
        wt = Whiptail(title="PXE 服务配置", height=20, width=60)
        config = {}

        wt.msgbox(
            "PXE 网络安装模式\n\n"
            "本机将配置为 PXE 服务器，提供以下服务：\n"
            "  - DHCP：为 Worker 节点分配 IP\n"
            "  - TFTP：提供网络引导文件\n"
            "  - HTTP：提供 ISO 内容和安装配置\n\n"
            "Master 节点必须已部署完成。"
        )

        # DHCP 起始 IP
        dhcp_start = wt.inputbox(
            "请输入 DHCP 分配起始 IP：\n\n"
            "Worker 节点将从此 IP 开始自动分配。",
            default="192.168.220.200"
        )
        if dhcp_start is None:
            return None
        config["dhcp_start"] = dhcp_start

        # DHCP 结束 IP
        dhcp_end = wt.inputbox(
            "请输入 DHCP 分配结束 IP：\n\n"
            "DHCP 地址池范围。",
            default="192.168.220.250"
        )
        if dhcp_end is None:
            return None
        config["dhcp_end"] = dhcp_end

        # 预期 Worker 数量
        worker_count = wt.inputbox(
            "请输入预期 Worker 节点数量：\n\n"
            "用于预分配 DHCP 地址和生成配置。",
            default="3"
        )
        if worker_count is None:
            return None
        config["worker_count"] = int(worker_count)

        # Worker 主机名前缀
        hostname_prefix = wt.inputbox(
            "请输入 Worker 节点主机名前缀：\n\n"
            "节点将命名为 vdi-worker-01, vdi-worker-02, ...",
            default="vdi-worker"
        )
        if hostname_prefix is None:
            return None
        config["hostname_prefix"] = hostname_prefix

        logger.info(f"PXE 配置: dhcp={dhcp_start}-{dhcp_end}, workers={worker_count}")
        return config
