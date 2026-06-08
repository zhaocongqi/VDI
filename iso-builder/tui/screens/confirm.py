"""配置确认界面"""
import logging
from utils.whiptail_wrapper import Whiptail

logger = logging.getLogger("vdi-installer")

MODE_NAMES = {
    1: "全新安装（安装 OS + 部署 VDI 集群）",
    2: "追加部署（在已有 OS 上部署 VDI 集群）",
    3: "添加节点（Worker 加入已有集群）",
    4: "PXE 服务（启动 PXE 服务器）",
}


class ConfirmScreen:
    """配置确认界面"""

    def __init__(self, config):
        self.config = config
        self.wt = Whiptail(title="配置确认", height=25, width=70)

    def show(self):
        """显示配置摘要并请求确认

        返回: True=确认, False=取消
        """
        mode = self.config.get("mode", "未知")
        lines = [
            f"部署模式: {MODE_NAMES.get(mode, mode)}",
            "",
            "--- 网络配置 ---",
            f"  主机名:       {self.config.get('hostname', '-')}",
            f"  本机 IP:      {self.config.get('node_ip', '-')}/{self.config.get('netmask', '24')}",
            f"  网关:         {self.config.get('gateway', '-')}",
            f"  DNS:          {self.config.get('dns', '-')}",
        ]

        if mode in (1, 2, 4):
            lines.extend([
                "",
                "--- 集群配置 ---",
                f"  节点角色:     {self.config.get('role', '-')}",
                f"  VIP:          {self.config.get('vip', '-')}",
                f"  VIP 接口:     {self.config.get('vip_interface', '-')}",
                f"  Pod CIDR:     {self.config.get('pod_cidr', '-')}",
                f"  Service CIDR: {self.config.get('svc_cidr', '-')}",
                f"  K8s 版本:     {self.config.get('k8s_version', '-')}",
            ])

        if mode in (1, 2):
            lines.extend([
                "",
                "--- 存储配置 ---",
                f"  Longhorn 磁盘: {self.config.get('longhorn_disk', '-')}",
                f"  数据目录:      {self.config.get('longhorn_data_dir', '-')}",
                f"  副本数:        {self.config.get('longhorn_replicas', '3')}",
            ])

        if mode == 3:
            lines.extend([
                "",
                "--- Join 配置 ---",
                f"  Master IP:    {self.config.get('master_ip', '-')}",
                f"  Join 方式:    {self.config.get('join_method', '-')}",
            ])

        if mode == 4:
            lines.extend([
                "",
                "--- PXE 配置 ---",
                f"  DHCP 范围:    {self.config.get('dhcp_start', '-')}-{self.config.get('dhcp_end', '-')}",
                f"  Worker 数量:  {self.config.get('worker_count', '-')}",
            ])

        lines.extend([
            "",
            "离线资源: " + (
                "已检测到 (/cdrom/offline)" if self.config.get("offline_available") else "未检测到"
            ),
            "",
            "确认以上配置无误后，将开始自动部署。",
        ])

        message = "\n".join(lines)
        return self.wt.yesno(message, height=25, width=70)
