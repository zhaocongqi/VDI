## 1. D-Bus 层属性扩展

- [x] 1.1 vdi_interface.py 新增 Role/ServerUrl/Token/DataDisk/RootPassword 5 个 @property + setter + watch_property 信号绑定
- [x] 1.2 vdi.py 新增 5 个私有字段 + *_changed Signal
- [x] 1.3 vdi.py process_kickstart / setup_kickstart 读写新属性
- [x] 1.4 vdi.py install_with_tasks 传参 VdiInstallationTask

## 2. Glade 布局重构

- [x] 2.1 将 13 行平铺 GtkGrid 重构为 4 个 GtkFrame 分组（网络配置/静态 IP/集群/系统）
- [x] 2.2 每个可校验 Entry 右侧预留 GtkImage 校验图标位
- [x] 2.3 新增 role_combo / server_url_entry / token_entry（agent 时显隐）
- [x] 2.4 新增 data_disk_combo 数据盘下拉
- [x] 2.5 新增 password_entry / password_confirm_entry（密码模式）

## 3. GUI 控件绑定与校验

- [x] 3.1 新增 _is_valid_ipv4 / _is_valid_cidr / _is_valid_netmask 纯校验函数
- [x] 3.2 新增 _on_validate_entry / _on_validate_password / _on_validate_server_url handler
- [x] 3.3 _validation_errors Set 聚合错误，驱动 completed
- [x] 3.4 refresh() 加载新属性 + _fill_data_disks 填充磁盘下拉
- [x] 3.5 apply() 保存新属性 + role 联动 server_url/token 显隐
- [x] 3.6 _on_role_changed 角色切换 handler

## 4. installation.py 功能适配

- [x] 4.1 __init__ 扩展 role/server_url/token/data_disk/root_password 参数
- [x] 4.2 _write_rke2_config 按 role 分流 server/agent config.yaml
- [x] 4.3 _setup_data_disk 支持指定磁盘（auto 走原自动探测）
- [x] 4.4 新增 _set_root_password（chpasswd 兜底，空则跳过）

## 5. kickstart.py 参数扩展

- [x] 5.1 __init__ 新增 5 个参数默认值
- [x] 5.2 __str__ 序列化新参数（敏感字段仅非空时输出）
- [x] 5.3 handle_header argparse 解析新参数

## 6. 验证

- [x] 6.1 python3 ast.parse 语法检查 6 个修改文件全过
- [x] 6.2 跨层字段名一致性核对（GUI/D-Bus/installation）
- [x] 6.3 ./scripts/dev-cycle start + VNC 实测 4 Frame 渲染与联动

## 7. 实测反馈修复（第一轮 VNC 验证后）

- [x] 7.1 移除 root 密码入口（GUI + installation 兜底全删，交 Anaconda 原生 Root 密码 Spoke）
- [x] 7.2 Spoke 全面改名 VdiNetworkSpoke → VdiInstallConfigSpoke，文件 vdi_network.* → vdi_install_config.*
- [x] 7.3 去掉自建 ScrolledWindow（塌缩致界面揉在一起），回归 Box+Frame 直排
- [x] 7.4 默认值校验：refresh() 设值后手动触发 _validate_all_defaults()，默认 IP/CIDR 显示绿勾
- [x] 7.5 非法提示改红色叉（gtk-no）+ 加大图标尺寸（LARGE_TOOLBAR / icon_size 3）
- [x] 7.6 第二轮 VNC 实测：4 Frame 清晰分开、默认值绿勾、红叉明显、密码入口已移除
