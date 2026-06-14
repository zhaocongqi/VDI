"""加入集群配置界面（模式 2/3）

管理节点 (Mode 2): 输入 Master IP + install-key → 从 discovery /cp-join 获取控制面加入凭证
工作节点 (Mode 3): 输入 Master IP → 从 discovery /join-token 获取 worker join token
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
    """从首节点 discovery 服务获取集群信息"""
    url = f"http://{master_ip}:{DISCOVERY_PORT}/cluster-info"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=DISCOVERY_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning(f"从首节点获取集群信息失败: {e}")
        return None


def _fetch_join_token(master_ip):
    """从首节点 discovery 服务获取 worker join token"""
    url = f"http://{master_ip}:{DISCOVERY_PORT}/join-token"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=DISCOVERY_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.warning(f"获取 worker join token 失败: {e}")
        return None


def _fetch_cp_join(master_ip, install_key):
    """从首节点 discovery 服务获取 control-plane join 凭证"""
    url = f"http://{master_ip}:{DISCOVERY_PORT}/cp-join?key={install_key}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=DISCOVERY_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning("install-key 鉴权失败")
            return None
        raise
    except Exception as e:
        logger.warning(f"获取 control-plane join 凭证失败: {e}")
        return None


class JoinConfigScreen:
    """加入集群配置界面（管理节点/工作节点）"""

    def show(self, stdscr, mode):
        """收集加入集群配置参数

        Args:
            stdscr: curses 标准屏幕
            mode: 2=管理节点, 3=工作节点

        Returns:
            dict 或 None（用户取消）
        """
        config = {}
        is_control = mode == 2

        if is_control:
            msgbox(stdscr,
                   title="管理节点配置",
                   text="管理节点模式\n\n"
                        "此节点将安装 OS 并加入已有集群的控制面。\n"
                        "需要首节点已部署完成且 discovery 服务可达。\n\n"
                        "你需要提供:\n"
                        "  - 首节点 IP 地址\n"
                        "  - Install Key（首节点部署完成后显示）")
        else:
            msgbox(stdscr,
                   title="工作节点配置",
                   text="工作节点模式\n\n"
                        "此节点将安装 OS 并加入已有集群作为工作节点。\n"
                        "需要首节点已部署完成且 discovery 服务可达。\n\n"
                        "你只需要提供首节点 IP 地址。\n"
                        "集群信息和 join token 将自动获取。")

        # 首节点 IP
        while True:
            master_ip = inputbox(stdscr,
                                 title="加入集群配置",
                                 text="输入首节点 IP 地址:\n\n"
                                      "首节点必须已部署完成且 discovery 服务运行中。",
                                 default="")
            if master_ip is None:
                return None
            valid, msg = validate_ip(master_ip)
            if valid:
                config["master_ip"] = master_ip
                break
            msgbox(stdscr, "输入错误", f"IP 地址格式错误: {msg}")

        # 自动获取集群信息
        cluster_info = _fetch_cluster_info(master_ip)
        if cluster_info:
            config["vip"] = cluster_info.get("vip", "")
            config["pod_cidr"] = cluster_info.get("pod_cidr", "")
            config["svc_cidr"] = cluster_info.get("svc_cidr", "")
            config["k8s_version"] = cluster_info.get("k8s_version", "")
            config["vip_interface"] = cluster_info.get("vip_interface", "")

            msgbox(stdscr,
                   title="集群信息已获取",
                   text=f"成功从首节点获取集群信息:\n\n"
                        f"  VIP:        {config['vip']}\n"
                        f"  K8s 版本:   {config['k8s_version']}\n"
                        f"  Pod CIDR:   {config['pod_cidr']}\n"
                        f"  SVC CIDR:   {config['svc_cidr']}")
        else:
            msgbox(stdscr,
                   title="自动发现失败",
                   text="无法连接首节点 discovery 服务。\n\n"
                        "回退为手动输入。\n"
                        "请确认首节点已部署且端口 8090 可达。")
            vip = inputbox(stdscr,
                           title="加入集群配置",
                           text="输入集群 VIP (Kubernetes API 端点):",
                           default="192.168.220.100")
            if vip is None:
                return None
            config["vip"] = vip

        # 管理节点: 输入 install-key → 获取控制面加入凭证
        if is_control:
            install_key = inputbox(stdscr,
                                   title="管理节点配置",
                                   text="输入 Install Key:\n\n"
                                        "此 key 在首节点部署完成后显示，\n"
                                        "用于鉴权获取控制面加入凭证。",
                                   default="")
            if install_key is None:
                return None
            config["install_key"] = install_key

            cp_info = _fetch_cp_join(master_ip, install_key)
            if cp_info and cp_info.get("join_command"):
                config["join_command"] = cp_info.get("join_command", "")
                config["certificate_key"] = cp_info.get("certificate_key", "")
                config["join_method"] = "control-plane"

                msgbox(stdscr,
                       title="控制面凭证已获取",
                       text=f"成功获取控制面加入凭证。\n\n"
                            f"  Token: {cp_info.get('token', '')[:8]}...\n"
                            f"  Cert Key: {config['certificate_key'][:8]}...\n\n"
                            "重启后将自动加入控制面。")
            else:
                msgbox(stdscr,
                       title="获取控制面凭证失败",
                       text="无法获取控制面加入凭证。\n\n"
                            "可能原因:\n"
                            "  - Install Key 不正确\n"
                            "  - 首节点 discovery 服务不可达\n\n"
                            "请确认后重试。")
                return None

        # 工作节点: 获取 worker join token
        else:
            join_info = _fetch_join_token(master_ip)
            if join_info and join_info.get("join_command"):
                config["join_token"] = join_info.get("token", "")
                config["ca_cert_hash"] = join_info.get("ca_cert_hash", "")
                config["join_command"] = join_info.get("join_command", "")
                config["join_method"] = "worker"

                msgbox(stdscr,
                       title="Join Token 已获取",
                       text=f"Join token 已自动获取。\n\n"
                            f"  Token: {config['join_token'][:8]}...\n\n"
                            "重启后将自动加入集群。")
            else:
                msgbox(stdscr,
                       title="获取 Join Token 失败",
                       text="无法从首节点获取 join token。\n\n"
                            "请手动输入 join token。\n"
                            "在首节点执行: kubeadm token create --print-join-command")

                token = inputbox(stdscr,
                                 title="工作节点配置",
                                 text="输入 Join Token:\n\n"
                                      "在首节点执行:\n"
                                      "  kubeadm token create --print-join-command",
                                 default="")
                if token is None:
                    return None
                config["join_token"] = token
                config["join_method"] = "worker"

        logger.info(f"加入配置: master={master_ip}, mode={mode}, "
                    f"method={config.get('join_method')}, auto={cluster_info is not None}")
        return config
