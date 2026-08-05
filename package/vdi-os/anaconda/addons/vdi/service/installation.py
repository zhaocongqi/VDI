"""VDI Addon 安装任务实现（参考 com_redhat_kdump/service/installation.py）"""
import glob
import os
import uuid
import logging
import subprocess
import shutil

from pyanaconda.modules.common.task import Task

log = logging.getLogger(__name__)

__all__ = ["VdiInstallationTask"]

_BUNDLE_DIR = "/run/install/repo/bundle/vdi"


class VdiInstallationTask(Task):
    """VDI 平台系统配置与资源部署安装任务。

    在 Anaconda 安装阶段执行，负责：
    - 写入 NetworkManager 网卡配置
    - 配置 SSH root 登录
    - 双数据盘格式化与挂载（/apps + /var/lib/longhorn）
    - 释放 sealer 集群镜像与二进制
    - 生成 vdi-clusterd / vdi-join-agent systemd 单元
    - 激活 systemd 服务
    """

    def __init__(self, sysroot, mode, interface, interface2, bond_mode, ip, netmask, gateway, dns, pod_cidr, service_cidr, vip, network_mode, role="first-master", server_url="", token="", apps_disk="auto", longhorn_disk="auto", bond1_enabled=False, bond1_interface="", bond1_interface2="", bond1_bond_mode="active-backup", bond1_network_mode="static", bond1_ip="", bond1_netmask="255.255.255.0", bond1_gateway="", bond2_enabled=False, bond2_interface="", bond2_interface2="", bond2_bond_mode="active-backup", bond2_network_mode="static", bond2_ip="", bond2_netmask="255.255.255.0", bond2_gateway="", default_route_iface=""):
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
        :param vip: 集群虚拟 IP（静态模式）
        :param network_mode: 网络模式 (dhcp/static)
        :param role: 集群角色 (first-master/node)
        :param server_url: node 角色下 master vdi-clusterd 地址 (http://<ip>:9345)
        :param token: 集群预共享密钥
        :param apps_disk: /apps 数据盘 (auto 或设备名)
        :param longhorn_disk: Longhorn 数据盘 (auto 或设备名)
        :param bond1_enabled: 是否启用 bond1 业务网络
        :param bond1_interface: bond1 主网卡
        :param bond1_interface2: bond1 备网卡
        :param bond1_bond_mode: bond1 绑定模式
        :param bond1_network_mode: bond1 网络模式 (dhcp/static)
        :param bond1_ip: bond1 IP
        :param bond1_netmask: bond1 掩码
        :param bond1_gateway: bond1 网关
        :param bond2_enabled: 是否启用 bond2 业务网络
        :param bond2_interface: bond2 主网卡
        :param bond2_interface2: bond2 备网卡
        :param bond2_bond_mode: bond2 绑定模式
        :param bond2_network_mode: bond2 网络模式 (dhcp/static)
        :param bond2_ip: bond2 IP
        :param bond2_netmask: bond2 掩码
        :param bond2_gateway: bond2 网关
        :param default_route_iface: 默认路由网卡 (bond0/bond1/bond2，空=管理网络)
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
        self._vip = vip or ""
        self._network_mode = network_mode or "dhcp"
        self._role = role or "first-master"
        self._server_url = server_url or ""
        self._token = token or ""
        self._apps_disk = apps_disk or "auto"
        self._longhorn_disk = longhorn_disk or "auto"
        self._bond1_enabled = bond1_enabled if isinstance(bond1_enabled, bool) else str(bond1_enabled).lower() in ("true", "1", "yes")
        self._bond1_interface = bond1_interface or ""
        self._bond1_interface2 = bond1_interface2 or ""
        self._bond1_bond_mode = bond1_bond_mode or "active-backup"
        self._bond1_network_mode = bond1_network_mode or "static"
        self._bond1_ip = bond1_ip or ""
        self._bond1_netmask = bond1_netmask or "255.255.255.0"
        self._bond1_gateway = bond1_gateway or ""
        self._bond2_enabled = bond2_enabled if isinstance(bond2_enabled, bool) else str(bond2_enabled).lower() in ("true", "1", "yes")
        self._bond2_interface = bond2_interface or ""
        self._bond2_interface2 = bond2_interface2 or ""
        self._bond2_bond_mode = bond2_bond_mode or "active-backup"
        self._bond2_network_mode = bond2_network_mode or "static"
        self._bond2_ip = bond2_ip or ""
        self._bond2_netmask = bond2_netmask or "255.255.255.0"
        self._bond2_gateway = bond2_gateway or ""
        self._default_route_iface = default_route_iface or ""

    @property
    def name(self):
        return "Deploy VDI platform resources and configuration"

    @staticmethod
    def _ensure_dir(path, mode=0o755):
        os.makedirs(path, mode=mode, exist_ok=True)

    def run(self):
        """执行安装任务。"""
        log.info(">>> [VDI] 开始执行 VdiInstallationTask 全量系统配置写入 (role=%s)", self._role)

        # 1. 网卡与 Bond 持久化写入
        self._write_network_config()

        # 2. SSH Root 登录配置
        self._configure_ssh()

        # 3. 双数据盘探测、格式化与 fstab 挂载（/apps + /var/lib/longhorn）
        self._setup_data_disk()

        # 4. 释放 sealer 集群镜像、sealer 二进制与组件资产
        self._extract_sealer_resources()

        # 5. 写集群身份文件（master: cluster-token；worker: join.conf）
        self._write_cluster_identity()

        if self._role == "first-master":
            # 6. master: 渲染 Clusterfile（含 License 关闭 + PostGuest 组件 Plugin）
            self._render_clusterfile()

            # 7. master: 预置组件栈安装脚本与资产到 /opt/vdi/
            self._stage_components()

            # 8. master: 生成 vdi-clusterd 守护进程与 systemd 单元
            self._create_clusterd_service()

            # 9. master: kubeconfig 延迟拷贝服务（admin.conf → ~/.kube/config）
            self._create_kubeconfig_service()

            # 10. master: kubectl/helm 便捷配置
            self._setup_kubectl_convenience()
        else:
            # 6'. worker: 生成 vdi-join-agent oneshot 单元
            self._create_join_agent_service()

        # 11. 创建 systemd wants 链接，激活服务
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

    def _build_ipv4_section(self, is_dhcp, ip="", netmask="255.255.255.0", gateway="", dns="", never_default=False):
        """构建 [ipv4] 配置段。

        :param is_dhcp: 是否 DHCP
        :param ip: 静态 IP
        :param netmask: 子网掩码
        :param gateway: 网关（never_default=True 时忽略）
        :param dns: DNS 服务器
        :param never_default: True 时不生成默认路由（never-default=true）
        """
        if is_dhcp:
            lines = "[ipv4]\nmethod=auto"
            if never_default:
                lines += "\nnever-default=true"
            return lines
        cidr = self._netmask_to_cidr(netmask)
        if never_default:
            lines = f"[ipv4]\nmethod=manual\naddresses={ip}/{cidr}"
        else:
            lines = f"[ipv4]\nmethod=manual\naddresses={ip}/{cidr},{gateway}"
        if dns:
            lines += f"\ndns={dns};"
        if never_default:
            lines += "\nnever-default=true"
        return lines

    def _write_one_bond(self, conn_dir, bond_name, iface1, iface2, bond_mode,
                        ipv4_section, ipv6_section, priority=90):
        """写入一个 bond 的 nmconnection 文件（bond + 两个从网卡）。

        :param conn_dir: NetworkManager system-connections 目录
        :param bond_name: bond 接口名 (bond1/bond2)
        :param iface1: 主从网卡
        :param iface2: 备从网卡
        :param bond_mode: 绑定模式 (active-backup/802.3ad)
        :param ipv4_section: [ipv4] 配置段字符串
        :param ipv6_section: [ipv6] 配置段字符串
        :param priority: autoconnect-priority（bond0=100, bond1=90, bond2=80）
        """
        bond_uuid = str(uuid.uuid4())
        port1_uuid = str(uuid.uuid4())
        port2_uuid = str(uuid.uuid4())

        bond_path = os.path.join(conn_dir, f"{bond_name}.nmconnection")
        with open(bond_path, "w") as f:
            f.write(f"""[connection]
id={bond_name}
uuid={bond_uuid}
type=bond
interface-name={bond_name}
autoconnect=true
autoconnect-priority={priority}

[bond]
mode={bond_mode}
miimon=100

{ipv4_section}

{ipv6_section}
""")
        os.chmod(bond_path, 0o600)

        for iface, port_uuid in [(iface1, port1_uuid), (iface2, port2_uuid)]:
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
autoconnect-priority={priority}

[ethernet]

{ipv6_section}
""")
            os.chmod(port_path, 0o600)

        log.info("[VDI] 成功写入 %s 网卡绑定配置 (%s + %s)", bond_name, iface1, iface2)

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
        # 主网卡承载默认路由的条件：default_route_iface 为空（默认主网卡）
        # 或等于主网卡标识（single 模式=物理网卡名，bond 模式=bond0）。
        # 此前硬编码 "bond0"，single 模式选 enp0s2 时误判为非默认路由网卡，
        # 给 DHCP 主网卡加 never-default=true，导致系统零默认路由。
        primary_iface = "bond0" if (self._mode == "bond" and self._interface2) else self._interface
        bond0_never_default = bool(self._default_route_iface) and self._default_route_iface != primary_iface
        ipv4_section = self._build_ipv4_section(
            is_dhcp, self._ip, self._netmask, self._gateway, self._dns,
            never_default=bond0_never_default)
        ipv6_section = "[ipv6]\nmethod=disabled"

        if self._mode == "bond" and self._interface2:
            # ----------------- bond0 绑定模式 -----------------
            self._write_one_bond(conn_dir, "bond0", self._interface, self._interface2,
                                 self._bond_mode, ipv4_section, ipv6_section, priority=100)
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

        # ----------------- bond1/bond2 业务网络绑定（可选） -----------------
        for idx, (enabled, iface, iface2, bond_mode, net_mode, ip, netmask, gateway) in enumerate([
            (self._bond1_enabled, self._bond1_interface, self._bond1_interface2,
             self._bond1_bond_mode, self._bond1_network_mode, self._bond1_ip,
             self._bond1_netmask, self._bond1_gateway),
            (self._bond2_enabled, self._bond2_interface, self._bond2_interface2,
             self._bond2_bond_mode, self._bond2_network_mode, self._bond2_ip,
             self._bond2_netmask, self._bond2_gateway),
        ], start=1):
            if not enabled or not iface or not iface2:
                continue
            bond_name = f"bond{idx}"
            b_is_dhcp = (net_mode == "dhcp")
            b_never_default = (self._default_route_iface != bond_name)
            b_ipv4 = self._build_ipv4_section(
                b_is_dhcp, ip, netmask, gateway, "",
                never_default=b_never_default)
            self._write_one_bond(conn_dir, bond_name, iface, iface2,
                                 bond_mode, b_ipv4, ipv6_section, priority=100 - idx * 10)

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
DEFAULT_ROUTE_IFACE={self._default_route_iface}
# Bond1 Business Network
BOND1_ENABLED={self._bond1_enabled}
BOND1_INTERFACE={self._bond1_interface}
BOND1_INTERFACE2={self._bond1_interface2}
BOND1_BOND_MODE={self._bond1_bond_mode}
BOND1_NETWORK_MODE={self._bond1_network_mode}
BOND1_IP={self._bond1_ip}
BOND1_NETMASK={self._bond1_netmask}
BOND1_GATEWAY={self._bond1_gateway}
# Bond2 Business Network
BOND2_ENABLED={self._bond2_enabled}
BOND2_INTERFACE={self._bond2_interface}
BOND2_INTERFACE2={self._bond2_interface2}
BOND2_BOND_MODE={self._bond2_bond_mode}
BOND2_NETWORK_MODE={self._bond2_network_mode}
BOND2_IP={self._bond2_ip}
BOND2_NETMASK={self._bond2_netmask}
BOND2_GATEWAY={self._bond2_gateway}
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
        """判断块设备是否为系统盘。

        以"该盘分区是否为根(/)或 /boot 的底层设备"为准，而非笼统的 LVM 签名检测——
        anaconda clearpart 会给数据盘写入 LVM 签名但不实际使用，旧逻辑据此误判。

        anaconda 安装环境中目标系统挂在 /mnt/sysroot 下，findmnt 需以 sysroot 为根；
        已安装系统（二次进入）则直接用 /。
        """
        try:
            # 目标根：anaconda 环境为 /mnt/sysroot，装机后环境为 /
            target_root = self._sysroot if os.path.ismount(self._sysroot) or \
                os.path.isdir(os.path.join(self._sysroot, "boot")) else "/"
            holders = set()
            for mp in ("/", "/boot", "/boot/efi"):
                full_mp = os.path.join(target_root, mp.lstrip("/")) if target_root != "/" else mp
                try:
                    src = subprocess.check_output(
                        ["findmnt", "-no", "SOURCE", full_mp],
                        stderr=subprocess.DEVNULL
                    ).decode().strip()
                    if src:
                        holders.add(src)
                except subprocess.CalledProcessError:
                    # /boot/efi 在某些布局下非独立挂载，跳过
                    continue
            # 解析这些源设备的底层磁盘（lsblk PKNAME 追踪到物理盘）
            sys_disks = set()
            for src in holders:
                pk = subprocess.check_output(
                    ["lsblk", "-no", "PKNAME", src],
                    stderr=subprocess.DEVNULL
                ).decode().split()
                sys_disks.update(pk)
            if sys_disks:
                return dev_name in sys_disks
            raise RuntimeError("未解析到任何系统盘底层设备")
        except Exception as e:
            log.warning("[VDI] findmnt/lsblk 系统盘判定失败，回退保守策略: %s", e)
            # 回退：只信任"在 sysroot 内有挂载点"的分区，不再把 LVM 签名当系统盘
            partitions = glob.glob(f"/sys/block/{dev_name}/{dev_name}*")
            for part in partitions:
                part_dev = f"/dev/{os.path.basename(part)}"
                try:
                    mount_info = subprocess.check_output(
                        ["findmnt", "-no", "TARGET", "-S", part_dev],
                        stderr=subprocess.DEVNULL
                    ).decode().strip()
                    # 挂载点落在 sysroot 内（或装机后的 /）才算系统占用
                    if mount_info and (mount_info.startswith(self._sysroot) or mount_info.startswith("/boot") or mount_info == "/"):
                        return True
                except Exception:
                    pass
        return False

    def _pick_data_disks(self):
        """探测/指定双数据盘，返回 (apps_dev, longhorn_dev) 设备名元组。

        GUI 指定优先；auto 时按设备名字典序分配第一块为 /apps、第二块为 Longhorn。
        两块指定为同一设备时视为配置错误。
        """
        specified = []
        for raw in (self._apps_disk, self._longhorn_disk):
            if raw and raw != "auto":
                name = os.path.basename(raw)
                if os.path.exists(f"/dev/{name}"):
                    specified.append(name)
                else:
                    log.warning("[VDI] 指定数据盘 %s 不存在，回退自动探测", raw)
                    specified.append(None)
            else:
                specified.append(None)

        if specified[0] and specified[1] and specified[0] == specified[1]:
            log.error("[VDI] /apps 盘与 Longhorn 盘指定为同一设备 %s，配置错误", specified[0])
            return None, None

        auto_candidates = []
        all_block_devs = sorted(glob.glob("/sys/block/vd*")) + sorted(glob.glob("/sys/block/sd*"))
        for dev_path in all_block_devs:
            dev_name = os.path.basename(dev_path)
            if dev_name in specified:
                continue
            if not self._is_system_disk(dev_name):
                auto_candidates.append(dev_name)

        apps_dev = specified[0] or (auto_candidates[0] if len(auto_candidates) > 0 else None)
        longhorn_dev = specified[1] or (auto_candidates[1] if len(auto_candidates) > 1 else None)
        return apps_dev, longhorn_dev

    def _format_and_mount(self, dev_name, label, mount_point):
        """格式化单块数据盘并写入 fstab。"""
        dev_path = f"/dev/{dev_name}"
        log.info("[VDI] 格式化数据盘 %s (label=%s) 挂载至 %s", dev_path, label, mount_point)
        subprocess.run(["mkfs.ext4", "-F", "-L", label, dev_path], check=True)

        self._ensure_dir(os.path.join(self._sysroot, mount_point.lstrip("/")))

        fstab_path = os.path.join(self._sysroot, "etc/fstab")
        entry = f"LABEL={label} {mount_point} ext4 defaults,noatime,nofail 0 2"
        already = False
        if os.path.exists(fstab_path):
            with open(fstab_path, "r") as f:
                already = label in f.read()
        if not already:
            with open(fstab_path, "a") as f:
                f.write("\n" + entry + "\n")

    def _setup_data_disk(self):
        """双数据盘探测、格式化与 fstab 挂载（/apps + /var/lib/longhorn）。"""
        try:
            apps_dev, longhorn_dev = self._pick_data_disks()

            if not apps_dev:
                log.error("[VDI] 未探测到 /apps 数据盘（EKI 要求 /apps 独立挂载），跳数据盘处理")
                return
            self._format_and_mount(apps_dev, "VDI_APPS", "/apps")

            if not longhorn_dev:
                log.error("[VDI] 未探测到第二块数据盘（Longhorn），仅 /apps 已挂载，"
                          "Longhorn 需事后手工补盘")
                return
            self._format_and_mount(longhorn_dev, "VDI_LH_DEFAULT", "/var/lib/longhorn")
            log.info("[VDI] 双数据盘挂载完成: /apps=%s, /var/lib/longhorn=%s",
                     apps_dev, longhorn_dev)
        except Exception as e:
            log.error("[VDI] 数据盘处理发生错误: %s", e)

    def _extract_sealer_resources(self):
        """释放 sealer 集群镜像、sealer 二进制与组件资产到目标磁盘。"""
        if not os.path.exists(_BUNDLE_DIR):
            log.warning("[VDI] 未在光盘安装源中找到离线资源 bundle/vdi，跳过离线资源释放")
            return

        log.info("[VDI] 发现离线资源 bundle，开始释放 (role=%s)...", self._role)

        src_binaries_dir = os.path.join(_BUNDLE_DIR, "binaries")

        # ---- 所有节点：sealer 二进制 + black_white sudoers ----
        bin_out = os.path.join(self._sysroot, "usr/local/bin")
        self._ensure_dir(bin_out)
        for fname in os.listdir(src_binaries_dir) if os.path.isdir(src_binaries_dir) else []:
            src = os.path.join(src_binaries_dir, fname)
            if fname.startswith("sealer"):
                shutil.copy(src, os.path.join(bin_out, "sealer"))
                os.chmod(os.path.join(bin_out, "sealer"), 0o755)
                log.info("[VDI] sealer 二进制释放至 /usr/local/bin/sealer")
            elif fname == "black_white":
                sudoers_d = os.path.join(self._sysroot, "etc/sudoers.d")
                self._ensure_dir(sudoers_d)
                shutil.copy(src, os.path.join(sudoers_d, "black_white"))
                os.chmod(os.path.join(sudoers_d, "black_white"), 0o440)
                log.info("[VDI] black_white 释放至 /etc/sudoers.d/")
            elif fname.startswith("helm-") and fname.endswith(".tar.gz"):
                self._extract_helm(src)

        # ---- 仅 master：集群镜像 tar + 组件资产 ----
        if self._role != "first-master":
            log.info("[VDI] worker 节点，跳过集群镜像与组件资产释放")
            return

        opt_vdi = os.path.join(self._sysroot, "opt/vdi")
        images_out = os.path.join(opt_vdi, "images")
        self._ensure_dir(images_out)

        cluster_tar = None
        if os.path.isdir(src_binaries_dir):
            for fname in os.listdir(src_binaries_dir):
                if fname.startswith("kubernetes_") and fname.endswith(".tar"):
                    cluster_tar = fname
                    break
        if cluster_tar:
            shutil.copy(os.path.join(src_binaries_dir, cluster_tar),
                        os.path.join(images_out, cluster_tar))
            log.info("[VDI] 集群镜像 %s 释放至 /opt/vdi/images/", cluster_tar)
        else:
            log.error("[VDI] 未在 bundle 中找到 kubernetes_*.tar 集群镜像")

        # 组件镜像（.tar / .tar.zst / .tar.gz）→ /opt/vdi/images/components/
        comp_out = os.path.join(images_out, "components")
        self._ensure_dir(comp_out)
        src_images_dir = os.path.join(_BUNDLE_DIR, "images")
        if os.path.isdir(src_images_dir):
            for fname in os.listdir(src_images_dir):
                if fname.endswith((".tar", ".tar.zst", ".tar.gz")):
                    src_img = os.path.join(src_images_dir, fname)
                    if os.path.getsize(src_img) == 0:
                        log.warning("[VDI] 跳过空镜像文件: %s", fname)
                        continue
                    shutil.copy(src_img, comp_out)
            log.info("[VDI] 组件镜像释放至 /opt/vdi/images/components/")

        # charts / manifests → /opt/vdi/
        for sub in ("charts", "manifests"):
            src_dir = os.path.join(_BUNDLE_DIR, sub)
            dst_dir = os.path.join(opt_vdi, sub)
            self._ensure_dir(dst_dir)
            if os.path.isdir(src_dir):
                for fname in os.listdir(src_dir):
                    if fname.endswith((".tgz", ".yaml")):
                        shutil.copy(os.path.join(src_dir, fname), dst_dir)
        log.info("[VDI] charts/manifests 释放至 /opt/vdi/")

    def _extract_helm(self, helm_tar_path):
        """解压 helm 二进制到 /usr/local/bin/helm。"""
        try:
            tmp_dir = os.path.join(self._sysroot, "tmp/helm-extract")
            self._ensure_dir(tmp_dir)
            subprocess.run(["tar", "xzf", helm_tar_path, "-C", tmp_dir], check=True)
            for root, _dirs, files in os.walk(tmp_dir):
                if "helm" in files:
                    shutil.copy(os.path.join(root, "helm"),
                                os.path.join(self._sysroot, "usr/local/bin/helm"))
                    os.chmod(os.path.join(self._sysroot, "usr/local/bin/helm"), 0o755)
                    log.info("[VDI] helm 二进制释放至 /usr/local/bin/helm")
                    break
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception as e:
            log.error("[VDI] 解压 helm 二进制失败: %s", e)

    def _write_cluster_identity(self):
        """写集群身份文件：master 持密钥，worker 持 master 地址+密钥。"""
        try:
            vdi_conf_dir = os.path.join(self._sysroot, "etc/vdi")
            self._ensure_dir(vdi_conf_dir)

            if self._role == "first-master":
                token_path = os.path.join(vdi_conf_dir, "cluster-token")
                with open(token_path, "w") as f:
                    f.write(self._token + "\n")
                os.chmod(token_path, 0o600)
                log.info("[VDI] master 集群密钥写入 /etc/vdi/cluster-token")
            else:
                join_path = os.path.join(vdi_conf_dir, "join.conf")
                with open(join_path, "w") as f:
                    f.write(f"SERVER_URL={self._server_url}\n")
                    f.write(f"TOKEN={self._token}\n")
                os.chmod(join_path, 0o600)
                log.info("[VDI] worker 加入配置写入 /etc/vdi/join.conf (server=%s)",
                         self._server_url)
        except Exception as e:
            log.error("[VDI] 写入集群身份文件失败: %s", e)

    def _render_clusterfile(self):
        """渲染 sealer Clusterfile（单 master，License 关闭，PostGuest 组件 Plugin）。"""
        try:
            opt_vdi = os.path.join(self._sysroot, "opt/vdi")
            self._ensure_dir(opt_vdi)
            clusterfile_path = os.path.join(opt_vdi, "Clusterfile")

            master_ip = self._ip or "${MASTER_IP}"
            clusterfile = f"""apiVersion: sealer.cloud/v2
kind: Cluster
metadata:
  name: vdi-cluster
spec:
  image: eki/kubernetes-noncni:v1.34.3-eki.2606.0
  env:
    - IPV6=false
    - CNI_TYPE=noncni
    - ENABLE_CLUSTER_LICENSE=false
    - IPV4_AUTODETECTION_METHOD="can-reach={master_ip}"
    - IPV4_POD_SUBNET={self._pod_cidr}
    - IPV4_SERVICE_SUBNET={self._service_cidr}
    - CHECK_VOLUME_MOUNTS=false
  ssh:
    user: root
    passwd: vdi123
  hosts:
    - ips: [{master_ip}]
      roles: [ master ]
---
apiVersion: sealer.cmss.com/v1
kind: Plugin
metadata:
  name: Label
spec:
  type: LABEL
  action: PreGuest
  data: |
    {master_ip} node-role.kubernetes.io/master=
---
apiVersion: sealer.cmss.com/v1
kind: Plugin
metadata:
  name: ClearSSH
spec:
  type: SHELL
  action: Originally
  data: |
    sed -i '/^a=/ s/^/#/' /etc/profile.d/security.sh
    mv /etc/sshbanner /etc/sshbanner.bak || echo "skip"
---
apiVersion: sealer.cmss.com/v1
kind: Plugin
metadata:
  name: VdiComponents
spec:
  type: SHELL
  action: PostGuest
  data: |
    bash /opt/vdi/scripts/install-components.sh >> /apps/logs/vdi-components.log 2>&1 || echo "WARN: VDI 组件安装失败，详见 /apps/logs/vdi-components.log"
---
apiVersion: sealer.cmss.com/v1
kind: Plugin
metadata:
  name: MyShell
spec:
  type: SHELL
  action: PostClean
  data: |
    for pid in $(ps aux | grep containerd-shim-runc-v2 | grep -v grep | awk '{{print $2}}'); do
        kill -9 $pid 2>/dev/null || true
    done
"""
            with open(clusterfile_path, "w") as f:
                f.write(clusterfile)
            log.info("[VDI] Clusterfile 渲染完成: %s (master=%s, POD=%s, SVC=%s, LICENSE=off)",
                     clusterfile_path, master_ip, self._pod_cidr, self._service_cidr)
        except Exception as e:
            log.error("[VDI] 渲染 Clusterfile 失败: %s", e)

    def _stage_components(self):
        """预置组件栈安装脚本与 clusterd 到 /opt/vdi/（master 角色）。"""
        try:
            scripts_out = os.path.join(self._sysroot, "opt/vdi/scripts")
            self._ensure_dir(scripts_out)

            # ---- install-components.sh（PostGuest Plugin 调用） ----
            install_script = os.path.join(scripts_out, "install-components.sh")
            with open(install_script, "w") as f:
                f.write(_INSTALL_COMPONENTS_SH)
            os.chmod(install_script, 0o755)

            # ---- vdi-clusterd 守护进程 ----
            clusterd_out = os.path.join(self._sysroot, "usr/local/bin/vdi-clusterd")
            with open(clusterd_out, "w") as f:
                f.write(_VDI_CLUSTERD_PY)
            os.chmod(clusterd_out, 0o755)

            log.info("[VDI] 组件安装脚本与 vdi-clusterd 预置完成")
        except Exception as e:
            log.error("[VDI] 预置组件脚本失败: %s", e)

    def _create_clusterd_service(self):
        """生成 vdi-clusterd systemd 单元（bootstrap: sealer apply → 常驻: HTTP 监听）。"""
        try:
            unit_path = os.path.join(self._sysroot, "etc/systemd/system/vdi-clusterd.service")
            with open(unit_path, "w") as f:
                f.write("""[Unit]
Description=VDI cluster daemon (sealer bootstrap + join orchestrator)
After=network-online.target sshd.service
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/usr/local/bin/vdi-cluster-bootstrap.sh
ExecStart=/usr/local/bin/vdi-clusterd
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
""")
            # bootstrap 脚本：sealer load + apply（幂等，已成功则跳过）
            bootstrap_path = os.path.join(self._sysroot, "usr/local/bin/vdi-cluster-bootstrap.sh")
            with open(bootstrap_path, "w") as f:
                f.write(_CLUSTER_BOOTSTRAP_SH)
            os.chmod(bootstrap_path, 0o755)
            log.info("[VDI] vdi-clusterd.service 与 bootstrap 脚本创建完成")
        except Exception as e:
            log.error("[VDI] 创建 vdi-clusterd 服务失败: %s", e)

    def _create_join_agent_service(self):
        """生成 vdi-join-agent oneshot 单元（worker 角色，有限重试 + stamp 幂等）。"""
        try:
            agent_path = os.path.join(self._sysroot, "usr/local/bin/vdi-join-agent.sh")
            with open(agent_path, "w") as f:
                f.write(_JOIN_AGENT_SH)
            os.chmod(agent_path, 0o755)

            unit_path = os.path.join(self._sysroot, "etc/systemd/system/vdi-join-agent.service")
            with open(unit_path, "w") as f:
                f.write("""[Unit]
Description=VDI join agent (report to master and join cluster)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vdi-join-agent.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
""")
            log.info("[VDI] vdi-join-agent.service 创建完成")
        except Exception as e:
            log.error("[VDI] 创建 vdi-join-agent 服务失败: %s", e)

    def _create_kubeconfig_service(self):
        """创建 systemd oneshot 服务，等 admin.conf 生成再拷贝到 ~/.kube/config。"""
        try:
            script_path = os.path.join(self._sysroot, "usr/local/bin/vdi-kubeconfig.sh")
            with open(script_path, "w") as f:
                f.write("""#!/bin/bash
# 等待 kubeadm 生成 admin.conf（最多 10 分钟）
SRC="/etc/kubernetes/admin.conf"
DST="/root/.kube/config"
TIMEOUT=600
ELAPSED=0

while [ ! -s "$SRC" ]; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
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
Description=Copy kubeadm admin.conf to root home after cluster up
After=vdi-clusterd.service

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

    def _setup_kubectl_convenience(self):
        """配置 kubectl 便捷访问：KUBECONFIG profile。"""
        try:
            profile_d_dir = os.path.join(self._sysroot, "etc/profile.d")
            self._ensure_dir(profile_d_dir)
            with open(os.path.join(profile_d_dir, "vdi-k8s.sh"), "w") as f:
                f.write('export KUBECONFIG="/etc/kubernetes/admin.conf"\n')
            log.info("[VDI] kubectl 便捷配置完成（profile.d KUBECONFIG）")
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

            if self._role == "first-master":
                for svc in ("vdi-clusterd.service", "vdi-kubeconfig.service"):
                    link = os.path.join(wants_dir, svc)
                    if not os.path.exists(link):
                        os.symlink(f"/etc/systemd/system/{svc}", link)
                log.info("[VDI] 激活 sshd, iscsid, vdi-clusterd, vdi-kubeconfig 开机自启")
            else:
                link = os.path.join(wants_dir, "vdi-join-agent.service")
                if not os.path.exists(link):
                    os.symlink("/etc/systemd/system/vdi-join-agent.service", link)
                log.info("[VDI] 激活 sshd, iscsid, vdi-join-agent 开机自启")
        except Exception as e:
            log.error("[VDI] 激活 systemd 服务发生错误: %s", e)


# ============================================================================
# 内嵌运行时脚本（首启阶段在目标系统执行，非安装阶段）
# ============================================================================

_CLUSTER_BOOTSTRAP_SH = r"""#!/bin/bash
# vdi-clusterd bootstrap：sealer load + apply 单机集群（幂等）
set -uo pipefail

STAMP=/var/lib/vdi/bootstrap.done
[ -f "$STAMP" ] && exit 0

mkdir -p /var/lib/vdi /apps/logs

CLUSTER_TAR=$(ls /opt/vdi/images/kubernetes_*.tar 2>/dev/null | head -1)
if [ -z "$CLUSTER_TAR" ]; then
    echo "[VDI] 集群镜像缺失 /opt/vdi/images/kubernetes_*.tar" >&2
    exit 1
fi

echo "[VDI] sealer load -i $CLUSTER_TAR"
sealer load -i "$CLUSTER_TAR" || { echo "[VDI] sealer load 失败" >&2; exit 1; }

# DHCP 场景下装机时写的静态 IP 占位失效，用首启实际出口 IP 重写 Clusterfile hosts
# 与 IPV4_AUTODETECTION_METHOD（sealer apply 需对本机 SSH 可达，静态模式此值等于静态 IP 无需改）
# 服务启动可能早于网络就绪，多源兜底 + 重试直至拿到 IP
MY_IP=""
for i in $(seq 1 15); do
    MY_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')
    [ -z "$MY_IP" ] && MY_IP=$(ip -4 -o addr show scope global 2>/dev/null | awk 'NR==1{split($4,a,"/"); print a[1]}')
    [ -z "$MY_IP" ] && MY_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -n "$MY_IP" ] && break
    echo "[VDI] 第 $i 次探测本机 IP 失败，5s 后重试"
    sleep 5
done
if [ -z "$MY_IP" ]; then
    echo "[VDI] 无法探测本机出口 IP，sealer apply 中止" >&2
    exit 1
fi
echo "[VDI] 本机出口 IP=${MY_IP}，重写 Clusterfile hosts 与 autodetection"
sed -i -E "s|ips: \[[^]]*\]|ips: [${MY_IP}]|; s|can-reach=[0-9.]+|can-reach=${MY_IP}|g" /opt/vdi/Clusterfile

# EKI 要求节点主机名非 localhost（kubeadm 节点名 = 主机名，localhost 触发其校验脚本拒绝）
CUR_HOST=$(hostname)
case "$CUR_HOST" in
    localhost*|"" )
        NEW_HOST="vdi-master-$(echo "${MY_IP##*.}")"
        echo "[VDI] 主机名为 '$CUR_HOST'，重命名为 $NEW_HOST"
        hostnamectl set-hostname "$NEW_HOST"
        grep -q "$NEW_HOST" /etc/hosts || echo "127.0.0.1 $NEW_HOST" >> /etc/hosts
        ;;
esac

echo "[VDI] sealer apply -f /opt/vdi/Clusterfile"
sealer apply -f /opt/vdi/Clusterfile || { echo "[VDI] sealer apply 失败" >&2; exit 1; }

touch "$STAMP"
echo "[VDI] 集群 bootstrap 完成"
"""

_JOIN_AGENT_SH = r"""#!/bin/bash
# vdi-join-agent：向 master vdi-clusterd 上报并等待加入完成
# 有限重试（30s × 20 ≈ 10 分钟），失败放弃，可 systemctl start 重触发
set -uo pipefail

STAMP=/var/lib/vdi/joined.stamp
[ -f "$STAMP" ] && { echo "[VDI] 已加入集群（stamp 存在），跳过"; exit 0; }

CONF=/etc/vdi/join.conf
if [ ! -f "$CONF" ]; then
    echo "[VDI] $CONF 不存在，无法加入集群" >&2
    exit 1
fi
# shellcheck disable=SC1090
source "$CONF"
: "${SERVER_URL:?join.conf 缺少 SERVER_URL}"
: "${TOKEN:?join.conf 缺少 TOKEN}"

# 本机 IP：默认路由出口网卡的主地址
MY_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')
[ -z "$MY_IP" ] && MY_IP=$(hostname -I | awk '{print $1}')

# EKI 要求节点主机名非 localhost（kubeadm 节点名 = 主机名）
CUR_HOST=$(hostname)
case "$CUR_HOST" in
    localhost*|"" )
        NEW_HOST="vdi-node-$(echo "${MY_IP##*.}")"
        echo "[VDI] 主机名为 '$CUR_HOST'，重命名为 $NEW_HOST"
        hostnamectl set-hostname "$NEW_HOST"
        grep -q "$NEW_HOST" /etc/hosts || echo "127.0.0.1 $NEW_HOST" >> /etc/hosts
        ;;
esac
MY_HOSTNAME=$(hostname)

echo "[VDI] 上报 master ${SERVER_URL} (ip=${MY_IP}, host=${MY_HOSTNAME})"

ATTEMPT=0
MAX_ATTEMPTS=20
while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    RESP=$(curl -sS -m 10 -o /tmp/vdi-join-resp.json -w "%{http_code}" \
        -X POST "${SERVER_URL}/join" \
        -H "Content-Type: application/json" \
        -d "{\"ip\":\"${MY_IP}\",\"hostname\":\"${MY_HOSTNAME}\",\"token\":\"${TOKEN}\"}" 2>&1) || RESP="000"

    case "$RESP" in
        202)
            echo "[VDI] master 已受理 join 请求（第 ${ATTEMPT} 次尝试）"
            break
            ;;
        403)
            echo "[VDI] 集群密钥校验失败（403），请核对 token 后重触发" >&2
            exit 1
            ;;
        *)
            echo "[VDI] 第 ${ATTEMPT}/${MAX_ATTEMPTS} 次上报失败 (http=${RESP})，30s 后重试"
            sleep 30
            ;;
    esac
done

if [ "$RESP" != "202" ]; then
    echo "[VDI] 重试窗口耗尽，放弃加入。修正后可 systemctl start vdi-join-agent 重触发" >&2
    exit 1
fi

# 轮询 join 状态直至 done/failed（server 端 sealer join 耗时长，给足 60 分钟）
for i in $(seq 1 120); do
    STATUS=$(curl -sS -m 10 "${SERVER_URL}/join/status?ip=${MY_IP}&token=${TOKEN}" 2>/dev/null \
        | sed -n 's/.*"state"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    case "$STATUS" in
        done)
            touch "$STAMP"
            echo "[VDI] 已成功加入集群"
            exit 0
            ;;
        failed)
            echo "[VDI] master 端 sealer join 失败，详情见 master journald (vdi-clusterd)" >&2
            exit 1
            ;;
        *)
            sleep 30
            ;;
    esac
done

echo "[VDI] 等待 join 完成超时（60 分钟）" >&2
exit 1
"""

_INSTALL_COMPONENTS_SH = r"""#!/bin/bash
# VDI 组件栈安装（sealer PostGuest Plugin 调用）
# 顺序：registry 检查 → 镜像 load+push → Kube-OVN → KubeVirt/CDI → Longhorn → kagent
set -uo pipefail

export KUBECONFIG=/etc/kubernetes/admin.conf
export PATH="/usr/local/bin:$PATH"

IMG_DIR=/opt/vdi/images/components
CHART_DIR=/opt/vdi/charts
MANIFEST_DIR=/opt/vdi/manifests
REGISTRY="127.0.0.1:5000"

log() { echo "[VDI-COMP] $(date '+%F %T') $*"; }

# ---- 1. sealer-registry 就绪 ----
log "等待 sealer-registry ..."
for i in $(seq 1 30); do
    nerdctl ps 2>/dev/null | grep -q "sealer-registry.*Up" && break
    nerdctl start sealer-registry >/dev/null 2>&1 || true
    sleep 10
done
nerdctl ps | grep "sealer-registry" || { log "ERROR: sealer-registry 未就绪"; exit 1; }

# ---- 2. 组件镜像 load + push ----
REGISTRY_PREFIX="${REGISTRY}/vdi"
if [ -d "$IMG_DIR" ]; then
    for tar_file in "$IMG_DIR"/*.tar "$IMG_DIR"/*.tar.zst "$IMG_DIR"/*.tar.gz; do
        [ -f "$tar_file" ] || continue
        log "nerdctl load < $(basename "$tar_file")"
        case "$tar_file" in
            *.zst) zstd -dc "$tar_file" | nerdctl load ;;
            *.gz)  zcat "$tar_file" | nerdctl load ;;
            *)     nerdctl load -i "$tar_file" ;;
        esac || { log "ERROR: load $tar_file 失败"; exit 1; }
    done
fi

# 推送全部本地业务镜像到内嵌 registry（跳过 cmss 系统镜像与 registry 自身）
for img in $(nerdctl images --format '{{.Repository}}:{{.Tag}}' | grep -vE "^(cmss/|${REGISTRY}|sealer|<none>)"); do
    target="${REGISTRY_PREFIX}/$(basename "${img%%:*}"):$(echo "${img##*:}")"
    log "push $img → $target"
    nerdctl tag "$img" "$target" && nerdctl push "$target" || { log "ERROR: push $img 失败"; exit 1; }
done

# ---- 3. Kube-OVN（首个 CNI，集群 Ready 前提） ----
KOVN_CHART=$(ls "$CHART_DIR"/kube-ovn-*.tgz 2>/dev/null | head -1)
if [ -n "$KOVN_CHART" ] && command -v helm >/dev/null; then
    log "helm install kube-ovn ($KOVN_CHART)"
    helm install kube-ovn "$KOVN_CHART" --namespace kube-system \
        --set global.images.registry="${REGISTRY_PREFIX}" || log "WARN: kube-ovn helm 安装失败"
else
    log "WARN: kube-ovn chart 或 helm 缺失，CNI 未安装（集群将保持 NotReady）"
fi

# ---- 4. KubeVirt / CDI（operator → 等 CRD → CR） ----
for prefix in kubevirt cdi; do
    op="$MANIFEST_DIR/${prefix}-operator.yaml"
    cr="$MANIFEST_DIR/${prefix}-cr.yaml"
    [ -f "$op" ] && { log "apply ${prefix} operator"; kubectl apply -f "$op" || log "WARN: ${prefix} operator apply 失败"; }
done

log "等待 KubeVirt/CDI CRD Established"
kubectl wait --for=condition=Established crd/kubevirts.kubevirt.io --timeout=300s 2>/dev/null || true
kubectl wait --for=condition=Established crd/cdis.cdi.kubevirt.io --timeout=300s 2>/dev/null || true

for prefix in kubevirt cdi; do
    cr="$MANIFEST_DIR/${prefix}-cr.yaml"
    [ -f "$cr" ] && { log "apply ${prefix} CR"; kubectl apply -f "$cr" || log "WARN: ${prefix} CR apply 失败"; }
done

# ---- 5. Longhorn ----
LH_CHART=$(ls "$CHART_DIR"/longhorn-*.tgz 2>/dev/null | head -1)
if [ -n "$LH_CHART" ] && command -v helm >/dev/null; then
    log "helm install longhorn ($LH_CHART)"
    helm install longhorn "$LH_CHART" --namespace longhorn-system --create-namespace \
        --set global.images.registry="${REGISTRY_PREFIX}" \
        --set persistence.defaultClassReplicaCount=1 || log "WARN: longhorn helm 安装失败"
fi

log "VDI 组件栈安装流程结束"
"""

_VDI_CLUSTERD_PY = r"""#!/usr/bin/env python3
# vdi-clusterd：master 上的 join 编排守护进程。
#
# - HTTP :9345 监听 worker 上报（POST /join）与状态查询（GET /join/status）
# - 预共享密钥校验（/etc/vdi/cluster-token）
# - 串行执行 sealer join（单并发队列），成功后 kubectl label node
# - 状态落盘 /var/lib/vdi/join-state/<ip>
import ipaddress
import json
import logging
import os
import queue
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format="[vdi-clusterd] %(message)s")
log = logging.getLogger("vdi-clusterd")

LISTEN_PORT = 9345
STATE_DIR = "/var/lib/vdi/join-state"
TOKEN_FILE = "/etc/vdi/cluster-token"
JOIN_PASSWD_FILE = "/etc/vdi/sealer-join.conf"
KUBECONFIG = "/etc/kubernetes/admin.conf"

_job_queue = queue.Queue()
_state_lock = threading.Lock()


def _load_token():
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except OSError:
        log.error("无法读取 %s", TOKEN_FILE)
        return ""


def _load_join_passwd():
    try:
        with open(JOIN_PASSWD_FILE) as f:
            for line in f:
                if line.startswith("PASSWD="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _read_state(ip):
    path = os.path.join(STATE_DIR, ip)
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def _write_state(ip, state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, ip), "w") as f:
        f.write(state)


def _join_worker():
    # 串行消费 join 队列：sealer join + kubectl label
    passwd = _load_join_passwd()
    while True:
        item = _job_queue.get()
        ip, hostname = item["ip"], item.get("hostname", "")
        try:
            _write_state(ip, "joining")
            cmd = ["sealer", "join", "--nodes", ip, "--user", "root"]
            if passwd:
                cmd += ["--passwd", passwd]
            log.info("执行: %s", " ".join(cmd[:-1] + ["***"]) if passwd else " ".join(cmd))
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if proc.returncode != 0:
                log.error("sealer join %s 失败: %s", ip, proc.stderr[-2000:])
                _write_state(ip, "failed")
                continue

            # join 成功 → 打 node label（node 名默认为主机名）
            env = dict(os.environ, KUBECONFIG=KUBECONFIG)
            node_name = hostname or ip
            subprocess.run(
                ["kubectl", "label", "node", node_name, "node-role.kubernetes.io/node=", "--overwrite"],
                capture_output=True, text=True, timeout=60, env=env)
            _write_state(ip, "done")
            log.info("节点 %s (%s) 加入完成", ip, node_name)
        except Exception as e:
            log.error("join %s 异常: %s", ip, e)
            _write_state(ip, "failed")
        finally:
            _job_queue.task_done()


class Handler(BaseHTTPRequestHandler):
    server_version = "vdi-clusterd/1.0"

    def _json_response(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_token(self, token):
        expected = _load_token()
        return expected and token == expected

    def do_POST(self):
        if self.path != "/join":
            self._json_response(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json_response(400, {"error": "bad request"})
            return

        ip = str(body.get("ip", ""))
        token = str(body.get("token", ""))
        hostname = str(body.get("hostname", ""))

        try:
            ipaddress.ip_address(ip)
        except ValueError:
            self._json_response(400, {"error": "invalid ip"})
            return
        if not self._check_token(token):
            log.warning("拒绝 join（token 不匹配）: %s", ip)
            self._json_response(403, {"error": "token mismatch"})
            return

        with _state_lock:
            state = _read_state(ip)
            if state in ("pending", "joining", "done"):
                log.info("重复上报 %s（当前 %s），忽略", ip, state)
                self._json_response(202, {"state": state})
                return
            _write_state(ip, "pending")
            _job_queue.put({"ip": ip, "hostname": hostname})

        log.info("受理 join: %s (%s)", ip, hostname)
        self._json_response(202, {"state": "pending"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/join/status":
            self._json_response(404, {"error": "not found"})
            return
        qs = parse_qs(parsed.query)
        ip = qs.get("ip", [""])[0]
        token = qs.get("token", [""])[0]
        if not self._check_token(token):
            self._json_response(403, {"error": "token mismatch"})
            return
        self._json_response(200, {"ip": ip, "state": _read_state(ip)})

    def log_message(self, fmt, *args):
        log.debug("http: " + fmt, *args)


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    worker = threading.Thread(target=_join_worker, daemon=True)
    worker.start()
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    log.info("监听 :%d，等待 worker 上报", LISTEN_PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
"""
