#!/bin/bash
set -euo pipefail

# PXE 服务启动脚本
# [部署时] 在 TUI 模式 4 中调用，配置并启动 DHCP/TFTP/HTTP 服务
# 用法: bash start-pxe.sh [dhcp|tftp|http|start|all]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PXE_ROOT="/srv/pxe"
TFTP_ROOT="/srv/tftp"
HTTP_ROOT="/srv/http"
LOG_DIR="/var/log/vdi-deploy"

mkdir -p "$PXE_ROOT" "$TFTP_ROOT" "$HTTP_ROOT" "$LOG_DIR"

# 配置文件路径（由 TUI 生成）
ENV_CONFIG="/etc/vdi/env-config.sh"
[ -f "$ENV_CONFIG" ] && source "$ENV_CONFIG"

# 从 TUI 配置读取参数
NODE_IP="${NODE_IP:-$(hostname -I | awk '{print $1}')}"
DHCP_START="${DHCP_START:-192.168.220.200}"
DHCP_END="${DHCP_END:-192.168.220.250}"
VIP="${VIP:-192.168.220.100}"
INTERFACE="${VIP_INTERFACE:-$(ip -json route show default | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["dev"])' 2>/dev/null || echo eth0)}"

SERVICE="${1:-all}"

# ========== DHCP 服务 (dnsmasq) ==========
setup_dhcp() {
    echo ">>> 配置 DHCP 服务 (dnsmasq)"

    cat > /etc/dnsmasq.d/vdi-pxe.conf <<EOF
# VDI PXE DHCP/TFTP 配置
# 由 TUI 安装器自动生成

# 监听接口
interface=${INTERFACE}
bind-interfaces

# DHCP 配置
dhcp-range=${DHCP_START},${DHCP_END},255.255.255.0,12h
dhcp-boot=pxelinux.0
dhcp-option=3,${NODE_IP}
dhcp-option=6,${NODE_IP}

# TFTP 配置
enable-tftp
tftp-root=${TFTP_ROOT}

# 日志
log-dhcp
log-queries
log-facility=${LOG_DIR}/dnsmasq.log
EOF

    echo "    dnsmasq 配置已生成: /etc/dnsmasq.d/vdi-pxe.conf"
}

# ========== TFTP 服务 ==========
setup_tftp() {
    echo ">>> 配置 TFTP 服务"

    # 复制 PXE 引导文件
    if [ -d /usr/lib/PXELINUX ]; then
        cp /usr/lib/PXELINUX/pxelinux.0 "${TFTP_ROOT}/"
    elif [ -d /usr/lib/syslinux ]; then
        cp /usr/lib/syslinux/pxelinux.0 "${TFTP_ROOT}/" 2>/dev/null || true
    fi

    # 复制附加引导文件
    for file in ldlinux.c32 libcom32.c32 libutil.c32 menu.c32; do
        for dir in /usr/lib/syslinux/modules/bios /usr/lib/syslinux; do
            if [ -f "${dir}/${file}" ]; then
                cp "${dir}/${file}" "${TFTP_ROOT}/" 2>/dev/null || true
                break
            fi
        done
    done

    # 复制内核和 initrd（从 ISO/cdrom）
    if [ -d /cdrom/casper ]; then
        cp /cdrom/casper/vmlinuz "${TFTP_ROOT}/"
        cp /cdrom/casper/initrd "${TFTP_ROOT}/"
    fi

    # 创建 pxelinux 配置目录
    mkdir -p "${TFTP_ROOT}/pxelinux.cfg"

    cat > "${TFTP_ROOT}/pxelinux.cfg/default" <<EOF
DEFAULT install
PROMPT 0
TIMEOUT 30

LABEL install
    MENU LABEL ^安装 VDI Worker 节点
    KERNEL /vmlinuz
    APPEND initrd=/initrd boot=casper auto=true url=http://${NODE_IP}:8080/preseed.cfg text ---

LABEL shell
    MENU LABEL ^进入 Live Shell
    KERNEL /vmlinuz
    APPEND initrd=/initrd boot=casper text ---
EOF

    echo "    TFTP 根目录: ${TFTP_ROOT}"
    echo "    引导文件已配置"
}

