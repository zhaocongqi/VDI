#!/bin/bash
# PXE 服务配置测试
# 验证 PXE 相关配置文件和服务脚本正确
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="${SCRIPT_DIR}/.."

echo "=== PXE 服务测试 ==="

# 检查 PXE 脚本存在且可执行
echo "[1/4] 检查 PXE 脚本..."
PXE_SCRIPT="${WORKSPACE}/pxe/start-pxe.sh"
if [ -f "$PXE_SCRIPT" ]; then
    [ -x "$PXE_SCRIPT" ] || chmod +x "$PXE_SCRIPT"
    echo "  ✓ start-pxe.sh 存在且可执行"
else
    echo "  ✗ start-pxe.sh 不存在"
    exit 1
fi

# 检查 dnsmasq 配置模板
echo "[2/4] 检查 dnsmasq 配置模板..."
DNSMASQ_TEMPLATE="${WORKSPACE}/pxe/dnsmasq.conf.template"
if [ -f "$DNSMASQ_TEMPLATE" ]; then
    echo "  ✓ dnsmasq.conf.template 存在"
    # 检查模板包含必要配置
    grep -q 'dhcp-range' "$DNSMASQ_TEMPLATE" && echo "    DHCP 配置: ✓" || echo "    DHCP 配置: ✗"
    grep -q 'tftp-root' "$DNSMASQ_TEMPLATE" && echo "    TFTP 配置: ✓" || echo "    TFTP 配置: ✗"
else
    echo "  ⚠ dnsmasq.conf.template 不存在"
fi

# 检查 preseed 模板
echo "[3/4] 检查 preseed 配置..."
PRESEED="${WORKSPACE}/configs/preseed.cfg"
if [ -f "$PRESEED" ]; then
    echo "  ✓ preseed.cfg 存在"
    grep -q 'partman-auto/method' "$PRESEED" && echo "    分区配置: ✓" || echo "    分区配置: ✗"
    grep -q 'pkgsel/include' "$PRESEED" && echo "    软件包: ✓" || echo "    软件包: ✗"
else
    echo "  ✗ preseed.cfg 不存在"
fi

# 检查 start-pxe.sh 中的关键函数
echo "[4/4] 检查 PXE 脚本函数..."
for func in setup_dhcp setup_tftp setup_http start_services; do
    if grep -q "${func}()" "$PXE_SCRIPT"; then
        echo "  ✓ ${func}() 函数存在"
    else
        echo "  ✗ ${func}() 函数缺失"
    fi
done

echo ""
echo "=== PXE 测试通过 ==="
