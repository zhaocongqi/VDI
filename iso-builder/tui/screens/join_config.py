"""Join 配置界面（模式 3：添加节点）"""
import logging
from utils.whiptail_wrapper import Whiptail
from utils.validator import validate_ip

logger = logging.getLogger("vdi-installer")


class JoinConfigScreen:
    """Worker 节点加入已有集群的配置界面"""

    def show(self):
        """收集 Join 配置参数

        返回: dict 或 None（用户取消）
        """
        wt = Whiptail(title="添加节点配置", height=20, width=60)
        config = {}

        wt.msgbox(
            "添加节点模式\n\n"
            "本机将作为 Worker 节点加入已有的 VDI 集群。\n"
            "请确保 Master 节点已部署完成并可访问。\n\n"
            "需要以下信息：\n"
            "  - Master 节点 IP 地址\n"
            "  - Join Token（在 Master 上执行 kubeadm token create 获取）"
        )

        # Master IP
        while True:
            master_ip = wt.inputbox(
                "请输入 Master 节点 IP 地址：\n\n"
                "Master 节点已部署完成，可以通过此 IP 访问。",
                default=""
            )
            if master_ip is None:
                return None
            valid, msg = validate_ip(master_ip)
            if valid:
                config["master_ip"] = master_ip
                break
            wt.msgbox(f"IP 地址格式错误: {msg}")

        # Master SSH 端口
        ssh_port = wt.inputbox(
            "请输入 Master SSH 端口：",
            default="22"
        )
        if ssh_port is None:
            return None
        config["master_ssh_port"] = ssh_port

        # Join Token
        token = wt.inputbox(
            "请输入 Join Token：\n\n"
            "在 Master 节点上执行以下命令获取：\n"
            "  kubeadm token create --print-join-command",
            default=""
        )
        if token is None:
            return None
        config["join_token"] = token

        # Join 方式选择
        join_method = wt.radiolist(
            "请选择 Join 方式：",
            [
                ("kk", "使用 KubeKey join（推荐）", "ON"),
                ("kubeadm", "使用 kubeadm join", "OFF"),
            ]
        )
        if join_method is None:
            return None
        config["join_method"] = join_method

        logger.info(f"Join 配置: master={config.get('master_ip')}, method={config.get('join_method')}")
        return config
