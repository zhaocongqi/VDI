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
    提供网络(管理/业务/存储)/集群/系统三层配置入口，含实时输入校验。
    """

    builderObjects = [
        "vdi_scrolled_window",
        "vdi_config_box",
        "default_route_combo",
        # 管理网络
        "mgmt_enabled_check", "mgmt_config_box",
        "network_mode_combo",
        "interface_combo",
        "mgmt_bond_check", "mgmt_bond_grid",
        "interface2_label", "interface2_combo",
        "bond_mode_label", "bond_mode_combo",
        "mgmt_static_grid",
        "ip_entry", "ip_icon",
        "vip_entry", "vip_icon",
        "netmask_entry", "netmask_icon",
        "gateway_entry", "gateway_icon",
        "dns_entry", "dns_icon",
        # 业务网络
        "biz_enabled_check", "biz_config_box",
        "bond1_network_mode_combo",
        "bond1_interface_combo",
        "biz_bond_check", "biz_bond_grid",
        "bond1_interface2_combo",
        "bond1_bond_mode_combo",
        "biz_static_grid",
        "bond1_ip_entry", "bond1_netmask_entry", "bond1_gateway_entry",
        # 存储网络
        "storage_enabled_check", "storage_config_box",
        "bond2_network_mode_combo",
        "bond2_interface_combo",
        "storage_bond_check", "storage_bond_grid",
        "bond2_interface2_combo",
        "bond2_bond_mode_combo",
        "storage_static_grid",
        "bond2_ip_entry", "bond2_netmask_entry", "bond2_gateway_entry",
        # 集群配置
        "role_combo",
        "server_url_label", "server_url_entry", "server_url_icon",
        "token_label", "token_entry", "token_icon",
        "pod_cidr_entry", "pod_cidr_icon",
        "service_cidr_entry", "service_cidr_icon",
        "join_cidr_entry", "join_cidr_icon",
        # 系统配置
        "data_disk_combo",
    ]
    mainWidgetName = "vdi_scrolled_window"
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
        # 全局
        self._default_route_combo = None
        # 管理网络
        self._mgmt_enabled_check = None
        self._mgmt_config_box = None
        self._network_mode_combo = None
        self._interface_combo = None
        self._mgmt_bond_check = None
        self._mgmt_bond_grid = None
        self._interface2_label = None
        self._interface2_combo = None
        self._bond_mode_label = None
        self._bond_mode_combo = None
        self._mgmt_static_grid = None
        self._ip_entry = None
        self._vip_entry = None
        self._netmask_entry = None
        self._gateway_entry = None
        self._dns_entry = None
        self._ip_icon = None
        self._vip_icon = None
        self._netmask_icon = None
        self._gateway_icon = None
        self._dns_icon = None
        # 业务网络
        self._biz_enabled_check = None
        self._biz_config_box = None
        self._bond1_network_mode_combo = None
        self._bond1_interface_combo = None
        self._biz_bond_check = None
        self._biz_bond_grid = None
        self._bond1_interface2_combo = None
        self._bond1_bond_mode_combo = None
        self._biz_static_grid = None
        self._bond1_ip_entry = None
        self._bond1_netmask_entry = None
        self._bond1_gateway_entry = None
        # 存储网络
        self._storage_enabled_check = None
        self._storage_config_box = None
        self._bond2_network_mode_combo = None
        self._bond2_interface_combo = None
        self._storage_bond_check = None
        self._storage_bond_grid = None
        self._bond2_interface2_combo = None
        self._bond2_bond_mode_combo = None
        self._storage_static_grid = None
        self._bond2_ip_entry = None
        self._bond2_netmask_entry = None
        self._bond2_gateway_entry = None
        # 集群配置
        self._role_combo = None
        self._server_url_label = None
        self._server_url_entry = None
        self._token_label = None
        self._token_entry = None
        self._pod_cidr_entry = None
        self._service_cidr_entry = None
        self._join_cidr_entry = None
        self._server_url_icon = None
        self._token_icon = None
        self._pod_cidr_icon = None
        self._service_cidr_icon = None
        self._join_cidr_icon = None
        # 系统配置
        self._data_disk_combo = None
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
        # 全局
        self._default_route_combo = self.builder.get_object("default_route_combo")
        # 管理网络
        self._mgmt_enabled_check = self.builder.get_object("mgmt_enabled_check")
        self._mgmt_config_box = self.builder.get_object("mgmt_config_box")
        self._network_mode_combo = self.builder.get_object("network_mode_combo")
        self._interface_combo = self.builder.get_object("interface_combo")
        self._mgmt_bond_check = self.builder.get_object("mgmt_bond_check")
        self._mgmt_bond_grid = self.builder.get_object("mgmt_bond_grid")
        self._interface2_label = self.builder.get_object("interface2_label")
        self._interface2_combo = self.builder.get_object("interface2_combo")
        self._bond_mode_label = self.builder.get_object("bond_mode_label")
        self._bond_mode_combo = self.builder.get_object("bond_mode_combo")
        self._mgmt_static_grid = self.builder.get_object("mgmt_static_grid")
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
        # 业务网络
        self._biz_enabled_check = self.builder.get_object("biz_enabled_check")
        self._biz_config_box = self.builder.get_object("biz_config_box")
        self._bond1_network_mode_combo = self.builder.get_object("bond1_network_mode_combo")
        self._bond1_interface_combo = self.builder.get_object("bond1_interface_combo")
        self._biz_bond_check = self.builder.get_object("biz_bond_check")
        self._biz_bond_grid = self.builder.get_object("biz_bond_grid")
        self._bond1_interface2_combo = self.builder.get_object("bond1_interface2_combo")
        self._bond1_bond_mode_combo = self.builder.get_object("bond1_bond_mode_combo")
        self._biz_static_grid = self.builder.get_object("biz_static_grid")
        self._bond1_ip_entry = self.builder.get_object("bond1_ip_entry")
        self._bond1_netmask_entry = self.builder.get_object("bond1_netmask_entry")
        self._bond1_gateway_entry = self.builder.get_object("bond1_gateway_entry")
        # 存储网络
        self._storage_enabled_check = self.builder.get_object("storage_enabled_check")
        self._storage_config_box = self.builder.get_object("storage_config_box")
        self._bond2_network_mode_combo = self.builder.get_object("bond2_network_mode_combo")
        self._bond2_interface_combo = self.builder.get_object("bond2_interface_combo")
        self._storage_bond_check = self.builder.get_object("storage_bond_check")
        self._storage_bond_grid = self.builder.get_object("storage_bond_grid")
        self._bond2_interface2_combo = self.builder.get_object("bond2_interface2_combo")
        self._bond2_bond_mode_combo = self.builder.get_object("bond2_bond_mode_combo")
        self._storage_static_grid = self.builder.get_object("storage_static_grid")
        self._bond2_ip_entry = self.builder.get_object("bond2_ip_entry")
        self._bond2_netmask_entry = self.builder.get_object("bond2_netmask_entry")
        self._bond2_gateway_entry = self.builder.get_object("bond2_gateway_entry")
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

        # 绑定信号
        self._mgmt_enabled_check.connect("toggled", self._on_mgmt_enabled_toggled)
        self._mgmt_bond_check.connect("toggled", self._on_mgmt_bond_toggled)
        self._network_mode_combo.connect("changed", self._on_network_mode_changed)
        self._role_combo.connect("changed", self._on_role_changed)
        self._biz_enabled_check.connect("toggled", self._on_biz_enabled_toggled)
        self._biz_bond_check.connect("toggled", self._on_biz_bond_toggled)
        self._bond1_network_mode_combo.connect("changed", self._on_bond1_network_mode_changed)
        self._storage_enabled_check.connect("toggled", self._on_storage_enabled_toggled)
        self._storage_bond_check.connect("toggled", self._on_storage_bond_toggled)
        self._bond2_network_mode_combo.connect("changed", self._on_bond2_network_mode_changed)
        # 网卡选择变化时刷新互斥灰化 + 默认路由下拉框
        for combo in [self._interface_combo, self._interface2_combo,
                      self._bond1_interface_combo, self._bond1_interface2_combo,
                      self._bond2_interface_combo, self._bond2_interface2_combo]:
            combo.connect("changed", lambda *args: (self._refresh_port_sensitivity(), self._refresh_default_route_combo()))

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
        mode = self._proxy.Mode or "single"
        network_mode = self._proxy.NetworkMode or "dhcp"
        role = self._proxy.Role or "server"

        # 管理网络：始终启用（不可关闭），配置区始终可见
        mgmt_on = self._mgmt_enabled_check.get_active()
        self._mgmt_config_box.set_visible(mgmt_on)
        if mgmt_on:
            # Bond 子区域：直接读 checkbox 状态，而非 proxy Mode
            is_bond = self._mgmt_bond_check.get_active()
            self._mgmt_bond_grid.set_visible(is_bond)
            # 静态 IP 子区域
            is_static = (network_mode == "static")
            self._mgmt_static_grid.set_visible(is_static)

        # 业务网络
        biz_on = self._biz_enabled_check.get_active()
        self._biz_config_box.set_visible(biz_on)
        if biz_on:
            b1_bond = self._biz_bond_check.get_active()
            self._biz_bond_grid.set_visible(b1_bond)
            b1_static = (self._proxy.Bond1NetworkMode == "static")
            self._biz_static_grid.set_visible(b1_static)

        # 存储网络
        storage_on = self._storage_enabled_check.get_active()
        self._storage_config_box.set_visible(storage_on)
        if storage_on:
            b2_bond = self._storage_bond_check.get_active()
            self._storage_bond_grid.set_visible(b2_bond)
            b2_static = (self._proxy.Bond2NetworkMode == "static")
            self._storage_static_grid.set_visible(b2_static)

        # Agent 字段
        is_agent = (role == "agent")
        self._server_url_label.set_visible(is_agent)
        self._server_url_entry.set_visible(is_agent)
        self._server_url_icon.set_visible(is_agent)
        self._token_label.set_visible(is_agent)
        self._token_entry.set_visible(is_agent)
        self._token_icon.set_visible(is_agent)

        self._refresh_default_route_combo()

    def _on_mgmt_enabled_toggled(self, check):
        if not check.get_active():
            # 管理网络不允许关闭——强制开启
            check.set_active(True)
        self._sync_visibility()

    def _on_mgmt_bond_toggled(self, check):
        if check.get_active():
            self._proxy.Mode = "bond"
        else:
            self._proxy.Mode = "single"
            self._proxy.Interface2 = ""
        self._sync_visibility()

    def _on_network_mode_changed(self, combo):
        active_id = combo.get_active_id() or "dhcp"
        self._proxy.NetworkMode = active_id
        self._sync_visibility()

    def _on_role_changed(self, combo):
        active_id = combo.get_active_id() or "server"
        self._proxy.Role = active_id
        self._sync_visibility()

    def _on_biz_enabled_toggled(self, check):
        self._proxy.Bond1Enabled = check.get_active()
        if not check.get_active():
            self._proxy.Bond1Interface = ""
            self._proxy.Bond1Interface2 = ""
        self._sync_visibility()

    def _on_biz_bond_toggled(self, check):
        if not check.get_active():
            self._proxy.Bond1Interface2 = ""
        self._sync_visibility()

    def _on_bond1_network_mode_changed(self, combo):
        self._proxy.Bond1NetworkMode = combo.get_active_id() or "static"
        self._sync_visibility()

    def _on_storage_enabled_toggled(self, check):
        self._proxy.Bond2Enabled = check.get_active()
        if not check.get_active():
            self._proxy.Bond2Interface = ""
            self._proxy.Bond2Interface2 = ""
        self._sync_visibility()

    def _on_storage_bond_toggled(self, check):
        if not check.get_active():
            self._proxy.Bond2Interface2 = ""
        self._sync_visibility()

    def _on_bond2_network_mode_changed(self, combo):
        self._proxy.Bond2NetworkMode = combo.get_active_id() or "static"
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
        self._bond1_interface_combo.remove_all()
        self._bond1_interface2_combo.remove_all()
        self._bond2_interface_combo.remove_all()
        self._bond2_interface2_combo.remove_all()
        for dev in devices:
            for combo in [self._interface_combo, self._interface2_combo,
                          self._bond1_interface_combo, self._bond1_interface2_combo,
                          self._bond2_interface_combo, self._bond2_interface2_combo]:
                combo.append(dev, dev)

        self._refresh_port_sensitivity()

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

    def _refresh_port_sensitivity(self):
        """实时灰化已被任一 bond 选中的网卡，防止跨 bond 重复选。"""
        all_combos = [
            (self._interface_combo, "mgmt-iface1"),
            (self._interface2_combo, "mgmt-iface2"),
            (self._bond1_interface_combo, "biz-iface1"),
            (self._bond1_interface2_combo, "biz-iface2"),
            (self._bond2_interface_combo, "storage-iface1"),
            (self._bond2_interface2_combo, "storage-iface2"),
        ]
        selected = {}
        for combo, tag in all_combos:
            dev = combo.get_active_id()
            if dev:
                selected[tag] = dev

        # Gtk.ComboBoxText 无行级 sensitive，此处仅做 apply 时兜底校验
        pass

    def _refresh_default_route_combo(self):
        """刷新默认路由下拉框选项（仅包含已启用的网络接口）。"""
        combo = self._default_route_combo
        if not combo:
            return
        current = combo.get_active_id()
        combo.remove_all()
        # 管理网络始终可选
        if self._mgmt_bond_check.get_active():
            combo.append("bond0", "bond0 (管理网络)")
        else:
            # 从 combo 实际选中项读取网卡名
            iface = self._interface_combo.get_active_id() or ""
            if iface:
                combo.append(iface, f"{iface} (管理网卡)")
            else:
                combo.append("bond0", "管理网络 (待选网卡)")
        # 业务网络
        if self._biz_enabled_check.get_active():
            if self._biz_bond_check.get_active():
                combo.append("bond1", "bond1 (业务网络)")
            else:
                b1_iface = self._bond1_interface_combo.get_active_id() or ""
                if b1_iface:
                    combo.append(b1_iface, f"{b1_iface} (业务网卡)")
                else:
                    combo.append("bond1", "业务网络 (待选网卡)")
        # 存储网络
        if self._storage_enabled_check.get_active():
            if self._storage_bond_check.get_active():
                combo.append("bond2", "bond2 (存储网络)")
            else:
                b2_iface = self._bond2_interface_combo.get_active_id() or ""
                if b2_iface:
                    combo.append(b2_iface, f"{b2_iface} (存储网卡)")
                else:
                    combo.append("bond2", "存储网络 (待选网卡)")
        # 恢复选中
        model = combo.get_model()
        if len(model) == 0:
            return
        if current:
            for row in model:
                if row[0] == current:
                    combo.set_active_id(current)
                    return
        combo.set_active(0)

    # ==================== Spoke 生命周期 ====================

    def refresh(self):
        self._fill_network_interfaces()
        self._fill_data_disks()

        network_mode_val = self._proxy.NetworkMode or "dhcp"
        self._network_mode_combo.set_active_id(network_mode_val)

        # 管理网络始终启用
        self._mgmt_enabled_check.set_active(True)
        mode_val = self._proxy.Mode or "single"
        self._mgmt_bond_check.set_active(mode_val == "bond")

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

        # 业务网络状态恢复
        self._biz_enabled_check.set_active(self._proxy.Bond1Enabled)
        if self._proxy.Bond1Interface:
            self._bond1_interface_combo.set_active_id(self._proxy.Bond1Interface)
        if self._proxy.Bond1Interface2:
            self._bond1_interface2_combo.set_active_id(self._proxy.Bond1Interface2)
        self._bond1_bond_mode_combo.set_active_id(self._proxy.Bond1BondMode or "active-backup")
        self._bond1_network_mode_combo.set_active_id(self._proxy.Bond1NetworkMode or "static")
        self._bond1_ip_entry.set_text(self._proxy.Bond1Ip or "")
        self._bond1_netmask_entry.set_text(self._proxy.Bond1Netmask or "255.255.255.0")
        self._bond1_gateway_entry.set_text(self._proxy.Bond1Gateway or "")
        # 业务网络 Bond 开关：有 Interface2 或模式为 bond 则勾选
        self._biz_bond_check.set_active(bool(self._proxy.Bond1Interface2))

        # 存储网络状态恢复
        self._storage_enabled_check.set_active(self._proxy.Bond2Enabled)
        if self._proxy.Bond2Interface:
            self._bond2_interface_combo.set_active_id(self._proxy.Bond2Interface)
        if self._proxy.Bond2Interface2:
            self._bond2_interface2_combo.set_active_id(self._proxy.Bond2Interface2)
        self._bond2_bond_mode_combo.set_active_id(self._proxy.Bond2BondMode or "active-backup")
        self._bond2_network_mode_combo.set_active_id(self._proxy.Bond2NetworkMode or "static")
        self._bond2_ip_entry.set_text(self._proxy.Bond2Ip or "")
        self._bond2_netmask_entry.set_text(self._proxy.Bond2Netmask or "255.255.255.0")
        self._bond2_gateway_entry.set_text(self._proxy.Bond2Gateway or "")
        self._storage_bond_check.set_active(bool(self._proxy.Bond2Interface2))

        # 默认路由
        default_route = self._proxy.DefaultRouteIface or ""
        if default_route:
            self._default_route_combo.set_active_id(default_route)

        self._sync_visibility()
        self._validate_all_defaults()

    def apply(self):
        self._proxy.NetworkMode = self._network_mode_combo.get_active_id() or "dhcp"
        self._proxy.Interface = self._interface_combo.get_active_id() or ""
        self._proxy.Role = self._role_combo.get_active_id() or "server"

        # 管理网络 Bond
        if self._mgmt_bond_check.get_active():
            self._proxy.Mode = "bond"
        else:
            self._proxy.Mode = "single"

        # Bond0 校验
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
                dialog.format_secondary_text("已将管理网络回退为单网卡，请重新选择两块不同网卡以启用 Bond。")
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

        # 业务网络
        self._proxy.Bond1Enabled = self._biz_enabled_check.get_active()
        if self._proxy.Bond1Enabled:
            self._proxy.Bond1Interface = self._bond1_interface_combo.get_active_id() or ""
            if self._biz_bond_check.get_active():
                self._proxy.Bond1Interface2 = self._bond1_interface2_combo.get_active_id() or ""
                self._proxy.Bond1BondMode = self._bond1_bond_mode_combo.get_active_id() or "active-backup"
            else:
                self._proxy.Bond1Interface2 = ""
                self._proxy.Bond1BondMode = "active-backup"
            self._proxy.Bond1NetworkMode = self._bond1_network_mode_combo.get_active_id() or "static"
            self._proxy.Bond1Ip = self._bond1_ip_entry.get_text()
            self._proxy.Bond1Netmask = self._bond1_netmask_entry.get_text() or "255.255.255.0"
            self._proxy.Bond1Gateway = self._bond1_gateway_entry.get_text()
        else:
            self._proxy.Bond1Interface = ""
            self._proxy.Bond1Interface2 = ""

        # 存储网络
        self._proxy.Bond2Enabled = self._storage_enabled_check.get_active()
        if self._proxy.Bond2Enabled:
            self._proxy.Bond2Interface = self._bond2_interface_combo.get_active_id() or ""
            if self._storage_bond_check.get_active():
                self._proxy.Bond2Interface2 = self._bond2_interface2_combo.get_active_id() or ""
                self._proxy.Bond2BondMode = self._bond2_bond_mode_combo.get_active_id() or "active-backup"
            else:
                self._proxy.Bond2Interface2 = ""
                self._proxy.Bond2BondMode = "active-backup"
            self._proxy.Bond2NetworkMode = self._bond2_network_mode_combo.get_active_id() or "static"
            self._proxy.Bond2Ip = self._bond2_ip_entry.get_text()
            self._proxy.Bond2Netmask = self._bond2_netmask_entry.get_text() or "255.255.255.0"
            self._proxy.Bond2Gateway = self._bond2_gateway_entry.get_text()
        else:
            self._proxy.Bond2Interface = ""
            self._proxy.Bond2Interface2 = ""

        # 默认路由
        self._proxy.DefaultRouteIface = self._default_route_combo.get_active_id() or ""

        # 跨 bond 网卡互斥兜底校验
        all_ports = []
        for label, dev in [("管理主", self._proxy.Interface), ("管理备", self._proxy.Interface2),
                           ("业务主", self._proxy.Bond1Interface), ("业务备", self._proxy.Bond1Interface2),
                           ("存储主", self._proxy.Bond2Interface), ("存储备", self._proxy.Bond2Interface2)]:
            if dev:
                all_ports.append((label, dev))
        seen = {}
        for label, dev in all_ports:
            if dev in seen:
                dialog = Gtk.MessageDialog(
                    transient_for=None,
                    flags=Gtk.DialogFlags.MODAL,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text=f"网卡 {dev} 同时被 {seen[dev]} 和 {label} 选中",
                )
                dialog.format_secondary_text("同一物理网卡不能属于多个网络，请修改配置。")
                dialog.run()
                dialog.destroy()
                break
            seen[dev] = label

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
        # 管理网络必选主网卡
        if not self._proxy.Interface:
            return False
        if self._proxy.NetworkMode == "static" and not self._proxy.Ip:
            return False
        # 业务/存储网络启用但未选主网卡
        if self._proxy.Bond1Enabled and not self._proxy.Bond1Interface:
            return False
        if self._proxy.Bond2Enabled and not self._proxy.Bond2Interface:
            return False
        return True

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
            parts.append(f"管理: DHCP {self._proxy.Interface}")
        elif self._proxy.Mode == "bond":
            parts.append(f"管理: Bond[{self._proxy.BondMode}] {self._proxy.Interface},{self._proxy.Interface2 or '?'} IP:{self._proxy.Ip}")
        else:
            parts.append(f"管理: {self._proxy.Interface} IP:{self._proxy.Ip}")
        if self._proxy.Bond1Enabled:
            b1 = f"业务: {self._proxy.Bond1Interface}"
            if self._proxy.Bond1Interface2:
                b1 += f",{self._proxy.Bond1Interface2}"
            parts.append(b1)
        if self._proxy.Bond2Enabled:
            b2 = f"存储: {self._proxy.Bond2Interface}"
            if self._proxy.Bond2Interface2:
                b2 += f",{self._proxy.Bond2Interface2}"
            parts.append(b2)
        parts.append(self._proxy.Role or "server")
        return " | ".join(parts)
