#!/usr/bin/env python3
"""VDI 离线部署 TUI 安装器主程序

基于 Python curses 标准库构建，零外部依赖。
curses.wrapper() 保证终端状态在任何情况下都能恢复，
从根源解决 whiptail/SLang 终端状态损坏问题。
"""
import sys
import os
import signal
import subprocess
import logging
import curses

# 将 tui 目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screens.welcome import WelcomeScreen
from screens.network_config import NetworkConfigScreen
from screens.cluster_config import ClusterConfigScreen
from screens.join_config import JoinConfigScreen
from screens.storage_config import StorageConfigScreen
from screens.disk_config import DiskConfigScreen
from screens.confirm import ConfirmScreen
from screens.progress import ProgressScreen
from screens.complete import CompleteScreen
from screens.error import ErrorScreen
from backend.config_generator import ConfigGenerator
from backend.deploy import DeployEngine
from utils.logger import setup_logger
from utils.offline import OfflineManager
from utils.install_state import is_resumable, load_state, save_state, update_phase, clear_state

# 部署模式常量
MODE_FIRST = 1      # 首节点：装机 + 创建集群 + 启动发现服务
MODE_CONTROL = 2    # 管理节点：装机 + 加入控制面（HA）
MODE_WORKER = 3     # 工作节点：装机 + 加入集群运行桌面


