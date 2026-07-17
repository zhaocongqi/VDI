"""VDI Addon 安装任务实现（参考 com_redhat_kdump/service/installation.py）"""
import glob
import os
import uuid
import logging
import subprocess
import shutil
import base64

from pyanaconda.modules.common.task import Task

log = logging.getLogger(__name__)

__all__ = ["VdiInstallationTask"]

_BUNDLE_DIR = "/run/install/repo/bundle/vdi"


class VdiInstallationTask(Task):
    """VDI 平台系统配置与资源部署安装任务。

    在 Anaconda 安装阶段执行，负责：
    - 写入 NetworkManager 网卡配置
    - 配置 SSH root 登录
    - 格式化并挂载数据盘
    - 释放 RKE2 离线资源
    - 生成 RKE2 config.yaml
    - 激活 systemd 服务
    """

    def __init__(self, sysroot, mode, interface, interface2, bond_mode, ip, netmask, gateway, dns, pod_cidr, service_cidr, join_cidr, vip, network_mode, role="server", server_url="", token="", data_disk="auto"):
        """创建安装任务。

        :param sysroot: 目标系统根路径
        :param mode: 网络模式 (single/bond)
        :param interface: 主网卡名
        :param interface2: 备网卡名（bond 模式）
        :param bond_mode: Bond 模式 (active-backup/802.3ad)
        :param ip: 管理 IP（静态模式）
        :param netmask: 子网掩码（如 255.255.255.0）
        :param gateway: 默认网关
        :param dns: DNS 服务器地址
        :param pod_cidr: POD CIDR 地址段
        :param service_cidr: SERVICE CIDR 地址段
        :param join_cidr: JOIN CIDR 地址段
        :param vip: 集群虚拟 IP（静态模式）
        :param network_mode: 网络模式 (dhcp/static)
        :param role: RKE2 角色 (server/agent)
        :param server_url: Agent 模式下 Server URL
        :param token: Agent 模式下加入集群令牌
        :param data_disk: 数据盘 (auto 或设备名)
        """
        super().__init__()
        self._sysroot = sysroot
        self._mode = mode or "single"
        self._interface = interface or ""
        self._interface2 = interface2 or ""
        self._bond_mode = bond_mode or "active-backup"
        self._ip = ip or ""
        self._netmask = netmask or "255.255.255.0"
        self._gateway = gateway or ""
        self._dns = dns or "8.8.8.8"
        self._pod_cidr = pod_cidr or "10.16.0.0/16"
        self._service_cidr = service_cidr or "10.96.0.0/12"
        self._join_cidr = join_cidr or "100.64.0.0/16"
        self._vip = vip or ""
        self._network_mode = network_mode or "dhcp"
        self._role = role or "server"
        self._server_url = server_url or ""
        self._token = token or ""
        self._data_disk = data_disk or "auto"

    @property
    def name(self):
        return "Deploy VDI platform resources and configuration"

    @staticmethod
    def _ensure_dir(path, mode=0o755):
        os.makedirs(path, mode=mode, exist_ok=True)

    def _copy_operator_cr_manifests(self, prefix):
        """将 operator.yaml 拷贝到 RKE2 manifests，CR 拷贝到 /etc/vdi/cr/ 延迟 apply。"""
        manifests_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/server/manifests")
        cr_dir = os.path.join(self._sysroot, "etc/vdi/cr")
        self._ensure_dir(manifests_dir)
        self._ensure_dir(cr_dir)

        src_manifests_dir = os.path.join(_BUNDLE_DIR, "manifests")
        operator_src = os.path.join(src_manifests_dir, f"{prefix}-operator.yaml")
        if os.path.exists(operator_src):
            shutil.copy(operator_src, os.path.join(manifests_dir, f"{prefix}-operator.yaml"))
        else:
            log.warning("[VDI] 未找到 %s-operator.yaml", prefix)

        cr_src = os.path.join(src_manifests_dir, f"{prefix}-cr.yaml")
        if os.path.exists(cr_src):
            shutil.copy(cr_src, os.path.join(cr_dir, f"{prefix}-cr.yaml"))
        else:
            log.warning("[VDI] 未找到 %s-cr.yaml", prefix)

        log.info("[VDI] %s manifest 分流完成（operator→manifests, CR→/etc/vdi/cr/）", prefix)

    def run(self):
        """执行安装任务。"""
        log.info(">>> [VDI] 开始执行 VdiInstallationTask 全量系统配置写入")

        # 1. 网卡与 Bond 持久化写入
        self._write_network_config()

        # 2. SSH Root 登录配置
        self._configure_ssh()

        # 3. 数据盘自动探测、格式化与 fstab 挂载
        self._setup_data_disk()

        # 4. 复制 ISO 离线资源 Bundle 到目标磁盘
        self._extract_bundle_resources()

        # 5. 动态配置并下发 RKE2 config.yaml
        self._write_rke2_config()

        # 6. 动态生成 Kube-OVN HelmChart CRD manifest
        self._write_kube_ovn_manifest()

        # 7. 复制 KubeVirt 静态 manifest（operator + CR）
        self._copy_kubevirt_manifests()

        # 8. 复制 CDI 静态 manifest（operator + CR）
        self._copy_cdi_manifests()

        # 9. kubectl 便捷配置（PATH、KUBECONFIG）
        self._setup_kubectl_convenience()

        # 10. 创建 kubeconfig 延迟拷贝服务（RKE2 首启后补拷 ~/.kube/config）
        self._create_kubeconfig_service()

        # 11. 创建 CR 延迟应用服务（等 CRD 就绪后 apply KubeVirt/CDI CR）
        self._create_cr_apply_service()

        # 12. 创建 systemd wants 链接，激活服务
        self._enable_systemd_services()

        log.info(">>> [VDI] VdiInstallationTask 全部配置下发与释放成功完成！")

    def _netmask_to_cidr(self, netmask):
        """将子网掩码转换为 CIDR 前缀长度（如 255.255.255.0 → 24）。"""
        import ipaddress
        try:
            return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
        except ValueError:
            log.warning("[VDI] 无效子网掩码 '%s'，回退 /24", netmask)
            return 24

    def _build_ipv4_section(self, is_dhcp):
        """构建 [ipv4] 配置段。"""
        if is_dhcp:
            return "[ipv4]\nmethod=auto"
        cidr = self._netmask_to_cidr(self._netmask)
        lines = f"[ipv4]\nmethod=manual\naddresses={self._ip}/{cidr},{self._gateway}"
        if self._dns:
            lines += f"\ndns={self._dns};"
        return lines

    def _write_network_config(self):
        """写入 NetworkManager 网卡配置。"""
        if not self._interface:
            log.warning("[VDI] 未配置有效的主网卡，跳过网络配置写入。")
            return

        conn_dir = os.path.join(self._sysroot, "etc/NetworkManager/system-connections")
        try:
            self._ensure_dir(conn_dir)
        except Exception as e:
            log.error("[VDI] 创建目标网卡配置目录失败: %s", e)
            return

        # 清理原有网卡配置，防止冲突
        for f in os.listdir(conn_dir):
            if f.endswith(".nmconnection"):
                try:
                    os.remove(os.path.join(conn_dir, f))
                except Exception as e:
                    log.warning("[VDI] 删除旧网卡配置 %s 失败: %s", f, e)

        # 清理 Anaconda 装机阶段生成的 ifcfg 残留（与 keyfile bond 配置语义冲突），
        # 确保 NM 以 keyfile 为唯一配置来源（NM 1.32 keyfile 优先于 ifcfg-rh）。
        ifcfg_dir = os.path.join(self._sysroot, "etc/sysconfig/network-scripts")
        if os.path.isdir(ifcfg_dir):
            for f in os.listdir(ifcfg_dir):
                if f.startswith("ifcfg-"):
                    try:
                        os.remove(os.path.join(ifcfg_dir, f))
                        log.debug("[VDI] 删除 ifcfg 残留 %s", f)
                    except Exception as e:
                        log.warning("[VDI] 删除 ifcfg 残留 %s 失败: %s", f, e)

        is_dhcp = (self._network_mode == "dhcp")
        ipv4_section = self._build_ipv4_section(is_dhcp)
        ipv6_section = "[ipv6]\nmethod=disabled"

        if self._mode == "bond" and self._interface2:
            # ----------------- 绑定模式 (Bonding) -----------------
            bond_uuid = str(uuid.uuid4())
            port1_uuid = str(uuid.uuid4())
            port2_uuid = str(uuid.uuid4())

            bond_path = os.path.join(conn_dir, "bond0.nmconnection")
            with open(bond_path, "w") as f:
                f.write(f"""[connection]
id=bond0
uuid={bond_uuid}
type=bond
interface-name=bond0
autoconnect=true
autoconnect-priority=100

[bond]
mode={self._bond_mode}
miimon=100

{ipv4_section}

{ipv6_section}
""")
            os.chmod(bond_path, 0o600)

            for iface, port_uuid in [(self._interface, port1_uuid), (self._interface2, port2_uuid)]:
                port_path = os.path.join(conn_dir, f"{iface}.nmconnection")
                with open(port_path, "w") as f:
                    f.write(f"""[connection]
id={iface}
uuid={port_uuid}
type=ethernet
interface-name={iface}
master={bond_uuid}
slave-type=bond
autoconnect=true
autoconnect-priority=100

[ethernet]

{ipv6_section}
""")
                os.chmod(port_path, 0o600)

            log.info("[VDI] 成功写入 Bond0 网卡绑定配置 (%s + %s, %s)",
                     self._interface, self._interface2, self._network_mode)
        else:
            # ----------------- 单网卡模式 (Single) -----------------
            single_uuid = str(uuid.uuid4())
            single_path = os.path.join(conn_dir, f"{self._interface}.nmconnection")
            with open(single_path, "w") as f:
                f.write(f"""[connection]
id={self._interface}
uuid={single_uuid}
type=ethernet
interface-name={self._interface}
autoconnect=true
autoconnect-priority=100

[ethernet]

{ipv4_section}

{ipv6_section}
""")
            os.chmod(single_path, 0o600)
            log.info("[VDI] 成功写入单网卡配置 %s (%s)", self._interface, self._network_mode)

        # 写入 VDI 内部网络配置文件
        vdi_conf_dir = os.path.join(self._sysroot, "etc/vdi")
        self._ensure_dir(vdi_conf_dir)
        with open(os.path.join(vdi_conf_dir, "network.conf"), "w") as f:
            f.write(f"""# VDI Management Network Config
NETWORK_MODE={self._network_mode}
MODE={self._mode}
INTERFACE={self._interface}
INTERFACE2={self._interface2}
BOND_MODE={self._bond_mode}
IP={self._ip}
NETMASK={self._netmask}
GATEWAY={self._gateway}
DNS={self._dns}
VIP={self._vip}
""")

    def _configure_ssh(self):
        """配置 SSH root 登录。"""
        try:
            sshd_conf_dir = os.path.join(self._sysroot, "etc/ssh/sshd_config.d")
            self._ensure_dir(sshd_conf_dir)
            with open(os.path.join(sshd_conf_dir, "00-vdi-root-login.conf"), "w") as f:
                f.write("PermitRootLogin yes\nPasswordAuthentication yes\nUseDNS no\nGSSAPIAuthentication no\n")
            log.info("[VDI] 成功写入 00-vdi-root-login.conf SSH 配置文件")
        except Exception as e:
            log.error("[VDI] 写入 SSH 配置文件发生错误: %s", e)

    def _is_system_disk(self, dev_name):
        """判断块设备是否为系统盘（包含 LVM PV 或已挂载的根分区）。"""
        partitions = glob.glob(f"/sys/block/{dev_name}/{dev_name}*")
        for part in partitions:
            part_dev = f"/dev/{os.path.basename(part)}"
            try:
                fstype = subprocess.check_output(
                    ["blkid", "-s", "TYPE", "-o", "value", part_dev],
                    stderr=subprocess.DEVNULL
                ).decode().strip()
                if fstype in ("LVM2_member", "ext4", "xfs"):
                    mount_info = subprocess.check_output(
                        ["lsblk", "-no", "MOUNTPOINT", part_dev],
                        stderr=subprocess.DEVNULL
                    ).decode().strip()
                    if mount_info or fstype == "LVM2_member":
                        return True
            except Exception as e:
                log.warning("[VDI] blkid/lsblk 探测 %s 失败: %s", part_dev, e)
        return False

    def _setup_data_disk(self):
        """数据盘自动探测/指定、格式化与 fstab 挂载。"""
        try:
            if self._data_disk and self._data_disk != "auto":
                data_disk_name = os.path.basename(self._data_disk)
                data_dev_path = f"/dev/{data_disk_name}"
                if not os.path.exists(data_dev_path):
                    log.warning("[VDI] 指定数据盘 %s 不存在，回退自动探测", data_dev_path)
                    data_disk_name = None
            else:
                data_disk_name = None

            if not data_disk_name:
                all_block_devs = sorted(glob.glob("/sys/block/vd*")) + sorted(glob.glob("/sys/block/sd*"))
                for dev_path in all_block_devs:
                    dev_name = os.path.basename(dev_path)
                    if not self._is_system_disk(dev_name):
                        data_disk_name = dev_name
                        break

            if not data_disk_name:
                log.warning("[VDI] 未探测到其它物理数据盘，跳过数据盘处理")
                return

            data_dev_path = f"/dev/{data_disk_name}"
            log.info("[VDI] 探测到物理数据盘: %s, 开始格式化...", data_dev_path)
            subprocess.run(["mkfs.ext4", "-F", "-L", "VDI_LH_DEFAULT", data_dev_path], check=True)

            self._ensure_dir(os.path.join(self._sysroot, "var/lib/longhorn"))

            fstab_path = os.path.join(self._sysroot, "etc/fstab")
            longhorn_entry = "LABEL=VDI_LH_DEFAULT /var/lib/longhorn ext4 defaults,noatime,nofail 0 2"
            already_mounted = False
            if os.path.exists(fstab_path):
                with open(fstab_path, "r") as f:
                    already_mounted = "VDI_LH_DEFAULT" in f.read()
            if not already_mounted:
                with open(fstab_path, "a") as f:
                    f.write("\n" + longhorn_entry + "\n")
            log.info("[VDI] 数据盘格式化并成功挂载至 /var/lib/longhorn")
        except Exception as e:
            log.error("[VDI] 数据盘处理发生错误: %s", e)

    def _extract_bundle_resources(self):
        """复制 ISO 离线资源 Bundle 到目标磁盘。"""
        if not os.path.exists(_BUNDLE_DIR):
            log.warning("[VDI] 未在光盘安装源中找到离线资源 bundle/vdi，跳过离线资源释放")
            return

        log.info("[VDI] 发现离线资源 bundle，开始释放...")

        # 拷贝 RKE2 离线镜像 (images)
        target_images_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/agent/images")
        self._ensure_dir(target_images_dir)
        src_images_dir = os.path.join(_BUNDLE_DIR, "images")
        if os.path.exists(src_images_dir):
            for f in os.listdir(src_images_dir):
                if f.endswith(".tar.zst"):
                    src_img = os.path.join(src_images_dir, f)
                    if not os.path.exists(src_img) or os.path.getsize(src_img) == 0:
                        log.warning("[VDI] 跳过空镜像文件: %s", f)
                        continue
                    shutil.copy(src_img, target_images_dir)
        log.info("[VDI] 离线 RKE2 镜像拷贝完成")

        # 拷贝 Helm Charts 和 Manifests
        target_charts_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/server/charts")
        self._ensure_dir(target_charts_dir)
        src_charts_dir = os.path.join(_BUNDLE_DIR, "charts")
        if os.path.exists(src_charts_dir):
            for f in os.listdir(src_charts_dir):
                if f.endswith(".tgz"):
                    shutil.copy(os.path.join(src_charts_dir, f), target_charts_dir)

        target_manifests_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/server/manifests")
        self._ensure_dir(target_manifests_dir)
        src_manifests_dir = os.path.join(_BUNDLE_DIR, "manifests")
        if os.path.exists(src_manifests_dir):
            for f in os.listdir(src_manifests_dir):
                if f.endswith(".yaml"):
                    shutil.copy(os.path.join(src_manifests_dir, f), target_manifests_dir)
        log.info("[VDI] 离线 Helm Charts & Manifests 拷贝完成")

        # 解压 RKE2 运行二进制包
        self._extract_rke2_binary()

    def _extract_rke2_binary(self):
        """从 bundle 中查找、校验并解压 RKE2 二进制包到 sysroot。"""
        src_binaries_dir = os.path.join(_BUNDLE_DIR, "binaries")
        rke2_tar = None
        if os.path.exists(src_binaries_dir):
            for f in os.listdir(src_binaries_dir):
                if f.startswith("rke2.linux-") and f.endswith(".tar.gz"):
                    rke2_tar = f
                    break

        if not rke2_tar:
            log.warning("[VDI] 未在离线 bundle 中找到 rke2.linux-*.tar.gz 二进制包")
            return

        tmp_tar_path = os.path.join(self._sysroot, "tmp", rke2_tar)
        shutil.copy(os.path.join(src_binaries_dir, rke2_tar), tmp_tar_path)

        try:
            if os.path.getsize(tmp_tar_path) == 0:
                log.error("[VDI] RKE2 二进制包 %s 为 0 字节，中止 RKE2 安装", rke2_tar)
                return

            verify = subprocess.run(
                ["tar", "tzf", tmp_tar_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            if verify.returncode != 0:
                log.error("[VDI] RKE2 二进制包 %s 校验失败（非合法 tar）: %s",
                          rke2_tar, verify.stderr.decode(errors="replace").strip())
                return

            usr_local = os.path.join(self._sysroot, "usr/local")
            self._ensure_dir(usr_local)
            subprocess.run(["tar", "xzf", tmp_tar_path, "-C", usr_local], check=True)
            log.info("[VDI] RKE2 运行二进制解压释放完成")
        except Exception as e:
            log.error("[VDI] 解压 RKE2 二进制包失败: %s", e)
        finally:
            if os.path.exists(tmp_tar_path):
                os.remove(tmp_tar_path)

    def _write_rke2_config(self):
        """动态配置并下发 RKE2 config.yaml，按角色分流。"""
        rke2_conf_dir = os.path.join(self._sysroot, "etc/rancher/rke2")
        self._ensure_dir(rke2_conf_dir)

        rke2_conf_path = os.path.join(rke2_conf_dir, "config.yaml")
        try:
            with open(rke2_conf_path, "w") as f:
                if self._role == "agent":
                    f.write(f"""server: {self._server_url}
token: "{self._token}"
kubelet-arg:
  - "max-pods=200"
""")
                else:
                    f.write("""write-kubeconfig-mode: "0600"
cni: none
disable:
  - rke2-ingress-nginx
kubelet-arg:
  - "max-pods=200"
""")
                    if self._ip or self._vip:
                        f.write("tls-san:\n")
                        if self._vip:
                            f.write(f"  - {self._vip}\n")
                        if self._ip:
                            f.write(f"  - {self._ip}\n")
            log.info("[VDI] RKE2 核心配置文件 config.yaml 写入完成")
        except Exception as e:
            log.error("[VDI] 写入 RKE2 config.yaml 失败: %s", e)

    def _write_kube_ovn_manifest(self):
        """动态生成 Kube-OVN HelmChart CRD manifest（含 bootstrap + chartContent 内嵌）。"""
        try:
            manifests_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/server/manifests")
            self._ensure_dir(manifests_dir)

            underlay_iface = "bond0" if self._mode == "bond" and self._interface2 else self._interface

            # 从 ISO bundle 读取 chart tgz 并 base64 编码内嵌到 chartContent
            chart_content = ""
            src_charts_dir = os.path.join(_BUNDLE_DIR, "charts")
            if os.path.exists(src_charts_dir):
                for f in os.listdir(src_charts_dir):
                    if f.startswith("kube-ovn") and f.endswith(".tgz"):
                        with open(os.path.join(src_charts_dir, f), "rb") as cf:
                            chart_content = base64.b64encode(cf.read()).decode("ascii")
                        log.info("[VDI] Kube-OVN chart tgz 已 base64 编码 (%d bytes)", len(chart_content))
                        break

            manifest_path = os.path.join(manifests_dir, "kube-ovn.yaml")
            with open(manifest_path, "w") as f:
                f.write(f"""apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: kube-ovn
  namespace: kube-system
spec:
  bootstrap: true
  chartContent: {chart_content}
  targetNamespace: kube-system
  valuesContent: |
    MASTER_NODES_LABEL: "node-role.kubernetes.io/master"
    ipv4:
      POD_CIDR: "{self._pod_cidr}"
      SVC_CIDR: "{self._service_cidr}"
      JOIN_CIDR: "{self._join_cidr}"
    networking:
      NETWORK_TYPE: "geneve"
      vlan:
        VLAN_INTERFACE_NAME: "{underlay_iface}"
        VLAN_ID: "0"
    func:
      ENABLE_LB: "true"
      ENABLE_NP: "true"
""")
            log.info("[VDI] Kube-OVN HelmChart CRD manifest 写入完成 (bootstrap=true, underlay=%s, POD=%s, SVC=%s)",
                     underlay_iface, self._pod_cidr, self._service_cidr)
        except Exception as e:
            log.error("[VDI] 写入 Kube-OVN manifest 失败: %s", e)

    def _copy_kubevirt_manifests(self):
        """KubeVirt operator 放 RKE2 manifests，CR 存 /etc/vdi/cr/ 延迟 apply。"""
        try:
            self._copy_operator_cr_manifests("kubevirt")
        except Exception as e:
            log.error("[VDI] 复制 KubeVirt manifest 失败: %s", e)

    def _copy_cdi_manifests(self):
        """CDI operator 放 RKE2 manifests，CR 存 /etc/vdi/cr/ 延迟 apply。"""
        try:
            self._copy_operator_cr_manifests("cdi")
        except Exception as e:
            log.error("[VDI] 复制 CDI manifest 失败: %s", e)

    def _create_kubeconfig_service(self):
        """创建 systemd oneshot 服务，RKE2 首启后等 rke2.yaml 生成再拷贝到 ~/.kube/config。"""
        try:
            script_path = os.path.join(self._sysroot, "usr/local/bin/vdi-kubeconfig.sh")
            with open(script_path, "w") as f:
                f.write("""#!/bin/bash
# 等待 RKE2 生成 rke2.yaml（最多 5 分钟）
SRC="/etc/rancher/rke2/rke2.yaml"
DST="/root/.kube/config"
TIMEOUT=300
ELAPSED=0

while [ ! -s "$SRC" ]; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        echo "VDI kubeconfig: 等待 $SRC 超时 (${TIMEOUT}s)" >&2
        exit 1
    fi
done

mkdir -p /root/.kube
cp "$SRC" "$DST"
chmod 600 "$DST"
echo "VDI kubeconfig: $SRC → $DST 拷贝完成"
""")
            os.chmod(script_path, 0o755)

            unit_path = os.path.join(self._sysroot, "etc/systemd/system/vdi-kubeconfig.service")
            with open(unit_path, "w") as f:
                f.write("""[Unit]
Description=Copy RKE2 kubeconfig to root home after first boot
After=rke2-server.service
Requires=rke2-server.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vdi-kubeconfig.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
""")
            log.info("[VDI] kubeconfig 延迟拷贝服务创建完成")
        except Exception as e:
            log.error("[VDI] 创建 kubeconfig 延迟拷贝服务失败: %s", e)

    def _create_cr_apply_service(self):
        """创建 systemd oneshot 服务，RKE2 启动后等 CRD 就绪再 apply KubeVirt/CDI CR。"""
        try:
            script_path = os.path.join(self._sysroot, "usr/local/bin/vdi-apply-cr.sh")
            with open(script_path, "w") as f:
                f.write("""#!/bin/bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export PATH="$PATH:/var/lib/rancher/rke2/bin"

# 等待 API server 就绪
until kubectl get nodes 2>/dev/null; do sleep 5; done

# 等待 KubeVirt CRD Established
kubectl wait --for=condition=Established crd/kubevirts.kubevirt.io --timeout=300s 2>/dev/null || true

# 等待 CDI CRD Established
kubectl wait --for=condition=Established crd/cdis.cdi.kubevirt.io --timeout=300s 2>/dev/null || true

# Apply CR
for f in /etc/vdi/cr/*.yaml; do
  [ -f "$f" ] || continue
  kubectl apply -f "$f" 2>/dev/null || true
done
""")
            os.chmod(script_path, 0o755)

            unit_path = os.path.join(self._sysroot, "etc/systemd/system/vdi-apply-cr.service")
            with open(unit_path, "w") as f:
                f.write("""[Unit]
Description=Apply KubeVirt/CDI CR after CRD ready
After=rke2-server.service
Requires=rke2-server.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vdi-apply-cr.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
""")
            log.info("[VDI] CR 延迟应用服务创建完成")
        except Exception as e:
            log.error("[VDI] 创建 CR 延迟应用服务失败: %s", e)

    def _setup_kubectl_convenience(self):
        """配置 kubectl 便捷访问：PATH 软链、KUBECONFIG。"""
        try:
            # kubectl 软链到 /usr/local/bin/
            kubectl_src = "/var/lib/rancher/rke2/bin/kubectl"
            kubectl_link = os.path.join(self._sysroot, "usr/local/bin/kubectl")
            if not os.path.exists(kubectl_link):
                os.symlink(kubectl_src, kubectl_link)

            # /etc/profile.d/rke2.sh — 登录时自动设置 PATH 和 KUBECONFIG
            profile_d_dir = os.path.join(self._sysroot, "etc/profile.d")
            self._ensure_dir(profile_d_dir)
            with open(os.path.join(profile_d_dir, "rke2.sh"), "w") as f:
                f.write('export PATH="$PATH:/var/lib/rancher/rke2/bin"\n')
                f.write('export KUBECONFIG="/etc/rancher/rke2/rke2.yaml"\n')

            # 注: ~/.kube/config 由 vdi-kubeconfig.service 在 RKE2 首启后延迟拷贝，
            # 安装阶段 rke2.yaml 尚未生成，此处无法拷贝。

            log.info("[VDI] kubectl 便捷配置完成（PATH 软链 + profile.d，kubeconfig 延迟拷贝）")
        except Exception as e:
            log.error("[VDI] kubectl 便捷配置失败: %s", e)

    def _enable_systemd_services(self):
        """创建 systemd wants 链接，激活服务。"""
        try:
            wants_dir = os.path.join(self._sysroot, "etc/systemd/system/multi-user.target.wants")
            self._ensure_dir(wants_dir)

            # 激活 sshd.service
            sshd_link = os.path.join(wants_dir, "sshd.service")
            if not os.path.exists(sshd_link):
                os.symlink("/usr/lib/systemd/system/sshd.service", sshd_link)

            # 激活 open-iscsid.service (Longhorn 依赖)
            iscsid_link = os.path.join(wants_dir, "iscsid.service")
            if not os.path.exists(iscsid_link):
                try:
                    os.symlink("/usr/lib/systemd/system/iscsid.service", iscsid_link)
                except Exception as e:
                    log.warning("[VDI] 激活 iscsid.service 失败: %s", e)

            # 激活 RKE2 服务
            service_name = "rke2-server"
            rke2_link = os.path.join(wants_dir, f"{service_name}.service")
            if not os.path.exists(rke2_link):
                os.symlink(f"/usr/local/lib/systemd/system/{service_name}.service", rke2_link)

            # 激活 kubeconfig 延迟拷贝服务
            kc_link = os.path.join(wants_dir, "vdi-kubeconfig.service")
            if not os.path.exists(kc_link):
                os.symlink("/etc/systemd/system/vdi-kubeconfig.service", kc_link)

            # 激活 CR 延迟应用服务
            cr_link = os.path.join(wants_dir, "vdi-apply-cr.service")
            if not os.path.exists(cr_link):
                os.symlink("/etc/systemd/system/vdi-apply-cr.service", cr_link)

            log.info("[VDI] 成功激活 sshd, iscsid, vdi-kubeconfig, vdi-apply-cr 及 %s 服务开机自启", service_name)
        except Exception as e:
            log.error("[VDI] 激活 systemd 服务发生错误: %s", e)