# ========== HTTP 服务 ==========
setup_http() {
    echo ">>> 配置 HTTP 服务"

    # 将 ISO 内容通过 HTTP 提供
    if [ -d /cdrom ]; then
        ln -sf /cdrom "${HTTP_ROOT}/iso" 2>/dev/null || true
    fi

    # 生成 preseed.cfg
    cat > "${HTTP_ROOT}/preseed.cfg" <<'PRESEED'
# Ubuntu 自动安装配置（由 PXE 服务自动生成）
d-i debian-installer/locale string zh_CN.UTF-8
d-i keyboard-configuration/layoutcode string cn
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string vdi-worker
d-i netcfg/get_domain string

# 用户配置
d-i passwd/root-login boolean true
d-i passwd/root-password password vdi
d-i passwd/root-password-again password vdi
d-i passwd/user-fullname string VDI Worker
d-i passwd/username string vdi
d-i passwd/user-password password vdi
d-i passwd/user-password-again password vdi
d-i user-setup/allow-password-weak boolean true

# 时区
d-i time/zone string Asia/Shanghai
d-i clock-setup/ntp boolean true

# 分区（自动）
d-i partman-auto/method string regular
d-i partman-auto/choose_recipe select atomic
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

# 软件包
d-i pkgsel/include string openssh-server python3 chrony curl wget jq
d-i pkgsel/upgrade select none

# 完成安装后执行 Worker 加入脚本
d-i preseed/late_command string \
    in-target wget -O /tmp/worker-setup.sh http://NODE_IP:8080/worker-setup.sh; \
    in-target chmod +x /tmp/worker-setup.sh; \
    in-target bash /tmp/worker-setup.sh

d-i finish-install/reboot_in_progress note
PRESEED

    # 替换 NODE_IP 占位符
    sed -i "s/NODE_IP/${NODE_IP}/g" "${HTTP_ROOT}/preseed.cfg"

    # 生成 Worker 加入脚本
    cat > "${HTTP_ROOT}/worker-setup.sh" <<'WORKEREOF'
#!/bin/bash
# Worker 节点安装后自动执行脚本
set -euo pipefail

echo ">>> Worker 节点安装后初始化"

# 配置离线环境
if [ -d /cdrom/offline ]; then
    export OFFLINE_BASE="/cdrom/offline"
    export PATH="${OFFLINE_BASE}/binaries:${PATH}"
fi

# 从 PXE Server 获取 join 命令
echo ">>> 获取集群加入命令"
JOIN_CMD=$(curl -sf http://WORKER_JOIN_URL/join-command.sh 2>/dev/null || echo "")

if [ -n "$JOIN_CMD" ]; then
    echo ">>> 执行加入集群"
    bash -c "$JOIN_CMD"
else
    echo ">>> 警告: 无法获取 join 命令，请手动加入集群"
fi

# 回报状态
curl -sf "http://NODE_IP:8080/report?host=$(hostname)&status=complete" 2>/dev/null || true
WORKEREOF

    sed -i "s/NODE_IP/${NODE_IP}/g" "${HTTP_ROOT}/worker-setup.sh"

    echo "    HTTP 根目录: ${HTTP_ROOT}"
    echo "    preseed.cfg 已生成"
}

# ========== 启动服务 ==========
start_services() {
    echo ">>> 启动 PXE 服务"

    # 停止已有服务
    systemctl stop dnsmasq 2>/dev/null || true
    pkill -f "python3 -m http.server" 2>/dev/null || true

    # 启动 dnsmasq (DHCP + TFTP)
    echo "    启动 dnsmasq (DHCP + TFTP)..."
    dnsmasq --conf-dir=/etc/dnsmasq.d --keep-in-foreground &
    DNSMASQ_PID=$!
    echo "    dnsmasq PID: ${DNSMASQ_PID}"

    # 启动 HTTP 服务
    echo "    启动 HTTP 服务 (端口 8080)..."
    cd "${HTTP_ROOT}"
    python3 -m http.server 8080 &
    HTTP_PID=$!
    echo "    HTTP PID: ${HTTP_PID}"

    # 生成 join 命令
    echo ">>> 从 Master 获取 Join 命令"
    JOIN_COMMAND=""
    if command -v kubectl &>/dev/null; then
        JOIN_COMMAND=$(kubeadm token create --print-join-command 2>/dev/null || echo "")
    fi

    if [ -n "$JOIN_COMMAND" ]; then
        echo "#!/bin/bash" > "${HTTP_ROOT}/join-command.sh"
        echo "$JOIN_COMMAND" >> "${HTTP_ROOT}/join-command.sh"
        chmod +x "${HTTP_ROOT}/join-command.sh"
        echo "    join-command.sh 已生成"
    fi

    # 保存环境信息
    cat > "${HTTP_ROOT}/env-config.sh" <<EOF
export VIP="${VIP}"
export NODE_IP="${NODE_IP}"
export OFFLINE_BASE="/cdrom/offline"
EOF

    echo ""
    echo "============================================"
    echo "  PXE 服务器已启动"
    echo "============================================"
    echo "  DHCP 范围: ${DHCP_START} - ${DHCP_END}"
    echo "  TFTP 目录: ${TFTP_ROOT}"
    echo "  HTTP 端口: http://${NODE_IP}:8080"
    echo "  dnsmasq PID: ${DNSMASQ_PID}"
    echo "  HTTP PID: ${HTTP_PID}"
    echo ""
    echo "  Worker 节点设置 PXE 网络启动即可自动安装"
    echo "  日志: ${LOG_DIR}/dnsmasq.log"
    echo "============================================"

    # 保存 PID 文件
    echo "${DNSMASQ_PID}" > "${PXE_ROOT}/dnsmasq.pid"
    echo "${HTTP_PID}" > "${PXE_ROOT}/http.pid"

    # 等待（前台运行）
    echo ">>> PXE 服务运行中，按 Ctrl+C 停止"
    wait
}

# ========== 主入口 ==========
case "$SERVICE" in
    dhcp)  setup_dhcp ;;
    tftp)  setup_tftp ;;
    http)  setup_http ;;
    start) start_services ;;
    all)
        setup_dhcp
        setup_tftp
        setup_http
        start_services
        ;;
    *)
        echo "用法: $0 [dhcp|tftp|http|start|all]"
        exit 1
        ;;
esac