class VDIInstaller:
    """VDI TUI 安装器主类"""

    def __init__(self):
        self.logger = setup_logger()
        self.config = {}
        self.mode = None
        self.offline = OfflineManager()
        self.deploy_engine = DeployEngine()
        self.config_generator = ConfigGenerator()

    def run(self, stdscr):
        """curses 主流程入口

        由 curses.wrapper() 调用，保证终端状态恢复。
        支持两阶段部署：
          Phase 1 (Live 环境): 收集配置 → 装机(os-install) → 重启
          Phase 2 (硬盘环境): 检测 install-state.json → 恢复配置 → VDI 部署
        """
        # 初始化 curses 设置
        curses.curs_set(0)          # 隐藏光标
        curses.noecho()             # 不回显按键
        curses.cbreak()             # 即时输入（无需等待 Enter）
        stdscr.keypad(True)         # 启用功能键
        stdscr.timeout(-1)          # 阻塞等待输入

        # 尝试启用颜色
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()

        self.logger.info("VDI 安装器启动 (curses mode)")

        try:
            # 检测是否为续跑（硬盘启动后的 Phase 2）
            if is_resumable():
                return self._resume_deploy(stdscr)

            # ── 全新流程 ──

            # 步骤 1：检查离线资源
            if not self._check_offline_resources():
                return 1

            # 步骤 2：选择部署模式
            self.mode = WelcomeScreen().show(stdscr)
            if self.mode is None:
                self.logger.info("User cancelled mode selection")
                return 0

            self.logger.info(f"Selected deploy mode: {self.mode}")
            self.config["mode"] = self.mode

            # 步骤 3：根据模式收集配置
            if not self._collect_config(stdscr):
                return 0

            # 步骤 4：确认配置
            if not ConfirmScreen(self.config).show(stdscr):
                self.logger.info("User cancelled confirmation")
                return 0

            # 步骤 5：生成配置文件 + 保存装机状态
            self.config_generator.generate(self.mode, self.config)
            save_state("configuring", self.mode, self.config)

            # 步骤 6：执行部署（Phase 1 装机）
            success = self._execute_deploy(stdscr)

            # 步骤 7：显示结果
            if success:
                action = CompleteScreen(self.mode, self.config).show(stdscr)
                if action == "reboot":
                    self._reboot()
                return 0
            else:
                return 1

        except Exception as e:
            self.logger.exception("Installer exited with exception")
            # 异常时尝试显示错误（curses 可能仍可用）
            try:
                ErrorScreen(str(e)).show(stdscr)
            except Exception:
                pass
            return 1

    def _resume_deploy(self, stdscr):
        """续跑 Phase 2：从 install-state.json 恢复配置，继续 VDI 部署"""
        state = load_state()
        if state is None:
            self.logger.error("续跑失败: 无法读取状态文件")
            return 1

        self.mode = state["mode"]
        self.config = state.get("config", {})
        self.config["mode"] = self.mode
        self.config["resumed"] = True

        self.logger.info(f"续跑 Phase 2: mode={self.mode}")

        # 更新 phase 标记
        update_phase("deploying")

        # 检查离线资源
        if not self._check_offline_resources():
            return 1

        # Phase 2: 执行 VDI 部署步骤（os-init → kagent）
        try:
            progress = ProgressScreen(self.mode, phase2=True)
            success = progress.run(stdscr, self.deploy_engine, self.mode, self.config)
        except Exception as e:
            self.logger.exception("Phase 2 deploy exception")
            ErrorScreen(f"Phase 2 deploy failed: {e}").show(stdscr)
            success = False

        if success:
            update_phase("deployed")
            action = CompleteScreen(self.mode, self.config).show(stdscr)
            if action == "reboot":
                self._reboot()
            clear_state()
            return 0
        else:
            return 1

    def _check_offline_resources(self):
        """检查离线资源完整性"""
        self.logger.info("Checking offline resources...")
        if self.offline.is_available():
            self.config["offline_available"] = True
            self.logger.info(f"Offline resources detected: {self.offline.base_dir}")
        else:
            self.config["offline_available"] = False
            self.logger.warning("Offline resources not available, continuing in online mode")
        return True

    def _collect_config(self, stdscr):
        """根据部署模式收集配置参数"""
        try:
            # 磁盘配置（所有模式都需要装机）
            default_hostnames = {MODE_FIRST: "vdi-master-01", MODE_CONTROL: "vdi-control-01", MODE_WORKER: "vdi-worker-01"}
            disk_config = DiskConfigScreen().show(stdscr, default_hostnames.get(self.mode, "vdi-node-01"))
            if disk_config is None:
                return False
            self.config.update(disk_config)

            # 网络配置（所有模式都需要）
            net_config = NetworkConfigScreen().show(stdscr)
            if net_config is None:
                return False
            self.config.update(net_config)

            # 根据模式收集特定配置
            if self.mode == MODE_FIRST:
                cluster_config = ClusterConfigScreen().show(stdscr)
                if cluster_config is None:
                    return False
                self.config.update(cluster_config)

                storage_config = StorageConfigScreen().show(stdscr)
                if storage_config is None:
                    return False
                self.config.update(storage_config)

            elif self.mode in (MODE_CONTROL, MODE_WORKER):
                join_config = JoinConfigScreen().show(stdscr, self.mode)
                if join_config is None:
                    return False
                self.config.update(join_config)

            return True

        except Exception as e:
            self.logger.exception("Config collection exception")
            ErrorScreen(f"Config collection failed: {e}").show(stdscr)
            return False

    def _execute_deploy(self, stdscr):
        """执行部署流程

        Mode 1 (Master): Phase 1 装机 → 重启 → Phase 2 部署集群
        Mode 2 (Worker): Phase 1 装机 → 重启 → Phase 2 加入集群
        """
        try:
            is_fresh = self.mode in (MODE_FIRST, MODE_CONTROL, MODE_WORKER)
            progress = ProgressScreen(self.mode, phase2=False)
            result = progress.run(stdscr, self.deploy_engine, self.mode, self.config)

            if result and is_fresh:
                # Phase 1 完成（OS 已写入磁盘），更新状态标记
                update_phase("os-installed")
                self.config["_need_reboot"] = True

            return result
        except Exception as e:
            self.logger.exception("Deploy execution exception")
            ErrorScreen(f"Deploy failed: {e}").show(stdscr)
            return False

    def _reboot(self):
        """重启系统"""
        self.logger.info("Rebooting system...")
        # 退出 curses 模式再打印提示
        curses.endwin()
        print("\nRebooting in 3 seconds... (Ctrl+C to cancel)")
        try:
            import time
            time.sleep(3)
            subprocess.run(["sync"], check=False)
            subprocess.run(["reboot", "-f"], check=False)
        except KeyboardInterrupt:
            print("\nReboot cancelled. Type 'reboot' to restart manually.")
        except Exception as e:
            self.logger.error(f"Reboot failed: {e}")
            print(f"\nReboot failed: {e}. Type 'reboot' manually.")


def main():
    """主入口"""
    # 检查是否在 TTY 环境中
    if not sys.stdin.isatty():
        print("Error: This program requires a TTY environment", file=sys.stderr)
        sys.exit(1)

    # 设置 TERM 环境变量（curses 依赖）
    term = os.environ.get("TERM")
    if not term or term == "dumb":
        os.environ["TERM"] = "linux"
        print(f"TERM not set, auto-set to linux", file=sys.stderr)

    try:
        installer = VDIInstaller()
    except Exception as e:
        print(f"Error: Installer init failed: {e}", file=sys.stderr)
        print("Check /var/log/vdi-deploy/installer.log for details", file=sys.stderr)
        sys.exit(1)

    # curses.wrapper 保证:
    # 1. 调用 initscr() 初始化
    # 2. 调用 endwin() 恢复终端（即使在异常情况下）
    # 3. 恢复 echo/cbreak 等模式
    # 终端状态损坏问题从根源消除
    sys.exit(curses.wrapper(installer.run))


if __name__ == "__main__":
    main()
