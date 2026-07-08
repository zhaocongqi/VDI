"""VDI Addon 安装任务实现（参考 com_redhat_kdump/service/installation.py）"""
import os
import uuid
import logging
import subprocess
import shutil

from pyanaconda.modules.common.task import Task

log = logging.getLogger(__name__)

__all__ = ["VdiInstallationTask"]


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

    def __init__(self, sysroot, mode, interface, interface2, bond_mode, ip, netmask, gateway, dns, vip, network_mode):
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
        :param vip: 集群虚拟 IP（静态模式）
        :param network_mode: 网络模式 (dhcp/static)
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
        self._vip = vip or ""
        self._network_mode = network_mode or "dhcp"

    @property
    def name(self):
        return "Deploy VDI platform resources and configuration"

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

        # 6. kubectl 便捷配置（PATH、KUBECONFIG、~/.kube/config）
        self._setup_kubectl_convenience()

        # 7. 创建 systemd wants 链接，激活服务
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
        if not os.path.exists(conn_dir):
            try:
                os.makedirs(conn_dir, mode=0o755)
            except Exception as e:
                log.error("[VDI] 创建目标网卡配置目录失败: %s", e)
                return

        # 清理原有网卡配置，防止冲突
        for f in os.listdir(conn_dir):
            if f.endswith(".nmconnection"):
                try:
                    os.remove(os.path.join(conn_dir, f))
                except Exception:
                    pass

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
options=mode={self._bond_mode},miimon=100

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
        if not os.path.exists(vdi_conf_dir):
            os.makedirs(vdi_conf_dir, mode=0o755)
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
            if not os.path.exists(sshd_conf_dir):
                os.makedirs(sshd_conf_dir, mode=0o755)
            with open(os.path.join(sshd_conf_dir, "00-vdi-root-login.conf"), "w") as f:
                f.write("PermitRootLogin yes\nPasswordAuthentication yes\nUseDNS no\nGSSAPIAuthentication no\n")
            log.info("[VDI] 成功写入 00-vdi-root-login.conf SSH 配置文件")
        except Exception as e:
            log.error("[VDI] 写入 SSH 配置文件发生错误: %s", e)

    def _setup_data_disk(self):
        """数据盘自动探测、格式化与 fstab 挂载。"""
        try:
            # 通过 /sys/block 枚举块设备，跳过系统盘（含根分区/LVM 的盘）
            import glob
            all_block_devs = sorted(glob.glob("/sys/block/vd*")) + sorted(glob.glob("/sys/block/sd*"))

            # 系统盘判定：包含 LVM PV 或根分区的盘
            boot_disk_name = ""
            for dev_path in all_block_devs:
                dev_name = os.path.basename(dev_path)
                # 检查该盘的分区是否包含 LVM 或根文件系统
                partitions = glob.glob(f"/sys/block/{dev_name}/{dev_name}*")
                for part in partitions:
                    part_name = os.path.basename(part)
                    part_dev = f"/dev/{part_name}"
                    try:
                        fstype = subprocess.check_output(
                            ["blkid", "-s", "TYPE", "-o", "value", part_dev],
                            stderr=subprocess.DEVNULL
                        ).decode().strip()
                        if fstype in ("LVM2_member", "ext4", "xfs"):
                            # 可能是系统盘
                            mount_info = subprocess.check_output(
                                ["lsblk", "-no", "MOUNTPOINT", part_dev],
                                stderr=subprocess.DEVNULL
                            ).decode().strip()
                            if mount_info or fstype == "LVM2_member":
                                boot_disk_name = dev_name
                                break
                    except Exception:
                        pass
                if boot_disk_name:
                    break

            # 查找非系统盘作为数据盘
            data_disk_name = None
            for dev_path in all_block_devs:
                dev_name = os.path.basename(dev_path)
                if dev_name != boot_disk_name:
                    data_disk_name = dev_name
                    break

            if not data_disk_name:
                log.warning("[VDI] 未探测到其它物理数据盘，跳过数据盘处理")
                return

            data_dev_path = f"/dev/{data_disk_name}"
            log.info("[VDI] 探测到物理数据盘: %s, 开始格式化...", data_dev_path)
            subprocess.run(["mkfs.ext4", "-F", "-L", "VDI_LH_DEFAULT", data_dev_path], check=True)

            longhorn_dir = os.path.join(self._sysroot, "var/lib/longhorn")
            if not os.path.exists(longhorn_dir):
                os.makedirs(longhorn_dir, mode=0o755)

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
        repo_dir = "/run/install/repo"
        bundle_dir = os.path.join(repo_dir, "bundle/vdi")

        if not os.path.exists(bundle_dir):
            log.warning("[VDI] 未在光盘安装源中找到离线资源 bundle/vdi，跳过离线资源释放")
            return

        log.info("[VDI] 发现离线资源 bundle，开始释放...")

        # 5.1 拷贝 RKE2 离线镜像 (images)
        target_images_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/agent/images")
        if not os.path.exists(target_images_dir):
            os.makedirs(target_images_dir, mode=0o755)
        src_images_dir = os.path.join(bundle_dir, "images")
        if os.path.exists(src_images_dir):
            for f in os.listdir(src_images_dir):
                if f.endswith(".tar.zst"):
                    src_img = os.path.join(src_images_dir, f)
                    if not os.path.exists(src_img) or os.path.getsize(src_img) == 0:
                        log.warning("[VDI] 跳过空镜像文件: %s", f)
                        continue
                    shutil.copy(src_img, target_images_dir)
        log.info("[VDI] 离线 RKE2 镜像拷贝完成")

        # 5.2 拷贝 Helm Charts 和 Manifests
        target_charts_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/server/charts")
        if not os.path.exists(target_charts_dir):
            os.makedirs(target_charts_dir, mode=0o755)
        src_charts_dir = os.path.join(bundle_dir, "charts")
        if os.path.exists(src_charts_dir):
            for f in os.listdir(src_charts_dir):
                if f.endswith(".tgz"):
                    shutil.copy(os.path.join(src_charts_dir, f), target_charts_dir)

        target_manifests_dir = os.path.join(self._sysroot, "var/lib/rancher/rke2/server/manifests")
        if not os.path.exists(target_manifests_dir):
            os.makedirs(target_manifests_dir, mode=0o755)
        src_manifests_dir = os.path.join(bundle_dir, "manifests")
        if os.path.exists(src_manifests_dir):
            for f in os.listdir(src_manifests_dir):
                if f.endswith(".yaml"):
                    shutil.copy(os.path.join(src_manifests_dir, f), target_manifests_dir)
        log.info("[VDI] 离线 Helm Charts & Manifests 拷贝完成")

        # 5.3 复制并解压 RKE2 运行二进制包
        src_binaries_dir = os.path.join(bundle_dir, "binaries")
        rke2_tar = None
        if os.path.exists(src_binaries_dir):
            for f in os.listdir(src_binaries_dir):
                if f.startswith("rke2.linux-") and f.endswith(".tar.gz"):
                    rke2_tar = f
                    break

        if rke2_tar:
            tmp_tar_path = os.path.join(self._sysroot, "tmp", rke2_tar)
            shutil.copy(os.path.join(src_binaries_dir, rke2_tar), tmp_tar_path)

            # 完整性校验
            if os.path.getsize(tmp_tar_path) == 0:
                log.error("[VDI] RKE2 二进制包 %s 为 0 字节，中止 RKE2 安装", rke2_tar)
                os.remove(tmp_tar_path)
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
                os.remove(tmp_tar_path)
                return

            # 解压
            usr_local = os.path.join(self._sysroot, "usr/local")
            if not os.path.exists(usr_local):
                os.makedirs(usr_local, mode=0o755)

            try:
                subprocess.run(["tar", "xzf", tmp_tar_path, "-C", usr_local], check=True)
                log.info("[VDI] RKE2 运行二进制解压释放完成")
            except Exception as e:
                log.error("[VDI] 解压 RKE2 二进制包失败: %s", e)
            finally:
                if os.path.exists(tmp_tar_path):
                    os.remove(tmp_tar_path)
        else:
            log.warning("[VDI] 未在离线 bundle 中找到 rke2.linux-*.tar.gz 二进制包")

    def _write_rke2_config(self):
        """动态配置并下发 RKE2 config.yaml。"""
        is_agent = False
        server_url = ""
        token = "vdi-cluster-token"

        rke2_conf_dir = os.path.join(self._sysroot, "etc/rancher/rke2")
        if not os.path.exists(rke2_conf_dir):
            os.makedirs(rke2_conf_dir, mode=0o755)

        rke2_conf_path = os.path.join(rke2_conf_dir, "config.yaml")
        try:
            with open(rke2_conf_path, "w") as f:
                if not is_agent:
                    f.write(f"""write-kubeconfig-mode: "0600"
cni: none
disable:
  - rke2-ingress-nginx
kubelet-arg:
  - "max-pods=200"
""")
                    # 如果配置了 IP/VIP，将其注入为 SAN
                    if self._ip or self._vip:
                        f.write("tls-san:\n")
                        if self._vip:
                            f.write(f"  - {self._vip}\n")
                        if self._ip:
                            f.write(f"  - {self._ip}\n")
                else:
                    f.write(f"""server: {server_url}
token: "{token}"
kubelet-arg:
  - "max-pods=200"
""")
            log.info("[VDI] RKE2 核心配置文件 config.yaml 写入完成")
        except Exception as e:
            log.error("[VDI] 写入 RKE2 config.yaml 失败: %s", e)

    def _setup_kubectl_convenience(self):
        """配置 kubectl 便捷访问：PATH 软链、KUBECONFIG、~/.kube/config。"""
        try:
            # 1. kubectl 软链到 /usr/local/bin/
            kubectl_src = "/var/lib/rancher/rke2/bin/kubectl"
            kubectl_link = os.path.join(self._sysroot, "usr/local/bin/kubectl")
            if not os.path.exists(kubectl_link):
                os.symlink(kubectl_src, kubectl_link)

            # 2. /etc/profile.d/rke2.sh — 登录时自动设置 PATH 和 KUBECONFIG
            profile_d_dir = os.path.join(self._sysroot, "etc/profile.d")
            if not os.path.exists(profile_d_dir):
                os.makedirs(profile_d_dir, mode=0o755)
            with open(os.path.join(profile_d_dir, "rke2.sh"), "w") as f:
                f.write('export PATH="$PATH:/var/lib/rancher/rke2/bin"\n')
                f.write('export KUBECONFIG="/etc/rancher/rke2/rke2.yaml"\n')

            # 3. root 用户 ~/.kube/config（拷贝 kubeconfig）
            kube_dir = os.path.join(self._sysroot, "root/.kube")
            if not os.path.exists(kube_dir):
                os.makedirs(kube_dir, mode=0o700)
            kubeconfig_src = os.path.join(self._sysroot, "etc/rancher/rke2/rke2.yaml")
            kubeconfig_dst = os.path.join(kube_dir, "config")
            if os.path.exists(kubeconfig_src):
                shutil.copy(kubeconfig_src, kubeconfig_dst)
                os.chmod(kubeconfig_dst, 0o600)

            log.info("[VDI] kubectl 便捷配置完成（PATH 软链 + profile.d + ~/.kube/config）")
        except Exception as e:
            log.error("[VDI] kubectl 便捷配置失败: %s", e)

    def _enable_systemd_services(self):
        """创建 systemd wants 链接，激活服务。"""
        try:
            wants_dir = os.path.join(self._sysroot, "etc/systemd/system/multi-user.target.wants")
            if not os.path.exists(wants_dir):
                os.makedirs(wants_dir, mode=0o755)

            # 激活 sshd.service
            sshd_link = os.path.join(wants_dir, "sshd.service")
            if not os.path.exists(sshd_link):
                os.symlink("/usr/lib/systemd/system/sshd.service", sshd_link)

            # 激活 open-iscsid.service (Longhorn 依赖)
            iscsid_link = os.path.join(wants_dir, "iscsid.service")
            if not os.path.exists(iscsid_link):
                try:
                    os.symlink("/usr/lib/systemd/system/iscsid.service", iscsid_link)
                except Exception:
                    pass

            # 激活 RKE2 服务
            service_name = "rke2-server"
            rke2_link = os.path.join(wants_dir, f"{service_name}.service")
            if not os.path.exists(rke2_link):
                os.symlink(f"/usr/local/lib/systemd/system/{service_name}.service", rke2_link)

            log.info("[VDI] 成功激活 sshd, iscsid 及 %s 服务开机自启", service_name)
        except Exception as e:
            log.error("[VDI] 激活 systemd 服务发生错误: %s", e)
