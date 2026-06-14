"""配置文件生成器

将 TUI 收集的配置参数转换为 deploy/env-config.sh、hosts、inventory.yaml 等文件。
"""
import json
import os
import secrets
import logging

logger = logging.getLogger("vdi-installer")


class ConfigGenerator:
    """配置文件生成器"""

    def __init__(self, output_dir="/etc/vdi"):
        self.output_dir = output_dir
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except PermissionError:
            self.output_dir = os.path.expanduser("~/vdi-config")
            os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, mode, config):
        """根据模式和配置生成所有配置文件

        Args:
            mode: 部署模式 (1=Master, 2=Worker)
            config: TUI 收集的配置字典
        """
        config["mode"] = mode

        # 生成 env-config.sh（所有模式）
        self._generate_env_config(config)
        logger.info("env-config.sh 已生成")

        # 生成 install-state.json（所有模式，os-install 脚本依赖此文件）
        self._generate_install_state(mode, config)
        logger.info("install-state.json 已生成")

        # Master 模式专属
        if mode == 1:
            self._generate_hosts(config)
            logger.info("hosts 已生成")

            self._generate_inventory(config)
            logger.info("inventory.yaml 已生成")

            self._generate_kk_config(config)
            logger.info("config.yaml 已生成")

            self.generate_install_key()
            logger.info("install-key 已生成")

    def generate_install_key(self):
        """生成一次性 install-key（24 字符随机），写入 output_dir/install.key"""
        import string
        alphabet = string.ascii_letters + string.digits
        key = "".join(secrets.choice(alphabet) for _ in range(24))
        path = os.path.join(self.output_dir, "install.key")
        with open(path, "w") as f:
            f.write(key)
        os.chmod(path, 0o600)
        return key

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

# ── OS 安装配置（Mode 1 专用）──
INSTALL_DISK="{config.get('install_disk', '')}"
PARTITION_SCHEME="{config.get('partition_scheme', 'auto')}"
SWAP_SIZE="{config.get('swap_size', '8G')}"
INSTALL_HOSTNAME="{config.get('hostname', 'vdi-node-01')}"

# ── KubeVirt 配置 ──
KUBEVIRT_VERSION="v1.5.0"
CDI_VERSION="v1.61.0"

# ── NTP 服务器 ──
NTP_SERVER="ntp.aliyun.com"

# ── 配置目录（TUI 生成的 inventory.yaml / config.yaml / hosts 在此）──
VDI_CONFIG_DIR="{self.output_dir}"

# ── Ansible 清单文件 ──
ANSIBLE_HOSTS_FILE="{self.output_dir}/hosts"

# ── 离线环境变量（自动检测，bundle 优先匹配 ISO 实际结构）──
if [ -z "${{OFFLINE_BASE:-}}" ]; then
    for _candidate in /cdrom/bundle /mnt/iso/bundle /cdrom/offline /mnt/iso/offline; do
        if [ -d "$_candidate" ]; then
            export OFFLINE_BASE="$_candidate"
            break
        fi
    done
fi

if [ -n "${{OFFLINE_BASE:-}}" ]; then
    export OFFLINE_BINARIES="${{OFFLINE_BASE}}/binaries"
    export OFFLINE_IMAGES="${{OFFLINE_BASE}}/images"
    export OFFLINE_CHARTS="${{OFFLINE_BASE}}/charts"
    export OFFLINE_MANIFESTS="${{OFFLINE_BASE}}/k8s-manifests"
    export OFFLINE_PACKAGES="${{OFFLINE_BASE}}/packages/deb"
    export PATH="${{OFFLINE_BINARIES}}:${{PATH}}"
fi

echo "[env-config] loaded OFFLINE_BASE=${{OFFLINE_BASE:-none}}"
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
        """生成 KubeKey v4 inventory.yaml（kind: Inventory，节点列表+角色分组）。

        v4 的 hosts 是 dict（键为主机名），每个含 connector + internal_ipv4；
        groups 用 Kubespray 风格的 kube_control_plane/etcd/kube_worker。
        """
        node_ip = config.get("node_ip", "127.0.0.1")
        hostname = config.get("hostname", "vdi-node-01")
        role = config.get("role", "master")
        ssh_user = config.get("ssh_user", "root")
        ssh_pass = config.get("ssh_password", "vdi")
        # master 角色进 control_plane + etcd；worker 只进 worker
        if role == "master":
            cp_block = f"        - {hostname}"
            worker_block = "        []"
            etcd_block = f"        - {hostname}"
        else:
            cp_block = "        []"
            worker_block = f"        - {hostname}"
            etcd_block = "        []"
        content = f"""apiVersion: kubekey.kubesphere.io/v1
kind: Inventory
metadata:
  name: vdi-cluster
spec:
  hosts:
    {hostname}:
      connector:
        type: ssh
        host: {node_ip}
        port: 22
        user: {ssh_user}
        password: "{ssh_pass}"
      internal_ipv4: {node_ip}
  groups:
    k8s_cluster:
      groups:
        - kube_control_plane
        - kube_worker
    kube_control_plane:
      hosts:
{cp_block}
    kube_worker:
      hosts:
{worker_block}
    etcd:
      hosts:
{etcd_block}
"""
        path = os.path.join(self.output_dir, "inventory.yaml")
        with open(path, "w") as f:
            f.write(content)

    def _generate_kk_config(self, config):
        """生成 KubeKey v4 config.yaml（kind: Config，集群级配置）。

        v4 采用 Config + Inventory 分离设计：
        - config.yaml（-c）：版本/CRI/CNI/存储/DNS 等集群级配置
        - inventory.yaml（-i）：节点列表与角色分组
        命令：kk create cluster -c config.yaml -i inventory.yaml
        """
        content = f"""apiVersion: kubekey.kubesphere.io/v1
kind: Config
spec:
  zone: ""
  kubernetes:
    kube_version: {config.get('k8s_version', 'v1.34.3')}
    helm_version: v3.18.5
    sandbox_image:
      tag: "3.10.1"
    control_plane_endpoint:
      # local: 单节点 bootstrap（control plane 解析为 127.0.0.1）
      # kube_vip: HA（kube-vip 抢 VIP，后续 HA 阶段切换）
      type: local
      host: lb.kubesphere.local
      port: 6443
  etcd:
    etcd_version: v3.6.5
  cri:
    container_manager: containerd
  cni:
    # 留空跳过 CNI 安装，后续手动部署 Kube-OVN
    type: ""
  storage_class:
    local:
      # 不装默认存储，后续手动部署 Longhorn
      enabled: false
  dns:
    coredns:
      image:
        tag: v1.12.1
    nodelocaldns:
      enabled: true
      image:
        tag: 1.26.4
  image_registry:
    type: ""
"""
        path = os.path.join(self.output_dir, "config.yaml")
        with open(path, "w") as f:
            f.write(content)

    def _generate_install_state(self, mode, config):
        """生成 install-state.json（os-install 脚本和续跑机制的核心输入）"""
        state = {
            "phase": "configuring",
            "mode": mode,
            "config": config,
        }
        path = os.path.join(self.output_dir, "install-state.json")
        with open(path, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.chmod(path, 0o600)
