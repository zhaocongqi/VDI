"""VDI 安装配置 GUI Spoke（严格参考 com_redhat_kdump/gui/spokes/kdump.py 架构）"""
import ipaddress
import logging
import os

from gi.repository import Gtk
from pyanaconda.modules.common.util import is_module_available
from pyanaconda.ui.categories.system import SystemCategory
from pyanaconda.ui.gui.spokes import NormalSpoke

from vdi.constants import VDI

log = logging.getLogger(__name__)

__all__ = ["VdiInstallConfigSpoke"]

_VIRTUAL_PREFIXES = ("virbr", "docker", "veth", "br-", "ovs-", "lo")


def _is_valid_ipv4(text):
    try:
        ipaddress.IPv4Address(text)
        return True
    except (ValueError, ipaddress.AddressValueError):
        return False


def _is_valid_cidr(text):
    try:
        ipaddress.IPv4Network(text, strict=False)
        return True
    except (ValueError, ipaddress.NetmaskValueError, ipaddress.AddressValueError):
        return False


def _is_valid_netmask(text):
    try:
        ipaddress.IPv4Network(f"0.0.0.0/{text}")
        return True
    except (ValueError, ipaddress.NetmaskValueError):
        return False


class WindowWrapper(Gtk.Box):
    """GTK 窗口包裹代理。

    直接继承自 Gtk.Box 以通过 Gtk.Stack C 语言底层的类型安全校验，
    并在顶部动态组装包含"完成"按钮的导航条，实现退出并保存配置。
    """

    def __init__(self, real_box, spoke_instance):
        Gtk.Box.__init__(self)
        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_spacing(6)
        self._real_box = real_box
        self._spoke = spoke_instance

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header_box.set_margin_top(12)
        header_box.set_margin_bottom(12)
        header_box.set_margin_start(18)
        header_box.set_margin_end(18)

        done_button = Gtk.Button.new_with_mnemonic("完成 (_D)")
        done_button.get_style_context().add_class("suggested-action")
        done_button.set_size_request(80, 36)
        done_button.connect("clicked", self._on_done_clicked)
        header_box.pack_start(done_button, False, False, 0)

        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold'>VDI 安装配置</span>")
        title_label.set_margin_start(18)
        header_box.pack_start(title_label, False, False, 0)

        self.pack_start(header_box, False, False, 0)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.pack_start(separator, False, False, 0)
        self.pack_start(self._real_box, True, True, 0)
        self.show_all()

    def _on_done_clicked(self, button):
        if self._spoke:
            self._spoke.on_back_clicked(button)

    def set_beta(self, beta):
        pass

    def set_property(self, name, value):
        if name in ("distribution", "window-name", "window_name"):
            return
        return Gtk.Box.set_property(self, name, value)

    def get_property(self, name):
        if name in ("distribution", "window-name", "window_name"):
            return ""
        return Gtk.Box.get_property(self, name)

    def connect_after(self, signal, callback):
        if signal == "help-button-clicked":
            return
        return Gtk.Box.connect_after(self, signal, callback)


