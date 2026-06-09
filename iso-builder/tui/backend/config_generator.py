"""配置文件生成器

将 TUI 收集的配置参数转换为 deploy/env-config.sh、hosts、inventory.yaml 等文件。
"""
import os
import logging

logger = logging.getLogger("vdi-installer")


class ConfigGenerator:
    """配置文件生成器"""

    def __init__(self, output_dir="/etc/vdi"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, mode, config):
        """根据模式和配置生成所有配置文件

        Args:
            mode: 部署模式 (1-4)
            config: TUI 收集的配置字典
        """
        config["mode"] = mode

        # 生成 env-config.sh
        self._generate_env_config(config)
        logger.info("env-config.sh 已生成")

        # 生成 hosts 文件（模式 1/2/4）
        if mode in (1, 2, 4):
            self._generate_hosts(config)
            logger.info("hosts 已生成")

        # 生成 KubeKey inventory.yaml（模式 1/2）
        if mode in (1, 2):
            self._generate_inventory(config)
            logger.info("inventory.yaml 已生成")

        # 生成 KubeKey config.yaml（模式 1/2）
        if mode in (1, 2):
            self._generate_kk_config(config)
            logger.info("config.yaml 已生成")

        # 生成 PXE 配置（模式 4）
        if mode == 4:
            self._generate_pxe_config(config)
            logger.info("PXE 配置已生成")

    def _generate_env_config(self, config):
        """生成 env-config.sh"""
        content = f"""#!/usr/bin/env bash
# ============================================================
# VDI 集群部署 — 共享环境配置（由 TUI 安装器自动生成）
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# ============================================================

# ── SSH / Ansible 用户 ──
ANSIBLE_USER="root"

# ── K8s 集群版本 ──
K8S_VERSION="{config.get('k8s_version', 'v1.34.3')}"
KUBEKEY_VERSION="v4.0.4"

# ── 网络配置 ──
SVC_CIDR="{config.get('svc_cidr', '10.96.0.0/12')}"
POD_CIDR="{config.get('pod_cidr', '10.16.0.0/16')}"
JOIN_CIDR="100.64.0.0/16"

# ── kube-vip 配置 ──
VIP="{config.get('vip', '192.168.220.100')}"
VIP_INTERFACE="{config.get('vip_interface', 'ens160')}"

# ── Longhorn 配置 ──
LONGHORN_DISK="{config.get('longhorn_disk', '/dev/sdb')}"
LONGHORN_DATA_DIR="{config.get('longhorn_data_dir', '/var/lib/longhorn')}"

# ── KubeVirt 配置 ──
KUBEVIRT_VERSION="v1.5.0"
CDI_VERSION="v1.61.0"

# ── NTP 服务器 ──
NTP_SERVER="ntp.aliyun.com"

# ── Ansible 清单文件 ──
ANSIBLE_HOSTS_FILE="{self.output_dir}/hosts"

# ── 离线环境变量（自动检测）──
if [ -z "${{OFFLINE_BASE:-}}" ]; then
    if [ -d /cdrom/offline ]; then
        export OFFLINE_BASE="/cdrom/offline"
    elif [ -d /mnt/iso/offline ]; then
        export OFFLINE_BASE="/mnt/iso/offline"
    fi
fi

if [ -n "${{OFFLINE_BASE:-}}" ]; then
    export OFFLINE_BINARIES="${{OFFLINE_BASE}}/binaries"
    export OFFLINE_IMAGES="${{OFFLINE_BASE}}/images"
    export OFFLINE_CHARTS="${{OFFLINE_BASE}}/charts"
    export OFFLINE_MANIFESTS="${{OFFLINE_BASE}}/k8s-manifests"
    export OFFLINE_PACKAGES="${{OFFLINE_BASE}}/packages/deb"
    export PATH="${{OFFLINE_BINARIES}}:${{PATH}}"
fi

echo "[env-config] loaded"
"""
        path = os.path.join(self.output_dir, "env-config.sh")
        with open(path, "w") as f:
            f.write(content)
        os.chmod(path, 0o755)

    def _generate_hosts(self, config):
        """生成 Ansible hosts 文件"""
        node_ip = config.get("node_ip", "127.0.0.1")
        content = f"""# VDI 集群节点清单（由 TUI 安装器自动生成）
[K8s]
{node_ip}

[K8s-control]
{node_ip}

[K8s:vars]
ansible_user=root
ansible_become=true
ansible_become_method=sudo
ansible_python_interpreter=/usr/bin/python3
"""
        path = os.path.join(self.output_dir, "hosts")
        with open(path, "w") as f:
            f.write(content)

    def _generate_inventory(self, config):
        """生成 KubeKey inventory.yaml"""
        node_ip = config.get("node_ip", "127.0.0.1")
        hostname = config.get("hostname", "vdi-node-01")
        content = f"""apiVersion: kubekey.kubesphere.io/v1alpha2
kind: Inventory
metadata:
  name: vdi-cluster
spec:
  hosts:
    - name: {hostname}
      address: {node_ip}
      internalAddress: {node_ip}
      user: root
      password: "vdi"
  groups:
    - name: etcd
      members:
        - {hostname}
    - name: control-plane
      members:
        - {hostname}
    - name: worker
      members: []
"""
        path = os.path.join(self.output_dir, "inventory.yaml")
        with open(path, "w") as f:
            f.write(content)

    def _generate_kk_config(self, config):
        """生成 KubeKey config.yaml"""
        content = f"""apiVersion: kubekey.kubesphere.io/v1alpha2
kind: Cluster
metadata:
  name: vdi-cluster
spec:
  version: {config.get('k8s_version', 'v1.34.3')}
  containerManager: containerd
  network:
    plugin: none
    kubePodsCIDR: {config.get('pod_cidr', '10.16.0.0/16')}
    kubeServiceCIDR: {config.get('svc_cidr', '10.96.0.0/12')}
  etcd:
    version: v3.6.5
  registry:
    privateRegistry: ""
  addons: []
"""
        path = os.path.join(self.output_dir, "config.yaml")
        with open(path, "w") as f:
            f.write(content)

    def _generate_pxe_config(self, config):
        """生成 PXE 相关配置文件"""
        pxe_dir = os.path.join(self.output_dir, "pxe")
        os.makedirs(pxe_dir, exist_ok=True)

        # dnsmasq 配置
        node_ip = config.get("node_ip", "192.168.220.100")
        dhcp_start = config.get("dhcp_start", "192.168.220.200")
        dhcp_end = config.get("dhcp_end", "192.168.220.250")

        dnsmasq_content = f"""# dnsmasq PXE 配置（由 TUI 安装器自动生成）
interface=eth0
bind-interfaces

# DHCP 配置
dhcp-range={dhcp_start},{dhcp_end},255.255.255.0,12h
dhcp-boot=pxelinux.0

# TFTP 配置
enable-tftp
tftp-root=/srv/tftp

# 日志
log-dhcp
log-queries
"""
        with open(os.path.join(pxe_dir, "dnsmasq.conf"), "w") as f:
            f.write(dnsmasq_content)

        # pxelinux 配置
        pxelinux_dir = os.path.join(pxe_dir, "pxelinux.cfg")
        os.makedirs(pxelinux_dir, exist_ok=True)

        pxelinux_content = f"""DEFAULT install
PROMPT 0
TIMEOUT 30

LABEL install
    MENU LABEL ^Install VDI Worker
    KERNEL /vmlinuz
    APPEND initrd=/initrd boot=casper auto=true url=http://{node_ip}:8080/preseed.cfg ---
"""
        with open(os.path.join(pxelinux_dir, "default"), "w") as f:
            f.write(pxelinux_content)
