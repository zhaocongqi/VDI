"""部署完成界面"""
import logging
from utils.whiptail_wrapper import Whiptail

logger = logging.getLogger("vdi-installer")

MODE_NAMES = {
    1: "全新安装",
    2: "追加部署",
    3: "添加节点",
    4: "PXE 服务",
}


class CompleteScreen:
    """部署完成界面"""

    def __init__(self, mode, config):
        self.mode = mode
        self.config = config
        self.wt = Whiptail(title="✓ 部署完成", height=22, width=70)

    def show(self):
        """显示部署结果和下一步操作"""
        vip = self.config.get("vip", "N/A")

        if self.mode in (1, 2):
            # Master 节点部署完成
            message = (
                f"VDI 集群部署完成！\n\n"
                f"部署模式: {MODE_NAMES.get(self.mode, '')}\n"
                f"集群 VIP: {vip}\n"
                f"K8s 版本: {self.config.get('k8s_version', '')}\n"
                f"Pod CIDR: {self.config.get('pod_cidr', '')}\n\n"
                f"--- 验证命令 ---\n"
                f"  kubectl get nodes\n"
                f"  kubectl get pods -A\n"
                f"  kubectl get sc\n\n"
                f"--- 添加 Worker 节点 ---\n"
                f"在其他节点上使用本 ISO 启动，选择模式 3（添加节点）\n"
                f"或选择模式 4（PXE 服务）批量部署 Worker 节点。\n\n"
                f"--- 添加 Worker 命令（手动）---\n"
                f"  kubeadm token create --print-join-command\n\n"
                f"日志目录: /var/log/vdi-deploy/"
            )
        elif self.mode == 3:
            # Worker 加入完成
            message = (
                "Worker 节点已成功加入集群！\n\n"
                f"节点 IP: {self.config.get('node_ip', '')}\n"
                f"主机名: {self.config.get('hostname', '')}\n\n"
                f"在 Master 节点上验证:\n"
                f"  kubectl get nodes\n"
                f"  kubectl get pods -A | grep {self.config.get('hostname', '')}\n\n"
                f"日志目录: /var/log/vdi-deploy/"
            )
        elif self.mode == 4:
            # PXE 服务启动
            message = (
                "PXE 服务器已启动！\n\n"
                f"DHCP 范围: {self.config.get('dhcp_start', '')}-{self.config.get('dhcp_end', '')}\n"
                f"预期 Worker 数量: {self.config.get('worker_count', '')}\n\n"
                "Worker 节点部署步骤:\n"
                "1. 将 Worker 节点设置为 PXE 网络启动\n"
                "2. Worker 自动获取 IP 并开始安装\n"
                "3. 安装完成后自动加入集群\n\n"
                "监控 Worker 安装进度:\n"
                "  tail -f /var/log/vdi-deploy/pxe.log\n\n"
                "日志目录: /var/log/vdi-deploy/"
            )
        else:
            message = "部署完成。"

        self.wt.msgbox(message, height=22, width=70)