class VdiInstallConfigSpoke(NormalSpoke):
    """VDI 安装配置图形 Spoke。

    在 Anaconda 安装器主界面（Hub）的 SYSTEM 分类下显示，
    提供网络/集群/系统三层配置入口，含实时输入校验。
    """

    builderObjects = [
        "vdi_config_box",
        "network_mode_combo",
        "mode_combo",
        "interface_combo",
        "interface2_label",
        "interface2_combo",
        "bond_mode_label",
        "bond_mode_combo",
        "static_ip_frame",
        "ip_entry", "ip_icon",
        "vip_entry", "vip_icon",
        "netmask_entry", "netmask_icon",
        "gateway_entry", "gateway_icon",
        "dns_entry", "dns_icon",
        "role_combo",
        "server_url_label", "server_url_entry", "server_url_icon",
        "token_label", "token_entry", "token_icon",
        "pod_cidr_entry", "pod_cidr_icon",
        "service_cidr_entry", "service_cidr_icon",
        "join_cidr_entry", "join_cidr_icon",
        "data_disk_combo",
    ]
    mainWidgetName = "vdi_config_box"
    uiFile = "vdi_install_config.glade"

    icon = "preferences-system-symbolic"
    title = "VDI 安装配置"
    category = SystemCategory

    @classmethod
    def should_run(cls, environment, data):
        return is_module_available(VDI)

    @property
    def window(self):
        from pyanaconda.ui.gui import GUIObject
        raw_win = GUIObject.window.fget(self)
        if self._wrapped_window is None or self._wrapped_window._real_box != raw_win:
            self._wrapped_window = WindowWrapper(raw_win, self)
        return self._wrapped_window

    def __init__(self, data, storage, payload):
        self._wrapped_window = None
        self._network_mode_combo = None
        self._mode_combo = None
        self._interface_combo = None
        self._interface2_label = None
        self._interface2_combo = None
        self._bond_mode_label = None
        self._bond_mode_combo = None
        self._static_ip_frame = None
        self._ip_entry = None
        self._vip_entry = None
        self._netmask_entry = None
        self._gateway_entry = None
        self._dns_entry = None
        self._role_combo = None
        self._server_url_label = None
        self._server_url_entry = None
        self._token_label = None
        self._token_entry = None
        self._pod_cidr_entry = None
        self._service_cidr_entry = None
        self._join_cidr_entry = None
        self._data_disk_combo = None
        self._ip_icon = None
        self._vip_icon = None
        self._netmask_icon = None
        self._gateway_icon = None
        self._dns_icon = None
        self._server_url_icon = None
        self._token_icon = None
        self._pod_cidr_icon = None
        self._service_cidr_icon = None
        self._join_cidr_icon = None
        self._validation_errors = set()
        NormalSpoke.__init__(self, data, storage, payload)
        self._proxy = VDI.get_proxy()

        from pyanaconda.modules.common.constants.services import NETWORK
        try:
            self.network_proxy = NETWORK.get_proxy()
        except Exception as e:
            log.error("无法获取 NetworkManager D-Bus 代理: %s", e)
            self.network_proxy = None

        self._configured = False
        log.debug("VdiInstallConfigSpoke 已初始化, proxy=%s", self._proxy)

    def initialize(self):
        NormalSpoke.initialize(self)
        # 网络配置区
        self._network_mode_combo = self.builder.get_object("network_mode_combo")
        self._mode_combo = self.builder.get_object("mode_combo")
        self._interface_combo = self.builder.get_object("interface_combo")
        self._interface2_label = self.builder.get_object("interface2_label")
        self._interface2_combo = self.builder.get_object("interface2_combo")
        self._bond_mode_label = self.builder.get_object("bond_mode_label")
        self._bond_mode_combo = self.builder.get_object("bond_mode_combo")
        # 静态 IP 区
        self._static_ip_frame = self.builder.get_object("static_ip_frame")
        self._ip_entry = self.builder.get_object("ip_entry")
        self._vip_entry = self.builder.get_object("vip_entry")
        self._netmask_entry = self.builder.get_object("netmask_entry")
        self._gateway_entry = self.builder.get_object("gateway_entry")
        self._dns_entry = self.builder.get_object("dns_entry")
        self._ip_icon = self.builder.get_object("ip_icon")
        self._vip_icon = self.builder.get_object("vip_icon")
        self._netmask_icon = self.builder.get_object("netmask_icon")
        self._gateway_icon = self.builder.get_object("gateway_icon")
        self._dns_icon = self.builder.get_object("dns_icon")
        # 集群配置区
        self._role_combo = self.builder.get_object("role_combo")
        self._server_url_label = self.builder.get_object("server_url_label")
        self._server_url_entry = self.builder.get_object("server_url_entry")
        self._server_url_icon = self.builder.get_object("server_url_icon")
        self._token_label = self.builder.get_object("token_label")
        self._token_entry = self.builder.get_object("token_entry")
        self._token_icon = self.builder.get_object("token_icon")
        self._pod_cidr_entry = self.builder.get_object("pod_cidr_entry")
        self._service_cidr_entry = self.builder.get_object("service_cidr_entry")
        self._join_cidr_entry = self.builder.get_object("join_cidr_entry")
        self._pod_cidr_icon = self.builder.get_object("pod_cidr_icon")
        self._service_cidr_icon = self.builder.get_object("service_cidr_icon")
        self._join_cidr_icon = self.builder.get_object("join_cidr_icon")
        # 系统配置区
        self._data_disk_combo = self.builder.get_object("data_disk_combo")

        # 绑定下拉框联动信号
        self._network_mode_combo.connect("changed", self._on_network_mode_changed)
        self._mode_combo.connect("changed", self._on_mode_changed)
        self._role_combo.connect("changed", self._on_role_changed)

        # 绑定输入校验信号
        for entry, icon, validator in [
            (self._ip_entry, self._ip_icon, _is_valid_ipv4),
            (self._vip_entry, self._vip_icon, _is_valid_ipv4),
            (self._netmask_entry, self._netmask_icon, _is_valid_netmask),
            (self._gateway_entry, self._gateway_icon, _is_valid_ipv4),
            (self._dns_entry, self._dns_icon, _is_valid_ipv4),
            (self._pod_cidr_entry, self._pod_cidr_icon, _is_valid_cidr),
            (self._service_cidr_entry, self._service_cidr_icon, _is_valid_cidr),
            (self._join_cidr_entry, self._join_cidr_icon, _is_valid_cidr),
        ]:
            entry.connect("changed", self._on_validate_entry, icon, validator)

        self._server_url_entry.connect("changed", self._on_validate_server_url)

        self._sync_visibility()
        log.debug("VdiInstallConfigSpoke 控件初始化完成")

    # ==================== 校验逻辑 ====================

    def _set_icon(self, icon, valid):
        if valid:
            icon.set_from_icon_name("gtk-apply", Gtk.IconSize.LARGE_TOOLBAR)
        else:
            icon.set_from_icon_name("gtk-no", Gtk.IconSize.LARGE_TOOLBAR)

    def _on_validate_entry(self, entry, icon, validator):
        text = entry.get_text().strip()
        if not text:
            icon.clear()
            self._validation_errors.discard(entry)
        elif validator(text):
            self._set_icon(icon, True)
            self._validation_errors.discard(entry)
        else:
            self._set_icon(icon, False)
            self._validation_errors.add(entry)

    def _on_validate_server_url(self, _widget=None):
        if self._proxy.Role != "agent":
            self._server_url_icon.clear()
            self._validation_errors.discard("server_url")
            return
        url = self._server_url_entry.get_text().strip()
        if not url:
            self._set_icon(self._server_url_icon, False)
            self._validation_errors.add("server_url")
        else:
            self._set_icon(self._server_url_icon, True)
            self._validation_errors.discard("server_url")

    def _validate_all_defaults(self):
        """refresh() 程序化 set_text 不触发 changed 信号，手动校验使默认值显示图标。"""
        if self._proxy.NetworkMode == "static":
            for entry, icon, validator in [
                (self._ip_entry, self._ip_icon, _is_valid_ipv4),
                (self._vip_entry, self._vip_icon, _is_valid_ipv4),
                (self._netmask_entry, self._netmask_icon, _is_valid_netmask),
                (self._gateway_entry, self._gateway_icon, _is_valid_ipv4),
                (self._dns_entry, self._dns_icon, _is_valid_ipv4),
            ]:
                self._on_validate_entry(entry, icon, validator)
        for entry, icon, validator in [
            (self._pod_cidr_entry, self._pod_cidr_icon, _is_valid_cidr),
            (self._service_cidr_entry, self._service_cidr_icon, _is_valid_cidr),
            (self._join_cidr_entry, self._join_cidr_icon, _is_valid_cidr),
        ]:
            self._on_validate_entry(entry, icon, validator)
        self._on_validate_server_url()

    # ==================== 显隐联动 ====================

    def _sync_visibility(self):
        network_mode = self._proxy.NetworkMode or "dhcp"
        mode = self._proxy.Mode or "single"
        role = self._proxy.Role or "server"

        is_static = (network_mode == "static")
        self._static_ip_frame.set_visible(is_static)

        is_bond = (mode == "bond")
        self._interface2_label.set_visible(is_bond)
        self._interface2_combo.set_visible(is_bond)
        self._bond_mode_label.set_visible(is_bond)
        self._bond_mode_combo.set_visible(is_bond)

        is_agent = (role == "agent")
        self._server_url_label.set_visible(is_agent)
        self._server_url_entry.set_visible(is_agent)
        self._server_url_icon.set_visible(is_agent)
        self._token_label.set_visible(is_agent)
        self._token_entry.set_visible(is_agent)
        self._token_icon.set_visible(is_agent)

    def _on_network_mode_changed(self, combo):
        active_id = combo.get_active_id() or "dhcp"
        self._proxy.NetworkMode = active_id
        self._sync_visibility()

    def _on_mode_changed(self, combo):
        active_id = combo.get_active_id() or "single"
        self._proxy.Mode = active_id
        self._sync_visibility()

    def _on_role_changed(self, combo):
        active_id = combo.get_active_id() or "server"
        self._proxy.Role = active_id
        self._sync_visibility()

    # ==================== 网卡/磁盘填充 ====================

    def _fill_network_interfaces(self):
        if not self.network_proxy:
            return
        try:
            from pyanaconda.modules.common.structures.network import NetworkDeviceInfo
            raw_devices = self.network_proxy.GetSupportedDevices()
            devices = [NetworkDeviceInfo.from_structure(d).device_name for d in raw_devices]
        except Exception as e:
            log.error("D-Bus 获取网卡列表失败: %s", e)
            devices = [
                d for d in os.listdir("/sys/class/net")
                if d != "lo" and not d.startswith(_VIRTUAL_PREFIXES)
            ]

        self._interface_combo.remove_all()
        self._interface2_combo.remove_all()
        for dev in devices:
            self._interface_combo.append(dev, dev)
            self._interface2_combo.append(dev, dev)

    def _fill_data_disks(self):
        self._data_disk_combo.remove_all()
        self._data_disk_combo.append("auto", "自动探测")
        import glob
        for dev_path in sorted(glob.glob("/sys/block/vd*")) + sorted(glob.glob("/sys/block/sd*")):
            dev_name = os.path.basename(dev_path)
            size_path = os.path.join(dev_path, "size")
            try:
                with open(size_path) as f:
                    sectors = int(f.read().strip())
                size_gb = sectors * 512 / (1024 ** 3)
                self._data_disk_combo.append(dev_name, f"/dev/{dev_name} ({size_gb:.0f} GB)")
            except Exception:
                self._data_disk_combo.append(dev_name, f"/dev/{dev_name}")

    # ==================== Spoke 生命周期 ====================

    def refresh(self):
        self._fill_network_interfaces()
        self._fill_data_disks()

        network_mode_val = self._proxy.NetworkMode or "dhcp"
        self._network_mode_combo.set_active_id(network_mode_val)

        mode_val = self._proxy.Mode or "single"
        self._mode_combo.set_active_id(mode_val)

        if self._proxy.Interface:
            self._interface_combo.set_active_id(self._proxy.Interface)
        else:
            self._interface_combo.set_active(0)

        if self._proxy.Interface2:
            self._interface2_combo.set_active_id(self._proxy.Interface2)
        else:
            self._interface2_combo.set_active(0)

        bond_mode_val = self._proxy.BondMode or "active-backup"
        self._bond_mode_combo.set_active_id(bond_mode_val)

        self._ip_entry.set_text(self._proxy.Ip)
        self._vip_entry.set_text(self._proxy.Vip)
        self._netmask_entry.set_text(self._proxy.Netmask or "255.255.255.0")
        self._gateway_entry.set_text(self._proxy.Gateway or "")
        self._dns_entry.set_text(self._proxy.Dns or "8.8.8.8")

        role_val = self._proxy.Role or "server"
        self._role_combo.set_active_id(role_val)
        self._server_url_entry.set_text(self._proxy.ServerUrl or "")
        self._token_entry.set_text(self._proxy.Token or "")

        self._pod_cidr_entry.set_text(self._proxy.PodCidr or "10.16.0.0/16")
        self._service_cidr_entry.set_text(self._proxy.ServiceCidr or "10.96.0.0/12")
        self._join_cidr_entry.set_text(self._proxy.JoinCidr or "100.64.0.0/16")

        self._data_disk_combo.set_active_id(self._proxy.DataDisk or "auto")

        self._sync_visibility()
        self._validate_all_defaults()

    def apply(self):
        self._proxy.NetworkMode = self._network_mode_combo.get_active_id() or "dhcp"
        self._proxy.Mode = self._mode_combo.get_active_id() or "single"
        self._proxy.Interface = self._interface_combo.get_active_id() or ""
        self._proxy.Role = self._role_combo.get_active_id() or "server"

        # Bond 校验
        if self._proxy.Mode == "bond":
            dev1 = self._interface_combo.get_active_id()
            dev2 = self._interface2_combo.get_active_id()
            if dev1 == dev2:
                dialog = Gtk.MessageDialog(
                    transient_for=None,
                    flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="主备物理网卡不能选择同一设备",
                )
                dialog.format_secondary_text("已将配置模式回退为单网卡，请重新选择两块不同网卡以启用 Bond。")
                dialog.run()
                dialog.destroy()
                self._proxy.Mode = "single"
                self._proxy.Interface2 = ""
            else:
                self._proxy.Interface2 = dev2 or ""
            self._proxy.BondMode = self._bond_mode_combo.get_active_id() or "active-backup"
        else:
            self._proxy.Interface2 = ""
            self._proxy.BondMode = "active-backup"

        # 静态 IP 字段
        if self._proxy.NetworkMode == "static":
            self._proxy.Ip = self._ip_entry.get_text()
            self._proxy.Netmask = self._netmask_entry.get_text() or "255.255.255.0"
            self._proxy.Gateway = self._gateway_entry.get_text()
            self._proxy.Dns = self._dns_entry.get_text() or "8.8.8.8"
            self._proxy.Vip = self._vip_entry.get_text()
        else:
            self._proxy.Ip = ""
            self._proxy.Netmask = ""
            self._proxy.Gateway = ""
            self._proxy.Dns = ""
            self._proxy.Vip = ""

        # Agent 字段
        self._proxy.ServerUrl = self._server_url_entry.get_text() if self._proxy.Role == "agent" else ""
        self._proxy.Token = self._token_entry.get_text() if self._proxy.Role == "agent" else ""

        # CIDR
        self._proxy.PodCidr = self._pod_cidr_entry.get_text() or "10.16.0.0/16"
        self._proxy.ServiceCidr = self._service_cidr_entry.get_text() or "10.96.0.0/12"
        self._proxy.JoinCidr = self._join_cidr_entry.get_text() or "100.64.0.0/16"

        # 系统配置
        self._proxy.DataDisk = self._data_disk_combo.get_active_id() or "auto"

        self._configured = True

    @staticmethod
    def _is_automatic_mode():
        try:
            with open("/proc/cmdline", "r") as f:
                return "vdi.install.automatic=true" in f.read()
        except Exception:
            return False

    @property
    def ready(self):
        return True

    @property
    def completed(self):
        if self._is_automatic_mode():
            return True
        if not self._configured:
            return False
        if self._validation_errors:
            return False
        if self._proxy.NetworkMode == "dhcp":
            return bool(self._proxy.Interface)
        else:
            return bool(self._proxy.Interface and self._proxy.Ip)

    @property
    def mandatory(self):
        if self._is_automatic_mode():
            return False
        return True

    @property
    def status(self):
        if not self._configured:
            return "未配置，请点击进入配置"
        parts = []
        if self._proxy.NetworkMode == "dhcp":
            parts.append(f"DHCP: {self._proxy.Interface}")
        elif self._proxy.Mode == "bond":
            parts.append(f"Static Bonding[{self._proxy.BondMode}]: {self._proxy.Interface},{self._proxy.Interface2 or '未配置'}  IP: {self._proxy.Ip}")
        else:
            parts.append(f"Static: {self._proxy.Interface}  IP: {self._proxy.Ip}")
        parts.append(self._proxy.Role or "server")
        return " | ".join(parts)
