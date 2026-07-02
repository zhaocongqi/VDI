"""VDI 平台系统引导安装 Addon 入口（采用环境隔离的防御性导入）"""
import os
import uuid
import logging
from vdi.constants import VDI

log = logging.getLogger(__name__)

# ----------------- 环境安全性防御 -----------------
# D-Bus 后台服务环境并不包含 pyanaconda.addons 等前端 GUI 库，
# 通过 conditional import 确保后台总线服务加载本包时不会发生 ModuleNotFoundError。
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

        log.info(">>> VDI Addon execute 阶段启动")
        sysroot = storage.config.sysroot
        
        # 1. 从 DBus 代理获取用户通过 GUI 输入的最新网络配置
        try:
            proxy = VDI.get_proxy()
            mode = proxy.Mode or "single"
            interface = proxy.Interface or ""
            interface2 = proxy.Interface2 or ""
            bond_mode = proxy.BondMode or "active-backup"
            ip = proxy.Ip or ""
            vip = proxy.Vip or ""
        except Exception as e:
            log.error("VDI execute 获取 D-Bus 属性失败: %s", e)
            return

        # 2. 检查配置，避免因未配置导致空写入
        if not ip or not interface:
            log.warning("未配置有效的 IP 或主网卡，跳过网卡配置文件生成。")
            return

        conn_dir = os.path.join(sysroot, "etc/NetworkManager/system-connections")
        if not os.path.exists(conn_dir):
            try:
                os.makedirs(conn_dir, mode=0o755)
            except Exception as e:
                log.error("创建目标网卡配置目录失败: %s", e)
                return

        # 动态清理原有该网卡的旧配置文件，防止冲突
        for f in os.listdir(conn_dir):
            if f.endswith(".nmconnection"):
                try:
                    os.remove(os.path.join(conn_dir, f))
                except Exception:
                    pass

        # 默认网关设置：根据配置的静态 IP 自动推导，例如 192.168.220.138 网关默认为 192.168.220.1
        gateway = ip.rsplit(".", 1)[0] + ".1"

        if mode == "bond" and interface2:
            # ----------------- 绑定模式 (Bonding) -----------------
            bond_uuid = str(uuid.uuid4())
            port1_uuid = str(uuid.uuid4())
            port2_uuid = str(uuid.uuid4())

            # 2.1 写入主 bond0.nmconnection 配置文件（网卡名 bond0）
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

            # 2.2 写入 Slave 1 (主物理网卡) 配置文件
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

            # 2.3 写入 Slave 2 (备物理网卡) 配置文件
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
            log.info("成功为目标系统配置网卡绑定 Bond0 (%s + %s, 模式=%s)", interface, interface2, bond_mode)

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
            log.info("成功为目标系统配置单网卡 %s", interface)

        # 3. 将完整的网络配置和虚拟 IP 写入 VDI 系统的配置文件，供开机引导和 K8s 网络组件消费
        vdi_conf_dir = os.path.join(sysroot, "etc/vdi")
        if not os.path.exists(vdi_conf_dir):
            try:
                os.makedirs(vdi_conf_dir, mode=0o755)
            except Exception:
                pass

        vdi_conf_path = os.path.join(vdi_conf_dir, "network.conf")
        try:
            with open(vdi_conf_path, "w") as f:
                f.write(f"""# VDI Management Network Config
MODE={mode}
INTERFACE={interface}
INTERFACE2={interface2}
BOND_MODE={bond_mode}
IP={ip}
VIP={vip}
""")
            log.info("成功生成 VDI 网络配置文件 %s", vdi_conf_path)
        except Exception as e:
            log.error("写入 VDI 网络配置文件失败: %s", e)
