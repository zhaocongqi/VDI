"""欢迎界面 - 选择部署模式"""
import logging
from utils.whiptail_wrapper import Whiptail

logger = logging.getLogger("vdi-installer")

# 部署模式定义
MODES = [
    ("1", "全新安装 - 安装 Ubuntu OS 并部署 VDI 集群"),
    ("2", "追加部署 - 在已有 OS 上部署 VDI 集群"),
    ("3", "添加节点 - 向现有集群添加 Worker 节点"),
    ("4", "PXE 服务 - 启动 PXE 服务器供其他节点网络安装"),
]


class WelcomeScreen:
    """欢迎界面，选择部署模式"""

    def show(self):
        """显示部署模式选择菜单

        返回: 模式编号 (1-4)，取消返回 None
        """
        wt = Whiptail(
            title="VDI 集群离线部署工具 v1.0",
            backtitle="VDI 集群离线部署",
            height=22, width=70
        )

        choice = wt.menu(
            "请选择部署模式：\n\n"
            "模式 1: 在裸机上安装 Ubuntu 系统，然后部署完整 VDI 集群（Master 角色）\n"
            "模式 2: 本机已安装 Ubuntu，直接部署 VDI 集群（Master 角色）\n"
            "模式 3: 将本机作为 Worker 节点加入已有的 VDI 集群\n"
            "模式 4: 将本机配置为 PXE 服务器，供其他节点通过网络安装",
            MODES
        )

        if choice is None:
            return None

        mode = int(choice)
        logger.info(f"用户选择部署模式: {mode} ({dict(MODES)[choice]})")
        return mode
