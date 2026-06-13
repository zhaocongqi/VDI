"""部署进度界面

使用 curses 内建进度条组件，不依赖 whiptail --gauge 子进程。
部署步骤在后台线程执行，主线程持续刷新 UI，保证进度可视化。
"""
import os
import sys
import time
import threading
import logging
import curses
from widgets import ProgressBar

logger = logging.getLogger("vdi-installer")


# 部署步骤定义（按模式）
DEPLOY_STEPS = {
    1: [  # 全新安装
        ("System Init", "os-init"),
        ("Deploy K8s Cluster", "kubekey-deploy-k8s"),
        ("Deploy kube-vip", "kubevip-deploy"),
        ("Deploy Kube-OVN", "kubeovn-deploy"),
        ("Deploy Longhorn", "longhorn-deploy"),
        ("Deploy KubeVirt", "kubevirt-deploy"),
        ("Deploy kagent", "kagent-deploy"),
    ],
    2: [  # 追加部署
        ("System Init", "os-init"),
        ("Deploy K8s Cluster", "kubekey-deploy-k8s"),
        ("Deploy kube-vip", "kubevip-deploy"),
        ("Deploy Kube-OVN", "kubeovn-deploy"),
        ("Deploy Longhorn", "longhorn-deploy"),
        ("Deploy KubeVirt", "kubevirt-deploy"),
        ("Deploy kagent", "kagent-deploy"),
    ],
    3: [  # 添加节点
        ("Load Offline Images", "load-images"),
        ("Join Cluster", "join-cluster"),
        ("Verify Node Status", "verify-join"),
    ],
    4: [  # PXE 服务
        ("Get Join Token", "get-join-token"),
        ("Setup DHCP Service", "setup-dhcp"),
        ("Setup TFTP Service", "setup-tftp"),
        ("Setup HTTP Service", "setup-http"),
        ("Start PXE Service", "start-pxe"),
    ],
}


class ProgressScreen:
    """部署进度显示界面"""

    def __init__(self, mode):
        self.mode = mode
        self.steps = DEPLOY_STEPS.get(mode, [])
        self.log_file = "/var/log/vdi-deploy/installer.log"

    def run(self, stdscr, deploy_engine, mode, config):
        """执行部署并显示进度

        Args:
            stdscr: curses 标准屏幕
            deploy_engine: 部署引擎
            mode: 部署模式
            config: 配置字典

        Returns:
            True=成功, False=失败
        """
        total = len(self.steps)
        if total == 0:
            logger.warning(f"No deploy steps defined for mode {mode}")
            return True

        step_names = [name for name, _ in self.steps]
        pb = ProgressBar(stdscr, "Deploy Progress", step_names)

        # 用于线程间通信
        step_result = [None]  # 当前步骤的结果: True/False/None
        step_error = [""]     # 当前步骤的错误信息
        cancelled = [False]   # 用户取消标志

        try:
            for i, (step_name, step_id) in enumerate(self.steps):
                pb.update(i, step_name)

                # 在后台线程执行部署步骤
                step_result[0] = None
                step_error[0] = ""

                def _run_step():
                    try:
                        ok = deploy_engine.execute_step(step_id, mode, config)
                        step_result[0] = ok
                        if not ok:
                            # 读取步骤日志的最后几行作为错误信息
                            log_path = os.path.join(deploy_engine.log_dir, f"{step_id}.log")
                            try:
                                with open(log_path, "r") as f:
                                    lines = f.readlines()
                                    step_error[0] = "".join(lines[-10:]).strip()
                            except Exception:
                                step_error[0] = "(no detail)"
                    except Exception as e:
                        step_result[0] = False
                        step_error[0] = str(e)

                worker = threading.Thread(target=_run_step, daemon=True)
                worker.start()

                # 主线程：刷新 UI + 检测取消
                while worker.is_alive():
                    worker.join(timeout=0.3)
                    # 检测取消
                    pb.win.timeout(0)
                    try:
                        ch = pb.win.getch()
                        if ch == 27 or ch == ord('q'):
                            cancelled[0] = True
                            break
                    except curses.error:
                        pass
                    finally:
                        pb.win.timeout(-1)
                    # 刷新进度条显示
                    pb._draw()

                if cancelled[0]:
                    logger.info("用户取消部署")
                    pb.close()
                    return False

                worker.join()
                success = step_result[0]
                pb.set_step_result(i, success)

                if not success:
                    logger.error(f"Step failed: {step_name}")
                    # 标记剩余步骤跳过
                    for j in range(i + 1, total):
                        pb.step_names[j] = f"{self.steps[j][0]} (skipped)"
                    pb.finish(False)

                    # 等待用户按 Enter
                    while True:
                        ch = pb.win.getch()
                        if ch in (10, 13, curses.KEY_ENTER, 27, ord('q')):
                            break

                    pb.close()

                    from screens.error import ErrorScreen
                    error_detail = step_error[0][:500] if step_error[0] else "(see log)"
                    ErrorScreen(
                        f"Deploy failed: {step_name}\n\n"
                        f"Error output:\n{error_detail}\n\n"
                        f"Full log: {self.log_file}"
                    ).show(stdscr)
                    return False

            # 完成
            pb.update(total - 1, step_names[-1], 100)
            for i in range(total):
                pb.set_step_result(i, True)
            pb.finish(True)

            # 等待用户确认
            while True:
                ch = pb.win.getch()
                if ch in (10, 13, curses.KEY_ENTER, 27, ord('q')):
                    break

            pb.close()
            return True

        except Exception as e:
            logger.exception("Deploy process exception")
            try:
                pb.close()
            except Exception:
                pass
            from screens.error import ErrorScreen
            ErrorScreen(f"Deploy exception: {e}").show(stdscr)
            return False
