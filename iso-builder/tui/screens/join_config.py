"""Join 配置界面（模式 3：添加节点）"""
import curses
import logging
from widgets import inputbox, msgbox, radiolist
from utils.validator import validate_ip

logger = logging.getLogger("vdi-installer")


class JoinConfigScreen:
    """Worker 节点加入已有集群的配置界面"""

    def show(self, stdscr):
        """收集 Join 配置参数

        Args:
            stdscr: curses 标准屏幕

        Returns:
            dict 或 None（用户取消）
        """
        config = {}

        msgbox(stdscr,
               title="Join Node Configuration",
               text="Join Node Mode\n\n"
                    "This node will join an existing VDI cluster as a Worker.\n"
                    "Ensure the Master node is deployed and accessible.\n\n"
                    "Required information:\n"
                    "  - Master node IP address\n"
                    "  - Join Token (run 'kubeadm token create' on Master)")

        # Master IP
        while True:
            master_ip = inputbox(stdscr,
                                 title="Join Node Configuration",
                                 text="Enter Master node IP address:\n\n"
                                      "The Master node must be deployed and reachable.",
                                 default="")
            if master_ip is None:
                return None
            valid, msg = validate_ip(master_ip)
            if valid:
                config["master_ip"] = master_ip
                break
            msgbox(stdscr, "Invalid Input", f"Invalid IP address: {msg}")

        # Master SSH 端口
        ssh_port = inputbox(stdscr,
                            title="Join Node Configuration",
                            text="Enter Master SSH port:",
                            default="22")
        if ssh_port is None:
            return None
        config["master_ssh_port"] = ssh_port

        # Join Token
        token = inputbox(stdscr,
                         title="Join Node Configuration",
                         text="Enter Join Token:\n\n"
                              "Get it from Master node:\n"
                              "  kubeadm token create --print-join-command",
                         default="")
        if token is None:
            return None
        config["join_token"] = token

        # Join 方式选择
        join_method = radiolist(stdscr,
                                title="Join Node Configuration",
                                text="Select join method:",
                                items=[
                                    ("kk", "KubeKey join (recommended)", "ON"),
                                    ("kubeadm", "kubeadm join", "OFF"),
                                ])
        if join_method is None:
            return None
        config["join_method"] = join_method

        logger.info(f"Join 配置: master={config.get('master_ip')}, method={config.get('join_method')}")
        return config
