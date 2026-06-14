"""Join 配置界面（模式 2：Worker 节点）

Worker 只需输入 Master IP，其余信息（VIP、K8s 版本、join token 等）
自动从 Master 的 discovery 服务获取。获取失败时回退为手动输入。
"""
import json
import logging
import urllib.request
import urllib.error
from widgets import inputbox, msgbox
from utils.validator import validate_ip

logger = logging.getLogger("vdi-installer")

DISCOVERY_PORT = 8090
DISCOVERY_TIMEOUT = 5


def _fetch_cluster_info(master_ip):
    """从 Master discovery 服务获取集群信息

    Returns:
        dict 或 None（获取失败）
    """
    url = f"http://{master_ip}:{DISCOVERY_PORT}/cluster-info"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=DISCOVERY_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning(f"从 Master 获取集群信息失败: {e}")
        return None


def _fetch_join_token(master_ip):
    """从 Master discovery 服务获取 worker join token

    Returns:
        dict 或 None（获取失败）
    """
    url = f"http://{master_ip}:{DISCOVERY_PORT}/join-token"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=DISCOVERY_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning(f"从 Master 获取 join token 失败: {e}")
        return None


class JoinConfigScreen:
    """Worker 节点加入已有集群的配置界面"""

    def show(self, stdscr):
        """收集 Join 配置参数

        只需输入 Master IP，自动拉取其余信息。

        Args:
            stdscr: curses 标准屏幕

        Returns:
            dict 或 None（用户取消）
        """
        config = {}

        msgbox(stdscr,
               title="Worker Node Configuration",
               text="Worker Node Mode\n\n"
                    "This node will be installed and join an existing VDI cluster.\n"
                    "Ensure the Master node is deployed and its discovery\n"
                    "service is accessible on port 8090.\n\n"
                    "You only need to provide the Master node IP.\n"
                    "Cluster info and join token will be fetched automatically.")

        # Master IP
        while True:
            master_ip = inputbox(stdscr,
                                 title="Worker Node Configuration",
                                 text="Enter Master node IP address:\n\n"
                                      "The Master must be deployed with discovery service running.",
                                 default="")
            if master_ip is None:
                return None
            valid, msg = validate_ip(master_ip)
            if valid:
                config["master_ip"] = master_ip
                break
            msgbox(stdscr, "Invalid Input", f"Invalid IP address: {msg}")

        # 自动从 Master 获取集群信息
        cluster_info = _fetch_cluster_info(master_ip)
        if cluster_info:
            config["vip"] = cluster_info.get("vip", "")
            config["pod_cidr"] = cluster_info.get("pod_cidr", "")
            config["svc_cidr"] = cluster_info.get("svc_cidr", "")
            config["k8s_version"] = cluster_info.get("k8s_version", "")
            config["vip_interface"] = cluster_info.get("vip_interface", "")

            msgbox(stdscr,
                   title="Cluster Info Fetched",
                   text=f"Successfully fetched cluster info from Master:\n\n"
                        f"  VIP:        {config['vip']}\n"
                        f"  K8s Version:{config['k8s_version']}\n"
                        f"  Pod CIDR:   {config['pod_cidr']}\n"
                        f"  SVC CIDR:   {config['svc_cidr']}")
        else:
            msgbox(stdscr,
                   title="Auto Discovery Failed",
                   text="Could not reach Master discovery service.\n\n"
                        "Falling back to manual input.\n"
                        "Check that Master is deployed and port 8090 is reachable.")

            # 手动回退：VIP
            vip = inputbox(stdscr,
                           title="Worker Node Configuration",
                           text="Enter Master VIP (Kubernetes API endpoint):",
                           default="192.168.220.100")
            if vip is None:
                return None
            config["vip"] = vip

        # 自动获取 join token
        join_info = _fetch_join_token(master_ip)
        if join_info and join_info.get("join_command"):
            config["join_token"] = join_info.get("token", "")
            config["ca_cert_hash"] = join_info.get("ca_cert_hash", "")
            config["join_command"] = join_info.get("join_command", "")
            config["join_method"] = "kubeadm"

            msgbox(stdscr,
                   title="Join Token Fetched",
                   text=f"Join token obtained automatically.\n\n"
                        f"  Token: {config['join_token'][:8]}...\n\n"
                        "The node will join the cluster on the next boot.")
        else:
            msgbox(stdscr,
                   title="Join Token Fetch Failed",
                   text="Could not fetch join token from Master.\n\n"
                        "Please enter the join token manually.\n"
                        "Get it from Master: kubeadm token create --print-join-command")

            token = inputbox(stdscr,
                             title="Worker Node Configuration",
                             text="Enter Join Token:\n\n"
                                  "Get it from Master node:\n"
                                  "  kubeadm token create --print-join-command",
                             default="")
            if token is None:
                return None
            config["join_token"] = token
            config["join_method"] = "kubeadm"

        logger.info(f"Worker 配置: master={master_ip}, method={config.get('join_method')}, "
                    f"auto={cluster_info is not None}")
        return config
