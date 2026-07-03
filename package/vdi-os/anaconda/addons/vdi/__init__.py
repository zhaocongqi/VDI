"""VDI 平台系统引导安装 Addon 入口（用纯 Python execute 实现全自动写盘持久化）"""
import os
import uuid
import logging
import subprocess
import shutil
from vdi.constants import VDI

log = logging.getLogger(__name__)

# ----------------- 环境安全性防御 -----------------
try:
    from pyanaconda.addons import AnacondaAddon
    _has_anaconda_gui = True
except ImportError:
    _has_anaconda_gui = False
    class AnacondaAddon(object):
        pass

__all__ = ["VdiAddon"]


class VdiAddon(AnacondaAddon):
    """VDI 平台系统配置与网络持久化 Addon"""

    def __init__(self):
        super().__init__()

    def execute(self, storage, ksdata, instClass):
        """Anaconda 在写入目标系统配置的最后阶段自动调用此方法。"""
        if not _has_anaconda_gui:
            log.warning("在非 GUI 环境下调用了 VdiAddon.execute，直接跳过")
            return

        log.info(">>> [VDI] 开始执行 VdiAddon.execute 全量系统配置写入")
        sysroot = storage.config.sysroot
        
        # ============================================================
        # 1. 读取网络与虚拟 IP 配置 (从 DBus 代理)
        # ============================================================
        try:
            proxy = VDI.get_proxy()
            mode = proxy.Mode or "single"
            interface = proxy.Interface or ""
            interface2 = proxy.Interface2 or ""
            bond_mode = proxy.BondMode or "active-backup"
            ip = proxy.Ip or ""
            vip = proxy.Vip or ""
        except Exception as e:
            log.error("[VDI] 获取 D-Bus 属性失败，无法下发网络配置: %s", e)
            return

        # ============================================================
        # 2. 网卡与 Bond 持久化写入
        # ============================================================
        if ip and interface:
            conn_dir = os.path.join(sysroot, "etc/NetworkManager/system-connections")
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

            gateway = ip.rsplit(".", 1)[0] + ".1"

            if mode == "bond" and interface2:
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

[bond]
options=mode={bond_mode},miimon=100

[ipv4]
method=manual
addresses={ip}/24,{gateway}
""")
                os.chmod(bond_path, 0o600)

                port1_path = os.path.join(conn_dir, f"{interface}.nmconnection")
                with open(port1_path, "w") as f:
                    f.write(f"""[connection]
id={interface}
uuid={port1_uuid}
type=ethernet
interface-name={interface}
master={bond_uuid}
slave-type=bond
autoconnect=true
""")
                os.chmod(port1_path, 0o600)

                port2_path = os.path.join(conn_dir, f"{interface2}.nmconnection")
                with open(port2_path, "w") as f:
                    f.write(f"""[connection]
id={interface2}
uuid={port2_uuid}
type=ethernet
interface-name={interface2}
master={bond_uuid}
slave-type=bond
autoconnect=true
""")
                os.chmod(port2_path, 0o600)
                log.info("[VDI] 成功写入 Bond0 网卡绑定配置 (%s + %s)", interface, interface2)
            else:
                # ----------------- 单网卡模式 (Single) -----------------
                single_uuid = str(uuid.uuid4())
                single_path = os.path.join(conn_dir, f"{interface}.nmconnection")
                with open(single_path, "w") as f:
                    f.write(f"""[connection]
id={interface}
uuid={single_uuid}
type=ethernet
interface-name={interface}
autoconnect=true

[ipv4]
method=manual
addresses={ip}/24,{gateway}
""")
                os.chmod(single_path, 0o600)
                log.info("[VDI] 成功写入单网卡配置 %s", interface)

            # 写入 VDI 内部网络配置文件
            vdi_conf_dir = os.path.join(sysroot, "etc/vdi")
            if not os.path.exists(vdi_conf_dir):
                os.makedirs(vdi_conf_dir, mode=0o755)
            with open(os.path.join(vdi_conf_dir, "network.conf"), "w") as f:
                f.write(f"""# VDI Management Network Config
