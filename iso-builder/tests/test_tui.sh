#!/bin/bash
# TUI 安装器冒烟测试
# 验证 Python 模块导入和 whiptail 接口正常
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TUI_DIR="${SCRIPT_DIR}/../tui"

echo "=== TUI 安装器冒烟测试 ==="

# 检查 Python 模块导入
echo "[1/4] 检查 Python 模块导入..."
python3 -c "
import sys
sys.path.insert(0, '${TUI_DIR}')
from screens.welcome import WelcomeScreen
from screens.network_config import NetworkConfigScreen
from screens.cluster_config import ClusterConfigScreen
from screens.confirm import ConfirmScreen
from screens.progress import ProgressScreen
from screens.complete import CompleteScreen
from screens.error import ErrorScreen
from backend.config_generator import ConfigGenerator
from backend.deploy import DeployEngine
from utils.whiptail_wrapper import Whiptail
from utils.validator import validate_ip, validate_cidr, validate_hostname
from utils.logger import setup_logger
from utils.offline import OfflineManager
print('  ✓ 所有模块导入成功')
"

# 检查参数校验
echo "[2/4] 检查参数校验..."
python3 -c "
import sys
sys.path.insert(0, '${TUI_DIR}')
from utils.validator import validate_ip, validate_cidr, validate_hostname

# IP 校验
assert validate_ip('192.168.1.1') == (True, '')
assert validate_ip('999.1.1.1')[0] == False
assert validate_ip('')[0] == False

# CIDR 校验
assert validate_cidr('10.16.0.0/16') == (True, '')
assert validate_cidr('invalid')[0] == False

# 主机名校验
assert validate_hostname('vdi-node-01') == (True, '')
assert validate_hostname('')[0] == False

print('  ✓ 参数校验测试通过')
"

# 检查配置生成器
echo "[3/4] 检查配置生成器..."
python3 -c "
import sys, os, tempfile
sys.path.insert(0, '${TUI_DIR}')
from backend.config_generator import ConfigGenerator

# 使用临时目录
with tempfile.TemporaryDirectory() as tmpdir:
    gen = ConfigGenerator(output_dir=tmpdir)
    config = {
        'node_ip': '192.168.220.128',
        'netmask': '24',
        'gateway': '192.168.220.2',
        'dns': '192.168.220.2',
        'hostname': 'vdi-node-01',
        'vip': '192.168.220.100',
        'vip_interface': 'ens160',
        'pod_cidr': '10.16.0.0/16',
        'svc_cidr': '10.96.0.0/12',
        'k8s_version': 'v1.34.3',
        'longhorn_disk': '/dev/sdb',
        'longhorn_data_dir': '/var/lib/longhorn',
        'longhorn_replicas': '3',
        'role': 'master',
    }
    gen.generate(2, config)

    # 验证文件已生成
    assert os.path.exists(f'{tmpdir}/env-config.sh')
    assert os.path.exists(f'{tmpdir}/hosts')
    assert os.path.exists(f'{tmpdir}/inventory.yaml')
    assert os.path.exists(f'{tmpdir}/config.yaml')

    # 验证 env-config.sh 内容
    with open(f'{tmpdir}/env-config.sh') as f:
        content = f.read()
        assert '192.168.220.100' in content  # VIP
        assert '10.16.0.0/16' in content     # Pod CIDR
        assert 'OFFLINE_BASE' in content      # 离线变量

    print('  ✓ 配置生成器测试通过')
"

# 检查 whiptail 可用性
echo "[4/4] 检查 whiptail..."
if command -v whiptail &>/dev/null; then
    echo "  ✓ whiptail 已安装"
else
    echo "  ⚠ whiptail 未安装（TUI 需要）"
fi

echo ""
echo "=== TUI 测试通过 ==="
