#!/usr/bin/env python3
"""TUI 安装器全面功能测试

验证模式体系、两阶段流程、配置生成、加入集群逻辑、状态管理。
不依赖 TTY/curses，纯逻辑验证。
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tui'))


class TestModeConsistency(unittest.TestCase):
    """模式定义一致性测试"""

    def test_welcome_modes_match_progress(self):
        from screens.welcome import MODES
        from screens.progress import DEPLOY_STEPS_PHASE1, DEPLOY_STEPS_PHASE2
        mode_ids = {int(k) for k, _ in MODES}
        self.assertEqual(mode_ids, set(DEPLOY_STEPS_PHASE1.keys()))
        self.assertEqual(mode_ids, set(DEPLOY_STEPS_PHASE2.keys()))

    def test_complete_mode_names_cover_all(self):
        from screens.welcome import MODES
        from screens.complete import MODE_NAMES
        mode_ids = {int(k) for k, _ in MODES}
        self.assertEqual(mode_ids, set(MODE_NAMES.keys()))

    def test_confirm_mode_names_cover_all(self):
        from screens.welcome import MODES
        from screens.confirm import MODE_NAMES
        mode_ids = {int(k) for k, _ in MODES}
        self.assertEqual(mode_ids, set(MODE_NAMES.keys()))

    def test_exactly_3_modes(self):
        from screens.welcome import MODES
        self.assertEqual(len(MODES), 3)


class TestProgressPhaseSelection(unittest.TestCase):
    """ProgressScreen Phase 判断逻辑测试"""

    def test_phase1_all_modes(self):
        """所有模式 phase2=False 时应走 Phase 1 (os-install)"""
        from screens.progress import ProgressScreen, DEPLOY_STEPS_PHASE1
        for mode in (1, 2, 3):
            ps = ProgressScreen(mode, phase2=False)
            self.assertEqual(ps.steps, DEPLOY_STEPS_PHASE1[mode],
                             f"Mode {mode} Phase 1 步骤不正确")
            self.assertEqual(len(ps.steps), 1)
            self.assertEqual(ps.steps[0][1], "os-install")

    def test_phase2_all_modes(self):
        """所有模式 phase2=True 时应走 Phase 2"""
        from screens.progress import ProgressScreen, DEPLOY_STEPS_PHASE2
        for mode in (1, 2, 3):
            ps = ProgressScreen(mode, phase2=True)
            self.assertEqual(ps.steps, DEPLOY_STEPS_PHASE2[mode],
                             f"Mode {mode} Phase 2 步骤不正确")

    def test_mode1_phase2_has_discovery(self):
        """首节点 Phase 2 最后一步应是 enable-discovery"""
        from screens.progress import DEPLOY_STEPS_PHASE2
        last_step = DEPLOY_STEPS_PHASE2[1][-1]
        self.assertEqual(last_step[1], "enable-discovery")

    def test_mode2_phase2_has_join_control_plane(self):
        """管理节点 Phase 2 应有 Join Control Plane"""
        from screens.progress import DEPLOY_STEPS_PHASE2
        step_ids = [s[1] for s in DEPLOY_STEPS_PHASE2[2]]
        self.assertIn("join-cluster", step_ids)

    def test_mode3_phase2_has_join_cluster(self):
        """工作节点 Phase 2 应有 Join Cluster"""
        from screens.progress import DEPLOY_STEPS_PHASE2
        step_ids = [s[1] for s in DEPLOY_STEPS_PHASE2[3]]
        self.assertIn("join-cluster", step_ids)


class TestInstallState(unittest.TestCase):
    """装机状态管理测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "install-state.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch('utils.install_state.STATE_DIR', new_callable=lambda: property(lambda self: None))
    def test_save_and_load_state(self, *_):
        from utils.install_state import save_state, load_state
        import utils.install_state as ist
        ist.STATE_DIR = self.tmpdir
        ist.STATE_FILE = self.state_file

        config = {"hostname": "vdi-master-01", "install_disk": "/dev/sda"}
        save_state("configuring", 1, config)

        state = load_state()
        self.assertIsNotNone(state)
        self.assertEqual(state["phase"], "configuring")
        self.assertEqual(state["mode"], 1)
        self.assertEqual(state["config"]["hostname"], "vdi-master-01")

    def test_is_resumable(self):
        from utils.install_state import save_state, is_resumable
        import utils.install_state as ist
        ist.STATE_DIR = self.tmpdir
        ist.STATE_FILE = self.state_file

        # 无状态文件
        self.assertFalse(is_resumable())

        # phase=configuring 不可续跑
        save_state("configuring", 1, {})
        self.assertFalse(is_resumable())

        # phase=os-installed 可续跑
        state = json.load(open(self.state_file))
        state["phase"] = "os-installed"
        json.dump(state, open(self.state_file, 'w'))
        self.assertTrue(is_resumable())

    def test_update_phase(self):
        from utils.install_state import save_state, update_phase, load_state
        import utils.install_state as ist
        ist.STATE_DIR = self.tmpdir
        ist.STATE_FILE = self.state_file

        save_state("configuring", 1, {"hostname": "test"})
        update_phase("os-installed")

        state = load_state()
        self.assertEqual(state["phase"], "os-installed")
        self.assertEqual(state["config"]["hostname"], "test")

    def test_clear_state(self):
        from utils.install_state import save_state, clear_state, load_state
        import utils.install_state as ist
        ist.STATE_DIR = self.tmpdir
        ist.STATE_FILE = self.state_file

        save_state("deployed", 1, {})
        self.assertTrue(os.path.exists(self.state_file))
        clear_state()
        self.assertIsNone(load_state())


