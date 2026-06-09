"""集群配置界面（模式 1/2/4）"""
import logging
from utils.whiptail_wrapper import Whiptail
from utils.validator import validate_ip, validate_cidr

logger = logging.getLogger("vdi-installer")


class ClusterConfigScreen:
    """集群配置界面"""

    def show(self):
        """收集集群配置参数

        返回: dict 或 None（用户取消）
        """
        wt = Whiptail(title="Cluster Configuration", height=20, width=60)
        config = {}

        # 节点角色
        role = wt.radiolist(
            "Select this node role:",
            [
                ("master", "Master (control plane + workload)", "ON"),
                ("worker", "Worker (workload only)", "OFF"),
            ]
        )
        if role is None:
            return None
        config["role"] = role

        # VIP 地址
        while True:
            vip = wt.inputbox(
                "Enter kube-vip virtual IP address:\n\n"
                "This IP will be the Kubernetes API Server endpoint.\n"
                "All nodes and clients access the cluster via this IP.",
                default="192.168.220.100"
            )
            if vip is None:
                return None
            valid, msg = validate_ip(vip)
            if valid:
                config["vip"] = vip
                break
            wt.msgbox(f"Invalid VIP format: {msg}")

        # VIP 网卡
        default_iface = self._detect_interface()
        iface = wt.inputbox(
            "Enter network interface for VIP binding:",
            default=default_iface
        )
        if iface is None:
            return None
        config["vip_interface"] = iface

        # Pod CIDR
        while True:
            pod_cidr = wt.inputbox(
                "Enter Pod CIDR:",
                default="10.16.0.0/16"
            )
            if pod_cidr is None:
                return None
            valid, msg = validate_cidr(pod_cidr)
            if valid:
                config["pod_cidr"] = pod_cidr
                break
            wt.msgbox(f"Invalid CIDR format: {msg}")

        # Service CIDR
        while True:
            svc_cidr = wt.inputbox(
                "Enter Service CIDR:",
                default="10.96.0.0/12"
            )
            if svc_cidr is None:
                return None
            valid, msg = validate_cidr(svc_cidr)
            if valid:
                config["svc_cidr"] = svc_cidr
                break
            wt.msgbox(f"Invalid CIDR format: {msg}")

        # K8s 版本
        k8s_version = wt.inputbox(
            "Enter Kubernetes version:",
            default="v1.34.3"
        )
        if k8s_version is None:
            return None
        config["k8s_version"] = k8s_version

        logger.info(f"集群配置: {config}")
        return config

    def _detect_interface(self):
        """自动检测主网络接口"""
        import subprocess
        try:
            result = subprocess.run(
                ["ip", "-json", "route", "show", "default"],
                capture_output=True, text=True
            )
            import json
            data = json.loads(result.stdout)
            return data[0].get("dev", "ens160")
        except Exception:
            return "ens160"
