"""VDI 平台 Anaconda Addon 入口。

Anaconda 36 使用 task queue 机制驱动安装流程：
- VdiService.install_with_tasks() 返回 VdiInstallationTask
- Anaconda 自动将 Task 加入 "Anaconda addon configuration" 队列执行
- 实际的安装逻辑（网络/SSH/双数据盘/sealer 集群底座）全部在 VdiInstallationTask.run() 中完成

参考 com_redhat_kdump/__init__.py（空模块）。
"""
