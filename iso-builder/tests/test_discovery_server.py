"""发现服务单元测试（Python 标准库 unittest，无外部依赖）"""
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.request import urlopen
from urllib.error import HTTPError

# 让测试能 import deploy/discovery/server.py
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, os.path.join(_REPO, "deploy", "discovery"))

import server


def _start_server(config_dir, install_key="", kubeadm_runner=None):
    """在后台线程起一个测试用 discovery server，返回 (server, port)"""
    srv = server.DiscoveryServer(
        config_dir=config_dir,
        install_key=install_key,
        kubeadm_runner=kubeadm_runner or mock.MagicMock(),
        port=0,  # 随机可用端口
    )
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    port = srv.httpd.server_address[1]
    return srv, port


def _get(port, path):
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return r.status, r.read().decode()


class TestHealthAndClusterInfo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "env-config.sh"), "w") as f:
            f.write('VIP="192.168.220.100"\n')
            f.write('POD_CIDR="10.16.0.0/16"\n')
            f.write('SVC_CIDR="10.96.0.0/12"\n')
            f.write('K8S_VERSION="v1.34.3"\n')
            f.write('VIP_INTERFACE="ens160"\n')

    def test_healthz(self):
        srv, port = _start_server(self.tmp)
        try:
            status, body = _get(port, "/healthz")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertIn("status", data)
        finally:
            srv.shutdown()

    def test_cluster_info_returns_global_params(self):
        srv, port = _start_server(self.tmp)
        try:
            status, body = _get(port, "/cluster-info")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["vip"], "192.168.220.100")
            self.assertEqual(data["pod_cidr"], "10.16.0.0/16")
            self.assertEqual(data["svc_cidr"], "10.96.0.0/12")
            self.assertEqual(data["k8s_version"], "v1.34.3")
            self.assertEqual(data["vip_interface"], "ens160")
        finally:
            srv.shutdown()


class TestInstallKeyAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "env-config.sh"), "w") as f:
            f.write('VIP="192.168.220.100"\n')

    def test_cp_join_without_key_returns_403(self):
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/cp-join", timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()

    def test_cp_join_with_wrong_key_returns_403(self):
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/cp-join?key=wrong", timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()

    def test_cp_join_with_correct_key_not_403(self):
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/cp-join?key=secret123", timeout=5)
            self.assertNotEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()

    def test_ca_without_key_returns_403(self):
        srv, port = _start_server(self.tmp, install_key="secret123")
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/ca", timeout=5)
            self.assertEqual(ctx.exception.code, 403)
        finally:
            srv.shutdown()


class TestTokenIssuance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "env-config.sh"), "w") as f:
            f.write('VIP="192.168.220.100"\n')

    def test_join_token_parses_kubeadm_output(self):
        fake_output = ("kubeadm join 192.168.220.100:6443 "
                       "--token abc123.abcdef0123456789 "
                       "--discovery-token-ca-cert-hash sha256:deadbeef\n")
        runner = mock.MagicMock(return_value=(0, fake_output))
        srv, port = _start_server(self.tmp, kubeadm_runner=runner)
        try:
            status, body = _get(port, "/join-token")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["token"], "abc123.abcdef0123456789")
            self.assertEqual(data["ca_cert_hash"], "sha256:deadbeef")
            self.assertIn("192.168.220.100:6443", data["join_command"])
            runner.assert_called_once()
            called_args = runner.call_args[0][0]
            self.assertEqual(called_args[0], "token")
            self.assertEqual(called_args[1], "create")
        finally:
            srv.shutdown()

    def test_cp_join_uses_upload_certs(self):
        fake_output = ("[upload-certs] Storing the certificates...\n"
                       "W0514 something\n"
                       "[upload-certs] Using certificate key:\n"
                       "aabbccddeeff00112233\n")
        runner = mock.MagicMock(return_value=(0, fake_output))
        srv, port = _start_server(self.tmp, install_key="key123", kubeadm_runner=runner)
        try:
            status, body = _get(port, "/cp-join?key=key123")
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["certificate_key"], "aabbccddeeff00112233")
            self.assertIn("--control-plane", data["join_command"])
            self.assertIn("--certificate-key aabbccddeeff00112233", data["join_command"])
        finally:
            srv.shutdown()

    def test_join_token_failure_returns_500(self):
        runner = mock.MagicMock(return_value=(1, "kubeadm error: not initialized"))
        srv, port = _start_server(self.tmp, kubeadm_runner=runner)
        try:
            with self.assertRaises(HTTPError) as ctx:
                urlopen(f"http://127.0.0.1:{port}/join-token", timeout=5)
            self.assertEqual(ctx.exception.code, 500)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