MODE={mode}
INTERFACE={interface}
INTERFACE2={interface2}
BOND_MODE={bond_mode}
IP={ip}
VIP={vip}
""")
        else:
            log.warning("[VDI] 未配置有效的 IP 或主网卡，跳过网络配置写入。")

        # ============================================================
        # 3. 影子密码 (shadow) 强行覆写与 SSH Root 登录配置 (防强密码强度机制)
        # ============================================================
        if ksdata.rootpw and ksdata.rootpw.password:
            try:
                import crypt
                plain_pass = ksdata.rootpw.password
                hash_val = crypt.crypt(plain_pass, crypt.mksalt(crypt.METHOD_SHA512))
                
                shadow_path = os.path.join(sysroot, "etc/shadow")
                if os.path.exists(shadow_path):
                    with open(shadow_path, "r") as f:
                        lines = f.readlines()
                    new_lines = []
                    for line in lines:
                        if line.startswith("root:"):
                            parts = line.split(":")
                            parts[1] = hash_val
                            line = ":".join(parts)
                        new_lines.append(line)
                    with open(shadow_path, "w") as f:
                        f.writelines(new_lines)
                    log.info("[VDI] 成功通过 shadow 覆写完成 root 密码强制写入")
            except Exception as e:
                log.error("[VDI] 影子密码强行覆写发生错误: %s", e)

        # 配置允许 root + 密码登录，并激活 sshd 服务
        try:
            sshd_conf_dir = os.path.join(sysroot, "etc/ssh/sshd_config.d")
            if not os.path.exists(sshd_conf_dir):
                os.makedirs(sshd_conf_dir, mode=0o755)
            with open(os.path.join(sshd_conf_dir, "00-vdi-root-login.conf"), "w") as f:
                f.write("PermitRootLogin yes\nPasswordAuthentication yes\nUseDNS no\nGSSAPIAuthentication no\n")
            log.info("[VDI] 成功写入 00-vdi-root-login.conf SSH 配置文件")
        except Exception as e:
            log.error("[VDI] 写入 SSH 配置文件发生错误: %s", e)

        # ============================================================
        # 4. 数据盘自动探测、格式化与 fstab 挂载 (LABEL 挂载)
        # ============================================================
        try:
            all_disks = [d for d in storage.disks if d.isDisk]
            boot_disk = storage.bootloader.stage1_device
            boot_disk_name = boot_disk.name if boot_disk else ""
            if not boot_disk_name and all_disks:
                boot_disk_name = all_disks[0].name

            data_disk = None
            for d in all_disks:
                if d.name != boot_disk_name:
                    data_disk = d
                    break

            if data_disk:
                data_dev_path = f"/dev/{data_disk.name}"
                log.info("[VDI] 探测到物理数据盘: %s, 开始格式化...", data_dev_path)
                subprocess.run(["mkfs.ext4", "-F", "-L", "VDI_LH_DEFAULT", data_dev_path], check=True)
                
                longhorn_dir = os.path.join(sysroot, "var/lib/longhorn")
                if not os.path.exists(longhorn_dir):
                    os.makedirs(longhorn_dir, mode=0o755)

                fstab_path = os.path.join(sysroot, "etc/fstab")
                with open(fstab_path, "a") as f:
                    f.write("\nLABEL=VDI_LH_DEFAULT /var/lib/longhorn ext4 defaults,noatime,nofail 0 2\n")
                log.info("[VDI] 数据盘格式化并成功挂载至 /var/lib/longhorn")
            else:
                log.warning("[VDI] 未探测到其它物理数据盘，跳过数据盘处理")
        except Exception as e:
            log.error("[VDI] 数据盘处理发生错误: %s", e)

        # ============================================================
        # 5. 复制 ISO 离线资源 Bundle 到目标磁盘
        # ============================================================
        repo_dir = "/run/install/repo"
        bundle_dir = os.path.join(repo_dir, "bundle/vdi")
        
        if os.path.exists(bundle_dir):
            log.info("[VDI] 发现离线资源 bundle，开始释放...")
            
            # 5.1 拷贝 RKE2 离线镜像 (images)
            target_images_dir = os.path.join(sysroot, "var/lib/rancher/rke2/agent/images")
            if not os.path.exists(target_images_dir):
                os.makedirs(target_images_dir, mode=0o755)
            src_images_dir = os.path.join(bundle_dir, "images")
            if os.path.exists(src_images_dir):
                for f in os.listdir(src_images_dir):
                    if f.endswith(".tar.zst"):
                        shutil.copy(os.path.join(src_images_dir, f), target_images_dir)
            log.info("[VDI] 离线 RKE2 镜像拷贝完成")

            # 5.2 拷贝 Helm Charts 和 Manifests (KubeVirt, Longhorn 等)
            target_charts_dir = os.path.join(sysroot, "var/lib/rancher/rke2/server/charts")
            if not os.path.exists(target_charts_dir):
                os.makedirs(target_charts_dir, mode=0o755)
            src_charts_dir = os.path.join(bundle_dir, "charts")
            if os.path.exists(src_charts_dir):
                for f in os.listdir(src_charts_dir):
                    if f.endswith(".tgz"):
                        shutil.copy(os.path.join(src_charts_dir, f), target_charts_dir)

            target_manifests_dir = os.path.join(sysroot, "var/lib/rancher/rke2/server/manifests")
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
                tmp_tar_path = os.path.join(sysroot, "tmp", rke2_tar)
                shutil.copy(os.path.join(src_binaries_dir, rke2_tar), tmp_tar_path)
                
                # 创建解压目标目录并解压
                usr_local = os.path.join(sysroot, "usr/local")
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
        else:
            log.warning("[VDI] 未在光盘安装源中找到离线资源 bundle/vdi，跳过离线资源释放")

        # ============================================================
        # 6. 动态配置并下发 RKE2 config.yaml
        # ============================================================
        # 智能推导是否为 Agent（从节点）：如果配置了 ServerURL 或者是加入已有集群，则为 Agent
        # 我们还可以从 VDI config (如果有) 或者默认规则中推导
        is_agent = False
        server_url = ""
        token = "vdi-cluster-token" # 默认初始 token
        
        # 检查网络是否配置了 server-url 属性（暂时使用默认配置）
        rke2_conf_dir = os.path.join(sysroot, "etc/rancher/rke2")
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
                    if ip or vip:
                        f.write("tls-san:\n")
                        if vip:
                            f.write(f"  - {vip}\n")
                        if ip:
                            f.write(f"  - {ip}\n")
                else:
                    f.write(f"""server: {server_url}
token: "{token}"
kubelet-arg:
  - "max-pods=200"
""")
            log.info("[VDI] RKE2 核心配置文件 config.yaml 写入完成")
        except Exception as e:
            log.error("[VDI] 写入 RKE2 config.yaml 失败: %s", e)

        # ============================================================
        # 7. 创建 Wants Wants 链接，激活 systemd 服务 (开机自启)
        # ============================================================
        try:
            wants_dir = os.path.join(sysroot, "etc/systemd/system/multi-user.target.wants")
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

            # 激活 RKE2 服务 (rke2-server 或者是 rke2-agent)
            service_name = "rke2-server" if not is_agent else "rke2-agent"
            rke2_link = os.path.join(wants_dir, f"{service_name}.service")
            if not os.path.exists(rke2_link):
                os.symlink(f"/usr/local/lib/systemd/system/{service_name}.service", rke2_link)

            log.info("[VDI] 成功激活 sshd, iscsid 及 %s 服务开机自启", service_name)
        except Exception as e:
            log.error("[VDI] 激活 systemd 服务发生错误: %s", e)

        log.info(">>> [VDI] VdiAddon.execute 全部配置下发与释放成功完成！")
