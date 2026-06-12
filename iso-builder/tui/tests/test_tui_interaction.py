"""TUI 交互逻辑单元测试

通过 mock Whiptail._run 方法模拟用户操作，验证各 Screen 的交互流程。
不依赖真实 whiptail 二进制，纯 Python 逻辑验证。
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# 将 tui 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.whiptail_wrapper import Whiptail, _strip_ansi


# ─── Whiptail wrapper 单元测试 ───


class TestStripAnsi:
    """ANSI 清理测试"""

    def test_clean_text(self):
        assert _strip_ansi("hello world") == "hello world"

    def test_csi_sequence(self):
        assert _strip_ansi("\x1b[32mOK\x1b[0m") == "OK"

    def test_control_chars(self):
        assert _strip_ansi("foo\x00\x01\x07bar") == "foobar"

    def test_mixed(self):
        text = "\x1b[1;32m  1\x1b[0m\n\x1b[?25h"
        assert _strip_ansi(text) == "1"

    def test_empty(self):
        assert _strip_ansi("") == ""


class TestWhiptailExtractTag:
    """tag 提取鲁棒性测试"""

    def setup_method(self):
        self.wt = Whiptail.__new__(Whiptail)

    def test_exact_match(self):
        items = [("1", "desc1"), ("2", "desc2")]
        assert self.wt._extract_tag("1", items) == "1"

    def test_with_trailing_newline(self):
        items = [("1", "desc1"), ("2", "desc2")]
        assert self.wt._extract_tag("1\n", items) == "1"

    def test_with_ansi_noise(self):
        items = [("1", "desc1"), ("2", "desc2")]
        noisy = "\x1b[24;1H\x1b[K1"
        assert self.wt._extract_tag(noisy, items) == "1"

    def test_multiline_extract(self):
        items = [("1", "desc1"), ("2", "desc2"), ("3", "desc3")]
        assert self.wt._extract_tag("some noise\nmore noise\n2", items) == "2"

    def test_embedded_in_text(self):
        items = [("2", "desc")]
        assert self.wt._extract_tag("selected 2 item", items) == "2"

    def test_fallback_last_line(self):
        items = [("99", "desc")]
        assert self.wt._extract_tag("unknown", items) == "unknown"


# ─── 辅助：构造 mock 响应序列 ───


def _make_whiptail_responses(responses):
    """构造 mock 响应序列

    responses: [(returncode, output), ...]
    每次调用 _run 返回下一个响应
    """
    it = iter(responses)

    def mock_run(self, args, input_data=None):
        try:
            rc, output = next(it)
            return rc, output
        except StopIteration:
            return 255, ""

    return mock_run


# ─── Screen 交互逻辑测试 ───


class TestWelcomeScreen:
    """欢迎界面 — 模式选择测试"""

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(0, "1")]))
    def test_select_mode_1(self):
        from screens.welcome import WelcomeScreen
        result = WelcomeScreen().show()
        assert result == 1

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(0, "2")]))
    def test_select_mode_2(self):
        from screens.welcome import WelcomeScreen
        result = WelcomeScreen().show()
        assert result == 2

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(0, "3")]))
    def test_select_mode_3(self):
        from screens.welcome import WelcomeScreen
        result = WelcomeScreen().show()
        assert result == 3

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(0, "4")]))
    def test_select_mode_4(self):
        from screens.welcome import WelcomeScreen
        result = WelcomeScreen().show()
        assert result == 4

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(1, "")]))
    def test_cancel_returns_none(self):
        from screens.welcome import WelcomeScreen
        result = WelcomeScreen().show()
        assert result is None


class TestNetworkConfigScreen:
    """网络配置 — IP/掩码/网关/DNS/主机名"""

    @patch.object(Whiptail, '_run', _make_whiptail_responses([
        (0, "192.168.1.10"), (0, "24"), (0, "192.168.1.1"), (0, "192.168.1.1"), (0, "vdi-node-01")
    ]))
    def test_normal_flow(self):
        from screens.network_config import NetworkConfigScreen
        result = NetworkConfigScreen().show()
        assert result is not None
        assert result["node_ip"] == "192.168.1.10"
        assert result["netmask"] == "24"
        assert result["gateway"] == "192.168.1.1"
        assert result["dns"] == "192.168.1.1"
        assert result["hostname"] == "vdi-node-01"

    @patch.object(Whiptail, '_run', _make_whiptail_responses([
        (0, "invalid_ip"),        # IP: 第一次输入无效
        (0, ""),                  # msgbox: 错误提示
        (0, "192.168.1.10"),      # IP: 第二次输入有效
        (0, "24"),                # CIDR
        (0, "192.168.1.1"),       # Gateway
        (0, "192.168.1.1"),       # DNS
        (0, "vdi-node-01"),       # Hostname
    ]))
    def test_invalid_ip_retry(self):
        """输入无效 IP 后重试"""
        from screens.network_config import NetworkConfigScreen
        result = NetworkConfigScreen().show()
        assert result is not None
        assert result["node_ip"] == "192.168.1.10"

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(1, "")]))
    def test_cancel_returns_none(self):
        from screens.network_config import NetworkConfigScreen
        result = NetworkConfigScreen().show()
        assert result is None


class TestClusterConfigScreen:
    """集群配置 — 角色/VIP/CIDR"""

    @patch.object(Whiptail, '_run', _make_whiptail_responses([
        (0, "master"), (0, "192.168.1.100"), (0, "ens160"),
        (0, "10.16.0.0/16"), (0, "10.96.0.0/12"), (0, "v1.34.3"),
    ]))
    def test_master_config(self):
        from screens.cluster_config import ClusterConfigScreen
        result = ClusterConfigScreen().show()
        assert result is not None
        assert result["role"] == "master"
        assert result["vip"] == "192.168.1.100"
        assert result["pod_cidr"] == "10.16.0.0/16"
        assert result["svc_cidr"] == "10.96.0.0/12"

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(1, "")]))
    def test_cancel_returns_none(self):
        from screens.cluster_config import ClusterConfigScreen
        result = ClusterConfigScreen().show()
        assert result is None


class TestStorageConfigScreen:
    """存储配置 — 磁盘/目录/副本数"""

    @patch.object(Whiptail, '_run', _make_whiptail_responses([
        (0, ""), (0, "/dev/sdb"), (0, ""), (0, "/var/lib/longhorn"), (0, "3"),
    ]))
    def test_normal_flow(self):
        from screens.storage_config import StorageConfigScreen
        result = StorageConfigScreen().show()
        assert result is not None
        assert result["longhorn_disk"] == "/dev/sdb"
        assert result["longhorn_data_dir"] == "/var/lib/longhorn"
        assert result["longhorn_replicas"] == "3"

    @patch.object(Whiptail, '_run', _make_whiptail_responses([
        (0, ""), (0, "/dev/sdb"), (1, ""),
    ]))
    def test_cancel_format_returns_none(self):
        from screens.storage_config import StorageConfigScreen
        result = StorageConfigScreen().show()
        assert result is None


class TestConfirmScreen:
    """配置确认"""

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(0, "")]))
    def test_confirm_yes(self):
        from screens.confirm import ConfirmScreen
        config = {
            "mode": 1, "hostname": "node1", "node_ip": "192.168.1.10",
            "netmask": "24", "gateway": "192.168.1.1", "dns": "192.168.1.1",
            "role": "master", "vip": "192.168.1.100", "vip_interface": "ens160",
            "pod_cidr": "10.16.0.0/16", "svc_cidr": "10.96.0.0/12",
            "k8s_version": "v1.34.3", "longhorn_disk": "/dev/sdb",
            "longhorn_data_dir": "/var/lib/longhorn", "longhorn_replicas": "3",
        }
        assert ConfirmScreen(config).show() is True

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(1, "")]))
    def test_confirm_no(self):
        from screens.confirm import ConfirmScreen
        assert ConfirmScreen({"mode": 1}).show() is False


class TestErrorScreen:
    """错误界面"""

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(0, "1")]))
    def test_retry(self):
        from screens.error import ErrorScreen
        assert ErrorScreen("test error").show() == "retry"

    @patch.object(Whiptail, '_run', _make_whiptail_responses([(0, "4")]))
    def test_exit(self):
        from screens.error import ErrorScreen
        assert ErrorScreen("test error").show() == "exit"


# ─── VDIInstaller 主流程测试 ───


class TestVDIInstallerFlow:
    """完整流程测试 — 验证模式 1 (Fresh Install) 的全链路"""

    @patch('installer.DeployEngine')
    @patch('installer.ConfigGenerator')
    @patch('installer.OfflineManager')
    def test_mode1_full_flow(self, MockOffline, MockConfigGen, MockDeploy):
        """模式 1 完整流程：Welcome → Network → Cluster → Storage → Confirm → Deploy"""
        MockOffline.return_value.is_available.return_value = True
        MockConfigGen.return_value.generate.return_value = None
        MockDeploy.return_value.execute_step.return_value = True

        responses = [
            (0, "1"),                    # Welcome: mode 1
            (0, "192.168.220.129"),      # Network: IP
            (0, "24"),                   # Network: CIDR
            (0, "192.168.220.2"),        # Network: GW
            (0, "192.168.220.2"),        # Network: DNS
            (0, "vdi-node-01"),          # Network: Hostname
            (0, "master"),               # Cluster: Role
            (0, "192.168.220.100"),      # Cluster: VIP
            (0, "ens160"),               # Cluster: Interface
            (0, "10.16.0.0/16"),        # Cluster: Pod CIDR
            (0, "10.96.0.0/12"),        # Cluster: SVC CIDR
            (0, "v1.34.3"),             # Cluster: K8s ver
            (0, ""),                     # Storage: msgbox (disk info)
            (0, "/dev/sdb"),             # Storage: disk
            (0, ""),                     # Storage: yesno (format confirm)
            (0, "/var/lib/longhorn"),    # Storage: data dir
            (0, "3"),                    # Storage: replicas
            (0, ""),                     # Confirm: yesno → True
            (0, ""),                     # Complete: msgbox
        ]

        with patch.object(Whiptail, '_run', _make_whiptail_responses(responses)):
            from installer import VDIInstaller
            installer = VDIInstaller()
            result = installer.run()
            assert result == 0

    @patch('installer.DeployEngine')
    @patch('installer.ConfigGenerator')
    @patch('installer.OfflineManager')
    def test_cancel_at_welcome(self, MockOffline, MockConfigGen, MockDeploy):
        """在欢迎页取消 → 返回 0"""
        MockOffline.return_value.is_available.return_value = True

        with patch.object(Whiptail, '_run', _make_whiptail_responses([(1, "")])):
            from installer import VDIInstaller
            installer = VDIInstaller()
            result = installer.run()
            assert result == 0

    @patch('installer.DeployEngine')
    @patch('installer.ConfigGenerator')
    @patch('installer.OfflineManager')
    def test_cancel_at_network(self, MockOffline, MockConfigGen, MockDeploy):
        """在网络配置页取消 → 返回 0"""
        MockOffline.return_value.is_available.return_value = True

        responses = [(0, "1"), (1, "")]
        with patch.object(Whiptail, '_run', _make_whiptail_responses(responses)):
            from installer import VDIInstaller
            installer = VDIInstaller()
            result = installer.run()
            assert result == 0

    @patch('installer.DeployEngine')
    @patch('installer.ConfigGenerator')
    @patch('installer.OfflineManager')
    def test_cancel_at_confirm(self, MockOffline, MockConfigGen, MockDeploy):
        """在确认页取消 → 返回 0"""
        MockOffline.return_value.is_available.return_value = True

        responses = [
            (0, "1"),
            (0, "10.0.0.1"), (0, "24"), (0, "10.0.0.254"), (0, "10.0.0.254"), (0, "node1"),
            (0, "master"), (0, "10.0.0.100"), (0, "ens160"), (0, "10.16.0.0/16"), (0, "10.96.0.0/12"), (0, "v1.34.3"),
            (0, ""), (0, "/dev/sdb"), (0, ""), (0, "/var/lib/longhorn"), (0, "3"),
            (1, ""),  # Confirm: No
        ]
        with patch.object(Whiptail, '_run', _make_whiptail_responses(responses)):
            from installer import VDIInstaller
            installer = VDIInstaller()
            result = installer.run()
            assert result == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
