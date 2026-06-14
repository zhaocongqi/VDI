"""config_generator 单元测试"""
import os
import re
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tui"))

from backend.config_generator import ConfigGenerator


class TestInstallKeyGeneration(unittest.TestCase):
    def test_generate_install_key_creates_24_char_file(self):
        tmp = tempfile.mkdtemp()
        gen = ConfigGenerator(output_dir=tmp)
        gen.generate_install_key()
        key_path = os.path.join(tmp, "install.key")
        self.assertTrue(os.path.exists(key_path))
        with open(key_path) as f:
            key = f.read().strip()
        # 24 字符，仅字母数字（URL 安全）
        self.assertEqual(len(key), 24)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9]{24}", key))

    def test_generate_install_key_is_random(self):
        tmp1 = tempfile.mkdtemp()
        tmp2 = tempfile.mkdtemp()
        k1 = ConfigGenerator(output_dir=tmp1)
        k2 = ConfigGenerator(output_dir=tmp2)
        k1.generate_install_key()
        k2.generate_install_key()
        with open(os.path.join(tmp1, "install.key")) as f:
            v1 = f.read()
        with open(os.path.join(tmp2, "install.key")) as f:
            v2 = f.read()
        self.assertNotEqual(v1, v2)

    def test_generate_bootstrap_includes_install_key(self):
        """bootstrap 模式 generate() 应同时生成 install.key"""
        tmp = tempfile.mkdtemp()
        gen = ConfigGenerator(output_dir=tmp)
        gen.generate(2, {
            "mode": 2,
            "node_ip": "192.168.220.128",
            "hostname": "vdi-node-01",
            "role": "master",
            "vip": "192.168.220.100",
            "vip_interface": "ens160",
            "pod_cidr": "10.16.0.0/16",
            "svc_cidr": "10.96.0.0/12",
            "k8s_version": "v1.34.3",
            "longhorn_disk": "/dev/sdb",
            "longhorn_data_dir": "/var/lib/longhorn",
        })
        self.assertTrue(os.path.exists(os.path.join(tmp, "install.key")))


if __name__ == "__main__":
    unittest.main()
