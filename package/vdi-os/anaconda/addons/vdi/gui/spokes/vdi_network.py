from pyanaconda.ui.gui.spokes import NormalSpoke


class VdiNetworkSpoke(NormalSpoke):
    """VDI 管理网络图形配置子页"""
    builderObjects = ["vdi_network_box", "ip_entry", "vip_entry"]
    mainWidgetName = "vdi_network_box"
    uiFile = "vdi_network.glade"
    title = "VDI Network"

    def __init__(self, data, storage, payload):
        super().__init__(data, storage, payload)
        self.ip_entry = None
        self.vip_entry = None

    def refresh(self):
        # 刷新界面各字段数据绑定
        self.ip_entry = self.builder.get_object("ip_entry")
        self.vip_entry = self.builder.get_object("vip_entry")
        
        vdi_data = getattr(self.data.addons, "vdi", None)
        if vdi_data and self.ip_entry and self.vip_entry:
            self.ip_entry.set_text(vdi_data.ip or "192.168.10.10")
            self.vip_entry.set_text(vdi_data.vip or "192.168.10.100")

    def apply(self):
        # 从界面写回数据模型
        vdi_data = getattr(self.data.addons, "vdi", None)
        if vdi_data and self.ip_entry and self.vip_entry:
            vdi_data.ip = self.ip_entry.get_text()
            vdi_data.vip = self.vip_entry.get_text()

    def execute(self):
        # 后台提交阶段执行
        pass
