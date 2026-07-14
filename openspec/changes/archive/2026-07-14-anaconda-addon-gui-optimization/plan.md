# VDI Anaconda Addon GUI 优化 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** 将 VdiNetworkSpoke 从 13 字段平铺重构为 4 分组 Frame，补齐实时校验与 role/data_disk/root_password 三大功能入口，三层 D-Bus 全链路贯通。

**Architecture:** Anaconda Addon 三层架构（GUI Spoke → VdiService D-Bus → VdiInstallationTask）保持不变；新增 5 个 D-Bus 属性贯穿 vdi_interface/vdi/kickstart/installation/glade 五处同步；校验用 Python 标准库实现，不引入新依赖。

**Tech Stack:** Python 3 / Gtk3 + Glade / dasbus D-Bus / Anaconda 36 task queue

---

> 说明：本 plan 为事后补全，对应代码改动（6 文件 +849/−439 行）已全部落地并通过语法检查。micro-step 标记为已完成（`[x]`），唯一待办项为真机 VNC 实测。

## Task 1: D-Bus 层属性扩展

- [x] **Step 1:** `vdi_interface.py` 新增 Role/ServerUrl/Token/DataDisk/RootPassword 5 个 `@property` + `@emits_properties_changed` setter + `connect_signals` 中 `watch_property` 绑定
- [x] **Step 2:** `vdi.py` `__init__` 新增 5 个 `_*` 私有字段 + `*_changed = Signal()`
- [x] **Step 3:** `vdi.py` 新增 5 个 `@property` + setter（含 emit + log.debug）
- [x] **Step 4:** `vdi.py` `process_kickstart` / `setup_kickstart` 读写 5 个新属性
- [x] **Step 5:** `vdi.py` `install_with_tasks` 向 `VdiInstallationTask` 传递新参数
- **验证:** `ast.parse vdi_interface.py vdi.py` 通过；D-Bus 属性名与 GUI 引用一致

## Task 2: Glade 布局重构

- [x] **Step 1:** 拆 13 行 GtkGrid 为 4 个 GtkFrame（网络配置/静态 IP 配置/集群配置/系统配置），各带 GtkLabel 标题
- [x] **Step 2:** 静态 IP/集群 Entry 右侧加 GtkImage（`gtk-apply`/`gtk-dialog-warning`）
- [x] **Step 3:** 集群 Frame 加 `role_combo` + `server_url_entry` + `token_entry`（agent 时可见）
- [x] **Step 4:** 系统 Frame 加 `data_disk_combo` + `password_entry` + `password_confirm_entry`（visibility=False）
- **验证:** glade 文件 XML 合法；控件 ID 与 vdi_network.py 引用一致

## Task 3: GUI 控件绑定与校验

- [x] **Step 1:** 新增 `_is_valid_ipv4` / `_is_valid_cidr` / `_is_valid_netmask` 纯函数
- [x] **Step 2:** 新增 `_on_validate_entry` / `_on_validate_password` / `_on_validate_server_url` handler，切换图标 + 维护 `_validation_errors`
- [x] **Step 3:** `refresh()` 加载新属性 + `_fill_data_disks()` 扫 `/sys/block/` 填下拉
- [x] **Step 4:** `apply()` 保存新属性；role=agent 时写 server_url/token，否则清空
- [x] **Step 5:** `_on_role_changed` 联动 server_url/token 行显隐
- [x] **Step 6:** `completed` property 综合必填字段 + `_validation_errors` 为空
- **验证:** `ast.parse vdi_network.py` 通过

## Task 4: installation.py 功能适配

- [x] **Step 1:** `__init__` 扩展 role/server_url/token/data_disk/root_password 参数与 `self._*` 字段
- [x] **Step 2:** `_write_rke2_config` 按 `self._role` 分流 server（完整配置）/ agent（server+token）
- [x] **Step 3:** `_setup_data_disk` 支持指定磁盘，"auto" 走原自动探测
- [x] **Step 4:** 新增 `_set_root_password`（chpasswd，空则跳过），在 `_configure_ssh` 后调用
- **验证:** `ast.parse installation.py` 通过；`run()` 调用链顺序正确

## Task 5: kickstart.py 参数扩展

- [x] **Step 1:** `__init__` 新增 5 个参数默认值
- [x] **Step 2:** `__str__` 序列化（token/root_password/data_disk 仅非空时输出）
- [x] **Step 3:** `handle_header` argparse 新增 5 个 `--role`/`--server-url`/`--token`/`--data-disk`/`--root-password`
- **验证:** `ast.parse kickstart.py` 通过

## Task 6: 集成验证

- [x] **Step 1:** 6 个修改文件 `python3 -c "import ast; ast.parse(...)"` 全过
- [x] **Step 2:** 跨层字段名核对（GUI Role/ServerUrl/Token/DataDisk/RootPassword ↔ D-Bus ↔ installation 参数）
- [ ] **Step 3:** `./scripts/dev-cycle start` + VNC 实测：4 Frame 渲染 / DHCP-Static 显隐 / 非法 IP 红图标 / agent 行显隐 / 数据盘下拉 / 密码校验
- **提交点:** VNC 实测通过后，执行 `/smart-multi-commit` 按 D-Bus 层 / Glade+GUI / installation / kickstart 拆分提交
