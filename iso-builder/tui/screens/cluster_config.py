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
        wt = Whiptail(title="集群配置", height=20, width=60)
        config = {}

        # 节点角色
        role = wt.radiolist(
            "请选择本节点角色：",
            [
                ("master", "Master 节点（控制平面 + 工作负载）", "ON"),
                ("worker", "Worker 节点（仅工作负载）", "OFF"),
            ]
        )
        if role is None:
            return None
        config["role"] = role

        # VIP 地址
        while True:
            vip = wt.inputbox(
                "请输入 kube-vip 虚拟 IP 地址：\n\n"
                "此 IP 将作为 Kubernetes API Server 的入口，\n"
                "所有节点和客户端通过此 IP 访问集群。",
                default="192.168.220.100"
            )
            if vip is None:
                return None
            valid, msg = validate_ip(vip)
            if valid:
                config["vip"] = vip
                break
            wt.msgbox(f"VIP 格式错误: {msg}")

        # VIP 网卡
        default_iface = self._detect_interface()
        iface = wt.inputbox(
            "请输入 VIP 绑定的网络接口名：",
            default=default_iface
        )
        if iface is None:
            return None
        config["vip_interface"] = iface

        # Pod CIDR
        while True:
            pod_cidr = wt.inputbox(
                "请输入 Pod CIDR：",
                default="10.16.0.0/16"
            )
            if pod_cidr is None:
                return None
            valid, msg = validate_cidr(pod_cidr)
            if valid:
                config["pod_cidr"] = pod_cidr
                break
            wt.msgbox(f"CIDR 格式错误: {msg}")

        # Service CIDR
        while True:
            svc_cidr = wt.inputbox(
                "请输入 Service CIDR：",
                default="10.96.0.0/12"
            )
            if svc_cidr is None:
                return None
            valid, msg = validate_cidr(svc_cidr)
            if valid:
                config["svc_cidr"] = svc_cidr
                break
            wt.msgbox(f"CIDR 格式错误: {msg}")

        # K8s 版本
        k8s_version = wt.inputbox(
            "请输入 Kubernetes 版本：",
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
