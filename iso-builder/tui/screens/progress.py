"""部署进度界面"""
import os
import sys
import time
import subprocess
import threading
import logging
from utils.whiptail_wrapper import Whiptail

logger = logging.getLogger("vdi-installer")


# 部署步骤定义（按模式）
DEPLOY_STEPS = {
    1: [  # 全新安装
        ("系统初始化", "os-init"),
        ("部署 K8s 集群", "kubekey-deploy-k8s"),
        ("部署 kube-vip", "kubevip-deploy"),
        ("部署 Kube-OVN", "kubeovn-deploy"),
        ("部署 Longhorn", "longhorn-deploy"),
        ("部署 KubeVirt", "kubevirt-deploy"),
        ("部署 kagent", "kagent-deploy"),
    ],
    2: [  # 追加部署（同模式 1 但跳过 OS 安装）
        ("系统初始化", "os-init"),
        ("部署 K8s 集群", "kubekey-deploy-k8s"),
        ("部署 kube-vip", "kubevip-deploy"),
        ("部署 Kube-OVN", "kubeovn-deploy"),
        ("部署 Longhorn", "longhorn-deploy"),
        ("部署 KubeVirt", "kubevirt-deploy"),
        ("部署 kagent", "kagent-deploy"),
    ],
    3: [  # 添加节点
        ("加载离线镜像", "load-images"),
        ("加入集群", "join-cluster"),
        ("验证节点状态", "verify-join"),
    ],
    4: [  # PXE 服务
        ("获取 Join Token", "get-join-token"),
        ("配置 DHCP 服务", "setup-dhcp"),
        ("配置 TFTP 服务", "setup-tftp"),
        ("配置 HTTP 服务", "setup-http"),
        ("启动 PXE 服务", "start-pxe"),
    ],
}


class ProgressScreen:
    """部署进度显示界面

    使用 whiptail --gauge 显示进度条，每步完成后更新。
    """

    def __init__(self, mode):
        self.mode = mode
        self.steps = DEPLOY_STEPS.get(mode, [])
        self.current_step = 0
        self.log_file = "/var/log/vdi-deploy/installer.log"

    def run(self, deploy_engine, mode, config):
        """执行部署并显示进度

        返回: True=成功, False=失败
        """
        total = len(self.steps)
        if total == 0:
            logger.warning(f"模式 {mode} 无部署步骤定义")
            return True

        # 使用 gauge 进度条显示
        gauge_proc = self._start_gauge()

        try:
            for i, (step_name, step_id) in enumerate(self.steps):
                self.current_step = i
                percent = int((i / total) * 100)

                # 更新进度
                self._update_gauge(gauge_proc, percent, step_name, i, total)

                # 执行部署步骤
                logger.info(f"执行步骤 [{i+1}/{total}]: {step_name}")
                success = deploy_engine.execute_step(step_id, mode, config)

                if not success:
                    logger.error(f"步骤失败: {step_name}")
                    self._stop_gauge(gauge_proc)
                    from screens.error import ErrorScreen
                    ErrorScreen(
                        f"部署失败: {step_name}\n\n"
                        f"查看日志: {self.log_file}"
                    ).show()
                    return False

            # 完成
            self._update_gauge(gauge_proc, 100, "部署完成", total, total)
            self._stop_gauge(gauge_proc)
            return True

        except Exception as e:
            logger.exception("部署过程异常")
            self._stop_gauge(gauge_proc)
            return False

    def _start_gauge(self):
        """启动 whiptail gauge 进程"""
        proc = subprocess.Popen(
            ["whiptail",
             "--title", "部署进度",
             "--backtitle", "VDI 集群离线部署",
             "--gauge", "正在准备...", "20", "70", "0"],
            stdin=subprocess.PIPE,
            text=True
        )
        return proc

    def _update_gauge(self, proc, percent, current_name, step_idx, total):
        """更新 gauge 进度"""
        # 构建进度文本
        lines = [f"正在执行: {current_name}", ""]

        for i, (name, _) in enumerate(self.steps):
            if i < step_idx:
                lines.append(f"  ✓ {name}")
            elif i == step_idx:
                lines.append(f"  ● {name} ...")
            else:
                lines.append(f"  ○ {name}")

        lines.extend(["", f"日志: {self.log_file}"])

        # gauge 格式：XXX PERCENT\n 描述文本
        msg = f"XXX\n{percent}\n" + "\n".join(lines) + "\nXXX\n"
        try:
            proc.stdin.write(msg)
            proc.stdin.flush()
        except BrokenPipeError:
            pass

    def _stop_gauge(self, proc):
        """停止 gauge 进程"""
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:
            proc.terminate()
