#!/usr/bin/env python3
"""VDI 离线部署 TUI 安装器主程序

使用 whiptail 提供 TUI 界面，引导用户完成 VDI 集群部署。
4 种部署模式：全新安装 / 追加部署 / 添加节点 / PXE 服务
"""
import sys
import os
import signal
import subprocess
import logging

# 将 tui 目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screens.welcome import WelcomeScreen
from screens.network_config import NetworkConfigScreen
from screens.cluster_config import ClusterConfigScreen
from screens.join_config import JoinConfigScreen
from screens.pxe_config import PXEConfigScreen
from screens.storage_config import StorageConfigScreen
from screens.confirm import ConfirmScreen
from screens.progress import ProgressScreen
from screens.complete import CompleteScreen
from screens.error import ErrorScreen
from backend.config_generator import ConfigGenerator
from backend.deploy import DeployEngine
from utils.logger import setup_logger
from utils.offline import OfflineManager

# 部署模式常量
MODE_FRESH = 1      # 全新安装：安装 OS + 部署 VDI
MODE_APPEND = 2     # 追加部署：已有 OS，仅部署 VDI
MODE_JOIN = 3       # 添加节点：作为 Worker 加入已有集群
MODE_PXE = 4        # PXE 服务：启动 PXE Server


class VDIInstaller:
    """VDI TUI 安装器主类"""

    def __init__(self):
        self.logger = setup_logger()
        self.config = {}
        self.mode = None
        self.offline = OfflineManager()
        self.deploy_engine = DeployEngine()
        self.config_generator = ConfigGenerator()

        # 注册信号处理
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def run(self):
        """主流程入口"""
        self.logger.info("VDI 安装器启动")

        try:
            # 步骤 1：检查离线资源
            if not self._check_offline_resources():
                return 1

            # 步骤 2：选择部署模式
            self.mode = WelcomeScreen().show()
            if self.mode is None:
                self.logger.info("用户取消选择")
                return 0

            self.logger.info(f"选择部署模式: {self.mode}")

            # 步骤 3：根据模式收集配置
            if not self._collect_config():
                return 0

            # 步骤 4：确认配置
            if not ConfirmScreen(self.config).show():
                self.logger.info("用户取消确认")
                return 0

            # 步骤 5：生成配置文件
            self.config_generator.generate(self.mode, self.config)

            # 步骤 6：执行部署
            success = self._execute_deploy()

            # 步骤 7：显示结果
            if success:
                CompleteScreen(self.mode, self.config).show()
                return 0
            else:
                return 1

        except Exception as e:
            self.logger.exception("安装器异常退出")
            ErrorScreen(str(e)).show()
            return 1

    def _check_offline_resources(self):
        """检查离线资源完整性"""
        self.logger.info("检查离线资源...")
        if not self.offline.is_available():
            # 非离线环境也允许继续（用于开发测试）
            self.logger.warning("离线资源不可用，继续在线模式")
        return True

    def _collect_config(self):
        """根据部署模式收集配置参数"""
        try:
            # 网络配置（所有模式都需要）
            net_config = NetworkConfigScreen().show()
            if net_config is None:
                return False
            self.config.update(net_config)

            # 根据模式收集特定配置
            if self.mode in (MODE_FRESH, MODE_APPEND):
                # 集群配置
                cluster_config = ClusterConfigScreen().show()
                if cluster_config is None:
                    return False
                self.config.update(cluster_config)

                # 存储配置
                storage_config = StorageConfigScreen().show()
                if storage_config is None:
                    return False
                self.config.update(storage_config)

            elif self.mode == MODE_JOIN:
                # Join 配置
                join_config = JoinConfigScreen().show()
                if join_config is None:
                    return False
                self.config.update(join_config)

            elif self.mode == MODE_PXE:
                # PXE 配置
                cluster_config = ClusterConfigScreen().show()
                if cluster_config is None:
                    return False
                self.config.update(cluster_config)

                pxe_config = PXEConfigScreen().show()
                if pxe_config is None:
                    return False
                self.config.update(pxe_config)

            return True

        except Exception as e:
            self.logger.exception("配置收集异常")
            ErrorScreen(f"配置收集失败: {e}").show()
            return False

    def _execute_deploy(self):
        """执行部署流程"""
        try:
            progress = ProgressScreen(self.mode)
            result = progress.run(self.deploy_engine, self.mode, self.config)
            return result
        except Exception as e:
            self.logger.exception("部署执行异常")
            ErrorScreen(f"部署失败: {e}").show()
            return False

    def _handle_interrupt(self, signum, frame):
        """处理中断信号"""
        self.logger.info(f"收到信号 {signum}，退出安装器")
        print("\n\n安装器已取消。")
        sys.exit(130)


def main():
    """主入口"""
    # 检查是否在 TTY 环境中
    if not sys.stdin.isatty():
        print("错误: 此程序需要在 TTY 环境中运行", file=sys.stderr)
        sys.exit(1)

    # 检查 whiptail 是否可用
    try:
        subprocess.run(["which", "whiptail"], check=True,
                       capture_output=True)
    except subprocess.CalledProcessError:
        print("错误: whiptail 未安装，请执行: apt-get install whiptail",
              file=sys.stderr)
        sys.exit(1)

    installer = VDIInstaller()
    sys.exit(installer.run())


if __name__ == "__main__":
    main()
