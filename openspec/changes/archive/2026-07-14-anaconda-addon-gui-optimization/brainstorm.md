<!--
Raw capture of brainstorming output.

本档原样捕捉 brainstorming skill 的产出，不强制结构。
design.md 从本档萃取并重新整理为结构化设计文件。
-->

# VDI Anaconda Addon GUI 优化 — 决策日志

## 背景

当前 `VdiNetworkSpoke`（`gui/spokes/vdi_network.py` + `.glade`）将 13 个网络/集群参数平铺在一个 `GtkGrid` 中，存在四个核心痛点：

1. **无分组无层次** — 13 字段平铺，用户一眼看不到重点，配置模式/角色/磁盘等关键决策项埋在 IP 之间。
2. **零输入校验** — IP/VIP/网关/DNS/CIDR 可输入任意内容，错误直到 `VdiInstallationTask.run()` 阶段才暴露，返工成本高。
3. **缺关键入口** — 无 RKE2 角色（server/agent）选择、无数据盘指定、无 root 密码设置，agent 模式与多盘场景只能事后手工补救。
4. **无状态反馈** — 用户不知道哪些字段已填、哪些必填，`completed` 仅看 interface 是否非空，过于粗糙。

本次优化在现有 D-Bus 三层架构（Spoke → VdiService → VdiInstallationTask）基础上，对 GUI 交互层与功能入口做全面增强，不改变整体安装链路。

---

## 决策链

### Q1：布局重构采用什么结构？

- **Flat Grid 保留** — 改动最小，但无法解决层次问题，否决。
- **Notebook 多页签** — 过重，Anaconda Spoke 单页惯例，且 Hub 进入成本高，否决。
- **GtkFrame 分组（4 组）** ✅ 采纳 — 符合 Anaconda Addon 视觉惯例（参考 com_redhat_kdump），4 个 Frame：
  1. 网络配置（mode/interface/bond）
  2. 静态 IP 配置（ip/vip/netmask/gateway/dns + 校验图标）
  3. 集群配置（role/server_url/token/pod/service/join CIDR + 校验图标）
  4. 系统配置（data_disk/root_password）

  每个 Entry 右侧预留 `GtkImage` 校验图标位（`gtk-apply` 绿 / `gtk-dialog-warning` 红）。

### Q2：实时校验如何驱动 completed？

- **方案 A：提交时统一校验** — 延迟到 apply()，用户体验差，否决。
- **方案 B：每字段 changed 信号实时校验 + `_validation_errors` Set 聚合** ✅ 采纳 —
  - `_is_valid_ipv4` / `_is_valid_cidr` / `_is_valid_netmask` 三个纯函数
  - `_on_validate_entry` / `_on_validate_password` / `_on_validate_server_url` 三个 handler
  - `completed` property 综合检查必填字段 + `_validation_errors` 为空

  **关键取舍**：DHCP 模式下静态 IP 字段免校验（仅 interface 必填），避免误报。

### Q3：新功能入口如何贯穿三层？

新增 5 个 D-Bus 属性：`role` / `server_url` / `token` / `data_disk` / `root_password`，需贯通：

| 层 | 落点 |
|---|---|
| `vdi_interface.py` | 5 个 `@property` + setter + `watch_property` 信号绑定 |
| `vdi.py` | 5 个 `_*` 私有字段 + `*_changed` Signal + `process_kickstart`/`setup_kickstart` 读写 + `install_with_tasks` 传参 |
| `kickstart.py` | `__init__` 默认值 + `__str__` 序列化 + `handle_header` argparse |
| `installation.py` | `__init__` 收参 + role 分流 config.yaml + data_disk 指定 + `_set_root_password()` |
| `vdi_network.py` + `.glade` | 新控件绑定 + refresh/apply 读写 + 校验 |

**决策**：token / root_password 敏感字段在 `__str__` 仅非空时输出，避免明文落入生成的 ks.cfg。

### Q4：role 分流如何实现？

- **决策**：`installation.py::_write_rke2_config()` 按 `self._role` 分流：
  - `server` → 写 `server` + `cluster-cidr`/`service-cidr` 等完整 config.yaml
  - `agent` → 写 `server: <server_url>` + `token: "<token>"`，由首节点准入
- **GUI 联动**：role == "agent" 时显示 Server URL + Token 行，否则隐藏；`apply()` 中 agent 模式才写这两个字段。

### Q5：数据盘选择如何兼顾自动与手动？

- **决策**：`data_disk` 默认 "auto"，`_setup_data_disk()` 中：
  - "auto" → 走原有自动探测逻辑（扫 `/sys/block`，过滤 loop/ram）
  - 具体设备名 → `os.path.basename` 取设备名，直接 mkfs.ext4 -L VDI_LH_DEFAULT
- **GUI**：`refresh()` 时调 `_fill_data_disks()` 扫 `/sys/block/` 填充下拉，默认选中 "自动探测"。

### Q6：root 密码如何设置，避开 kickstart 限制？

- **背景**：CLAUDE.md 红线记录 `rootpw --iscrypted` 偶发不生效，Addon Task 兜底。
- **决策**：`_set_root_password()` 在 `_configure_ssh()` 后执行，用 chpasswd 写入（空则跳过）。
- **GUI**：两个 `Gtk.Entry`（visibility=False 密码模式）+ 确认校验（长度≥6 且两次一致）。

---

## 设计取舍

- **不改安装链路** — `install_with_tasks` 仍返回单个 `VdiInstallationTask`，Anaconda 36 task queue 机制不变。
- **不引入新依赖** — 校验纯 Python 标准库实现（re + ipaddress 思路），无需第三方校验库。
- **Glade 重写而非增量改** — 13 行平铺 → 4 Frame 结构差异大，整文件重写比逐 widget 编辑更清晰。
- **向后兼容** — 新参数全部有默认值（role=server, data_disk=auto, 其余空），未配置时行为等同旧版。

---

## 验证策略

- Python `ast.parse` 语法检查全部修改文件
- `./scripts/dev-cycle start` + VNC 实测：
  1. 4 个分组 Frame 正确渲染
  2. DHCP/Static 切换时"静态 IP 配置" Frame 显隐
  3. 非法 IP 触发红色图标，completed 转 False
  4. Agent 角色时 Server URL/Token 行出现
  5. 数据盘下拉列出可用磁盘
  6. 密码输入/确认校验
