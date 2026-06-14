"""部署进度界面

使用 curses 内建进度条组件，不依赖 whiptail --gauge 子进程。
部署步骤在后台线程执行，主线程持续刷新 UI（含实时日志面板）。
步骤失败后支持 retry/skip/exit（消费 ErrorScreen 返回值）。
"""
import os
import sys
import time
import threading
import logging
import curses
from widgets import ProgressBar
from screens.error import ErrorScreen

logger = logging.getLogger("vdi-installer")


# 部署步骤定义（按模式）
# 所有模式都走两阶段：
#   Phase 1 (Live 环境): os-install → 重启
#   Phase 2 (硬盘环境): os-init → 组件部署（由 _resume_deploy 触发）

# Phase 1: Live 环境装机步骤（所有模式相同）
DEPLOY_STEPS_PHASE1 = {
    1: [
        ("Install OS to Disk", "os-install"),
    ],
    2: [
        ("Install OS to Disk", "os-install"),
    ],
}

# Phase 2: VDI 部署步骤（重启后从硬盘执行）
DEPLOY_STEPS_PHASE2 = {
    1: [  # Master: 部署完整集群 + 启动发现服务
        ("System Init", "os-init"),
        ("Deploy K8s Cluster", "kubekey-deploy-k8s"),
        ("Deploy kube-vip", "kubevip-deploy"),
        ("Deploy Kube-OVN", "kubeovn-deploy"),
        ("Deploy Longhorn", "longhorn-deploy"),
        ("Deploy KubeVirt", "kubevirt-deploy"),
        ("Deploy kagent", "kagent-deploy"),
        ("Enable Discovery Service", "enable-discovery"),
    ],
    2: [  # Worker: 加入集群
        ("System Init", "os-init"),
        ("Load Offline Images", "load-images"),
        ("Join Cluster", "join-cluster"),
        ("Verify Node Status", "verify-join"),
    ],
}

# 兼容旧接口
DEPLOY_STEPS = DEPLOY_STEPS_PHASE2


class ProgressScreen:
    """部署进度显示界面"""

    def __init__(self, mode, phase2=False):
        """初始化

        Args:
            mode: 部署模式 (1=Master, 2=Worker)
            phase2: True 表示 Phase 2（续跑 VDI 部署），False 为首次执行
        """
        self.mode = mode
        self.log_file = "/var/log/vdi-deploy/installer.log"

        if mode == 1 and not phase2:
            # Mode 1 Phase 1: Live 环境装机
            self.steps = DEPLOY_STEPS_PHASE1.get(mode, [])
        else:
            # Mode 1 Phase 2（续跑）或 Mode 2/3/4
            self.steps = DEPLOY_STEPS_PHASE2.get(mode, [])

    def run(self, stdscr, deploy_engine, mode, config):
        """执行部署并显示进度

        每个步骤外层包一个 retry 循环：成功进下一步，失败弹 ErrorScreen
        按 retry/skip/exit 分流。

        Returns:
            True=所有步骤完成（可能有 skip）, False=用户退出
        """
        total = len(self.steps)
        if total == 0:
            logger.warning(f"No deploy steps defined for mode {mode}")
            return True

        step_names = [name for name, _ in self.steps]
        pb = ProgressBar(stdscr, "Deploy Progress", step_names,
                         log_source=lambda n: deploy_engine.get_recent_logs(n))

        had_skip = False

        try:
            for i, (step_name, step_id) in enumerate(self.steps):
                pb.update(i, step_name)

                # ── 内层 retry 循环 ──
                while True:
                    success, step_error = self._execute_step_with_ui(
                        pb, deploy_engine, step_id, mode, config, i, step_name)

                    if success:
                        pb.set_step_result(i, "ok")
                        break  # 进下一个 step

                    # ── 失败：弹 ErrorScreen，按选择分流 ──
                    pb.set_step_result(i, "fail")
                    log_path = os.path.join(deploy_engine.log_dir, f"{step_id}.log")
                    error_detail = step_error[:500] if step_error else "(see log)"

                    action = ErrorScreen(
                        error_message=f"Deploy failed: {step_name}",
                        solution=None,
                        log_file=log_path,
                    ).show(stdscr)

                    logger.info(f"Step {step_name} failed, user chose: {action}")

                    if action == "retry":
                        # 清旧 fail 标记，重新点亮 --> 重跑
                        pb.clear_step_result(i)
                        pb.update(i, step_name)
                        continue
                    elif action == "skip":
                        pb.set_step_result(i, "skip")
                        had_skip = True
                        break  # 进下一个 step
                    else:  # exit
                        pb.close()
                        config["_had_skip"] = had_skip
                        return False

            # ── 所有步骤完成 ──
            pb.update(total - 1, step_names[-1], 100)
            for i in range(total):
                if i not in pb.step_status:
                    pb.set_step_result(i, "ok")
            pb.finish(True)

            while True:
                ch = pb.win.getch()
                if ch in (10, 13, curses.KEY_ENTER, 27, ord('q')):
                    break

            pb.close()
            config["_had_skip"] = had_skip
            return True

        except Exception as e:
            logger.exception("Deploy process exception")
            try:
                pb.close()
            except Exception:
                pass
            ErrorScreen(f"Deploy exception: {e}", fatal=True).show(stdscr)
            return False

    def _execute_step_with_ui(self, pb, deploy_engine, step_id, mode, config, i, step_name):
        """执行单个 step，期间刷新 UI（含日志面板）。返回 (success, error)。

        step 在 worker 线程跑（不阻塞 UI），主线程每 0.3s 轮询：刷新 UI +
        检测 ESC/q 取消。失败时从 deploy_engine 日志缓冲取最后若干行作为
        error 详情（_run_streaming 已把输出灌进缓冲）。
        """
        step_result = [None]
        step_error = [""]

        def _run_step():
            try:
                ok = deploy_engine.execute_step(step_id, mode, config)
                step_result[0] = ok
                if not ok:
                    # 优先用实时缓冲的最后 10 行作为错误摘要（已 strip）
                    logs = deploy_engine.get_recent_logs(10)
                    step_error[0] = "\n".join(logs).strip() if logs else "(no detail)"
            except Exception as e:
                step_result[0] = False
                step_error[0] = str(e)

        worker = threading.Thread(target=_run_step, daemon=True)
        worker.start()

        cancelled = False
        while worker.is_alive():
            worker.join(timeout=0.3)
            # ESC/q 取消（非阻塞取键）
            pb.win.timeout(0)
            try:
                ch = pb.win.getch()
                if ch == 27 or ch == ord('q'):
                    cancelled = True
                    break
            except curses.error:
                pass
            finally:
                pb.win.timeout(-1)
            # 刷新 UI（含最新日志行）
            pb._draw()

        if cancelled:
            return False, "cancelled by user"
        worker.join()
        return bool(step_result[0]), step_error[0]
