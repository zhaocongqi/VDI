"""VDI Addon 服务入口（参考 com_redhat_kdump/service/__main__.py）"""

# 初始化 Anaconda 模块化服务基础设施
from pyanaconda.modules.common import init
init()

# 启动 VDI 服务
from vdi.service.vdi import VdiService
service = VdiService()
service.run()
