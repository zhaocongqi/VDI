#!/bin/bash
set -euo pipefail

# 安装 VDI 发现服务：拷贝 server.py，部署 systemd unit，启动
LOG_TAG="[vdi-discovery]"

echo "$LOG_TAG 安装发现服务..."

# 1. 定位 server.py（ISO 内或源码）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_SRC=""
for _s in "${SCRIPT_DIR}/server.py" "/cdrom/scripts/deploy/discovery/server.py" "/opt/vdi/discovery/server.py"; do
    if [ -f "$_s" ]; then
        SERVER_SRC="$_s"
        break
    fi
done

if [ -z "$SERVER_SRC" ]; then
    echo "$LOG_TAG 错误: server.py 未找到"
    exit 1
fi

# 2. 部署文件
mkdir -p /opt/vdi/discovery
cp "$SERVER_SRC" /opt/vdi/discovery/server.py
chmod +x /opt/vdi/discovery/server.py

# 3. 部署 systemd unit
UNIT_SRC=""
for _u in "${SCRIPT_DIR}/vdi-discovery.service" "/cdrom/scripts/deploy/discovery/vdi-discovery.service"; do
    if [ -f "$_u" ]; then
        UNIT_SRC="$_u"
        break
    fi
done
if [ -n "$UNIT_SRC" ]; then
    cp "$UNIT_SRC" /etc/systemd/system/vdi-discovery.service
    systemctl daemon-reload
    systemctl enable vdi-discovery
    systemctl restart vdi-discovery
    sleep 2
    if systemctl is-active --quiet vdi-discovery; then
        echo "$LOG_TAG 发现服务已启动 (0.0.0.0:8090)"
    else
        echo "$LOG_TAG 警告: 发现服务启动失败，查看 journalctl -u vdi-discovery"
        exit 1
    fi
else
    echo "$LOG_TAG 错误: vdi-discovery.service 未找到"
    exit 1
fi