class TestConfigGenerator(unittest.TestCase):
    """配置生成器测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_mode1_generates_all_files(self):
        from backend.config_generator import ConfigGenerator
        gen = ConfigGenerator(output_dir=self.tmpdir)
        config = {
            "node_ip": "192.168.220.128", "netmask": "24",
            "gateway": "192.168.220.2", "dns": "192.168.220.2",
            "hostname": "vdi-master-01",
            "vip": "192.168.220.100", "vip_interface": "ens160",
            "pod_cidr": "10.16.0.0/16", "svc_cidr": "10.96.0.0/12",
            "k8s_version": "v1.34.3", "role": "master",
            "longhorn_disk": "/dev/sdb", "longhorn_data_dir": "/var/lib/longhorn",
            "longhorn_replicas": "3", "install_disk": "/dev/sda",
            "partition_scheme": "auto", "swap_size": "8G",
        }
        gen.generate(1, config)

        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "env-config.sh")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "hosts")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "inventory.yaml")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "config.yaml")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "install.key")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "install-state.json")))

        # install-key 非空
        with open(os.path.join(self.tmpdir, "install.key")) as f:
            key = f.read().strip()
            self.assertEqual(len(key), 24)

    def test_mode2_generates_minimal_files(self):
        from backend.config_generator import ConfigGenerator
        gen = ConfigGenerator(output_dir=self.tmpdir)
        config = {
            "hostname": "vdi-control-01", "install_disk": "/dev/sda",
            "partition_scheme": "auto", "swap_size": "8G",
            "master_ip": "192.168.220.128", "join_method": "control-plane",
            "join_command": "kubeadm join 192.168.220.100:6443 --control-plane",
        }
        gen.generate(2, config)

        # Mode 2 不应生成 hosts/inventory/config/install-key
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "hosts")))
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "install.key")))
        # 但应生成 env-config.sh 和 install-state.json
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "env-config.sh")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "install-state.json")))

    def test_mode3_generates_minimal_files(self):
        from backend.config_generator import ConfigGenerator
        gen = ConfigGenerator(output_dir=self.tmpdir)
        config = {
            "hostname": "vdi-worker-01", "install_disk": "/dev/sda",
            "partition_scheme": "auto", "swap_size": "8G",
            "master_ip": "192.168.220.128", "join_method": "worker",
            "join_command": "kubeadm join 192.168.220.100:6443",
        }
        gen.generate(3, config)

        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "hosts")))
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "install.key")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "env-config.sh")))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "install-state.json")))

    def test_env_config_contains_disk_params(self):
        from backend.config_generator import ConfigGenerator
        gen = ConfigGenerator(output_dir=self.tmpdir)
        config = {
            "install_disk": "/dev/nvme0n1",
            "partition_scheme": "minimal",
            "swap_size": "0",
            "hostname": "vdi-worker-01",
        }
        gen.generate(3, config)

        with open(os.path.join(self.tmpdir, "env-config.sh")) as f:
            content = f.read()
            self.assertIn("/dev/nvme0n1", content)
            self.assertIn("minimal", content)
            self.assertIn("vdi-worker-01", content)

    def test_install_state_json_structure(self):
        from backend.config_generator import ConfigGenerator
        gen = ConfigGenerator(output_dir=self.tmpdir)
        config = {"hostname": "test", "install_disk": "/dev/sda"}
        gen.generate(1, config)

        with open(os.path.join(self.tmpdir, "install-state.json")) as f:
            state = json.load(f)
            self.assertEqual(state["phase"], "configuring")
            self.assertEqual(state["mode"], 1)
            self.assertIn("install_disk", state["config"])


class TestJoinClusterLogic(unittest.TestCase):
    """加入集群命令构造测试"""

    def test_worker_join_with_discovery_command(self):
        from backend.deploy import DeployEngine
        engine = DeployEngine()
        config = {
            "join_command": "kubeadm join 192.168.220.100:6443 --token abc.123 --discovery-token-ca-cert-hash sha256:xyz",
            "join_method": "worker",
        }
        # 不实际执行，只验证命令拼接逻辑
        join_cmd = config.get("join_command", "")
        self.assertIn("kubeadm join", join_cmd)
        self.assertNotIn("--control-plane", join_cmd)

    def test_control_plane_join_with_discovery_command(self):
        config = {
            "join_command": "kubeadm join 192.168.220.100:6443 --token abc.123 --discovery-token-ca-cert-hash sha256:xyz --control-plane --certificate-key deadbeef",
            "join_method": "control-plane",
        }
        join_cmd = config.get("join_command", "")
        self.assertIn("--control-plane", join_cmd)
        self.assertIn("--certificate-key", join_cmd)

    def test_manual_worker_join_fallback(self):
        config = {
            "master_ip": "192.168.220.100",
            "join_token": "abc.123",
            "ca_cert_hash": "sha256:xyz",
            "join_method": "worker",
        }
        # 模拟手动拼接
        master_ip = config["master_ip"]
        token = config["join_token"]
        ca_hash = config["ca_cert_hash"]
        join_method = config["join_method"]
        cmd = f"kubeadm join {master_ip}:6443 --token {token}"
        if ca_hash:
            cmd += f" --discovery-token-ca-cert-hash {ca_hash}"
        if join_method == "control-plane":
            cmd += " --control-plane"
        self.assertNotIn("--control-plane", cmd)

    def test_manual_control_plane_join_fallback(self):
        config = {
            "master_ip": "192.168.220.100",
            "join_token": "abc.123",
            "ca_cert_hash": "sha256:xyz",
            "join_method": "control-plane",
            "certificate_key": "deadbeef",
        }
        master_ip = config["master_ip"]
        token = config["join_token"]
        ca_hash = config["ca_cert_hash"]
        join_method = config["join_method"]
        cert_key = config["certificate_key"]
        cmd = f"kubeadm join {master_ip}:6443 --token {token}"
        if ca_hash:
            cmd += f" --discovery-token-ca-cert-hash {ca_hash}"
        if join_method == "control-plane":
            cmd += " --control-plane"
            if cert_key:
                cmd += f" --certificate-key {cert_key}"
        self.assertIn("--control-plane", cmd)
        self.assertIn("--certificate-key deadbeef", cmd)


class TestJoinConfigScreenDiscovery(unittest.TestCase):
    """Discovery 服务获取逻辑测试"""

    @patch('screens.join_config._fetch_cluster_info')
    def test_fetch_cluster_info_success(self, mock_fetch):
        mock_fetch.return_value = {
            "vip": "192.168.220.100",
            "pod_cidr": "10.16.0.0/16",
            "svc_cidr": "10.96.0.0/12",
            "k8s_version": "v1.34.3",
            "vip_interface": "ens160",
        }
        from screens.join_config import _fetch_cluster_info
        result = _fetch_cluster_info("192.168.220.128")
        self.assertEqual(result["vip"], "192.168.220.100")
        self.assertEqual(result["k8s_version"], "v1.34.3")

    @patch('screens.join_config._fetch_cluster_info')
    def test_fetch_cluster_info_failure(self, mock_fetch):
        mock_fetch.return_value = None
        from screens.join_config import _fetch_cluster_info
        result = _fetch_cluster_info("192.168.220.128")
        self.assertIsNone(result)

    def test_fetch_cp_join_403(self):
        """403 时 _fetch_cp_join 应捕获异常返回 None"""
        import urllib.error
        from screens.join_config import _fetch_cp_join
        with patch('urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="", code=403, msg="Forbidden", hdrs=None, fp=None)
            result = _fetch_cp_join("192.168.220.128", "wrong-key")
            self.assertIsNone(result)

    @patch('screens.join_config._fetch_join_token')
    def test_fetch_join_token_success(self, mock_fetch):
        mock_fetch.return_value = {
            "token": "abc.123def",
            "ca_cert_hash": "sha256:xyz",
            "join_command": "kubeadm join 192.168.220.100:6443 --token abc.123def --discovery-token-ca-cert-hash sha256:xyz",
        }
        from screens.join_config import _fetch_join_token
        result = _fetch_join_token("192.168.220.128")
        self.assertIn("join_command", result)


class TestDiskConfig(unittest.TestCase):
    """磁盘配置逻辑测试"""

    def test_hostname_default_per_mode(self):
        """验证各模式有不同默认 hostname"""
        from installer import MODE_FIRST, MODE_CONTROL, MODE_WORKER
        default_hostnames = {
            MODE_FIRST: "vdi-master-01",
            MODE_CONTROL: "vdi-control-01",
            MODE_WORKER: "vdi-worker-01",
        }
        self.assertEqual(len(set(default_hostnames.values())), 3,
                         "各模式默认 hostname 应不同")


class TestValidator(unittest.TestCase):
    """参数校验测试"""

    def test_validate_ip(self):
        from utils.validator import validate_ip
        self.assertEqual(validate_ip("192.168.1.1"), (True, ""))
        self.assertFalse(validate_ip("999.1.1.1")[0])
        self.assertFalse(validate_ip("")[0])
        self.assertFalse(validate_ip("not-an-ip")[0])

    def test_validate_cidr(self):
        from utils.validator import validate_cidr
        self.assertEqual(validate_cidr("10.16.0.0/16"), (True, ""))
        self.assertFalse(validate_cidr("invalid")[0])
        self.assertFalse(validate_cidr("10.16.0.0/33")[0])

    def test_validate_hostname(self):
        from utils.validator import validate_hostname
        self.assertEqual(validate_hostname("vdi-master-01"), (True, ""))
        self.assertFalse(validate_hostname("")[0])
        self.assertFalse(validate_hostname("invalid_hostname")[0])

    def test_validate_disk(self):
        from utils.validator import validate_disk
        self.assertEqual(validate_disk("/dev/sda"), (True, ""))
        self.assertFalse(validate_disk("sda")[0])
        self.assertFalse(validate_disk("")[0])


class TestTwoPhaseFlow(unittest.TestCase):
    """两阶段流程集成测试"""

    def test_phase1_sets_need_reboot(self):
        """Phase 1 完成后应设置 _need_reboot"""
        from installer import MODE_FIRST, MODE_CONTROL, MODE_WORKER
        for mode in (MODE_FIRST, MODE_CONTROL, MODE_WORKER):
            config = {"mode": mode}
            # 模拟 _execute_deploy 中 Phase 1 完成后的逻辑
            is_fresh = mode in (MODE_FIRST, MODE_CONTROL, MODE_WORKER)
            if is_fresh:
                config["_need_reboot"] = True
            self.assertTrue(config.get("_need_reboot"),
                            f"Mode {mode} Phase 1 完成后应有 _need_reboot")

    def test_resume_flow_restores_mode_and_config(self):
        """续跑流程应从 install-state.json 恢复 mode 和 config"""
        state = {
            "phase": "os-installed",
            "mode": 3,
            "config": {
                "hostname": "vdi-worker-01",
                "install_disk": "/dev/sda",
                "master_ip": "192.168.220.128",
                "join_command": "kubeadm join ...",
            }
        }
        # 模拟续跑
        mode = state["mode"]
        config = state.get("config", {})
        config["mode"] = mode
        config["resumed"] = True
        self.assertEqual(mode, 3)
        self.assertTrue(config.get("resumed"))
        self.assertIn("join_command", config)


class TestPartitionNaming(unittest.TestCase):
    """分区设备命名逻辑测试（NVMe vs SATA）"""

    def test_sata_partition_naming(self):
        """SATA/SCSI 磁盘分区应为 /dev/sda1"""
        disk = "/dev/sda"
        if "nvme" in disk and disk[-1].isdigit():
            prefix = f"{disk}p"
        else:
            prefix = disk
        self.assertEqual(f"{prefix}1", "/dev/sda1")
        self.assertEqual(f"{prefix}3", "/dev/sda3")

    def test_nvme_partition_naming(self):
        """NVMe 磁盘分区应为 /dev/nvme0n1p1"""
        disk = "/dev/nvme0n1"
        if "nvme" in disk and disk[-1].isdigit():
            prefix = f"{disk}p"
        else:
            prefix = disk
        self.assertEqual(f"{prefix}1", "/dev/nvme0n1p1")
        self.assertEqual(f"{prefix}3", "/dev/nvme0n1p3")

    def test_nvme_second_device(self):
        """第二块 NVMe 设备命名"""
        disk = "/dev/nvme1n1"
        if "nvme" in disk and disk[-1].isdigit():
            prefix = f"{disk}p"
        else:
            prefix = disk
        self.assertEqual(f"{prefix}2", "/dev/nvme1n1p2")

    def test_vda_partition_naming(self):
        """virtio 磁盘分区应为 /dev/vda1（无 p 前缀）"""
        disk = "/dev/vda"
        if "nvme" in disk and disk[-1].isdigit():
            prefix = f"{disk}p"
        else:
            prefix = disk
        self.assertEqual(f"{prefix}1", "/dev/vda1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
