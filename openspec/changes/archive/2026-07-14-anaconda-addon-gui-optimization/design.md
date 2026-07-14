## Context

VDI 离线安装器的安装交互由 Anaconda Addon（Python3 + Gtk3 + D-Bus）驱动。`VdiNetworkSpoke` 在安装器 Hub 的 SYSTEM 分类下提供网卡/Bond/IP/VIP 配置 GUI，通过 `org.fedoraproject.Anaconda.Addons.Vdi` 私有总线与 `VdiService` 通信，最终由 `VdiInstallationTask.run()` 在 task queue 阶段落地。

当前 Spoke 将 13 个参数平铺在单层 GtkGrid，存在层次缺失、零实时校验、缺角色/数据盘/密码入口、无状态反馈四个痛点。D-Bus 三层架构（Spoke → Service → Task）已稳定，本次聚焦 GUI 交互层与功能入口补齐，不改整体安装链路。

约束：
- Anaconda 36 task queue 机制（`install_with_tasks()` 返回 Task，`execute()` 已废弃）
- `WindowWrapper`（继承 Gtk.Box）代理属性/信号的红线不可破坏
- 不引入新依赖，校验用标准库

## Goals / Non-Goals

**Goals:**
- 将 13 字段平铺重构为 4 个 GtkFrame 分组，突出关键决策项
- IP/VIP/网关/DNS/CIDR/密码字段实时校验，错误前置到输入阶段
- 新增 RKE2 角色（server/agent）入口，agent 时显隐 Server URL/Token
- 新增数据盘选择入口，支持自动探测与手动指定
- 新增 root 密码设置入口，兜底 kickstart rootpw 偶发失效
- 三层贯通：D-Bus 属性 / kickstart 参数 / installation 逻辑全链路对齐

**Non-Goals:**
- 不重构 `VdiInstallationTask.run()` 整体安装链路
- 不引入第三方校验/表单库
- 不改变 ISO 构建脚本与 kickstart 模板结构
- 不处理 anaconda 安装环境 SSH 不可用的已知限制

## Decisions

### D1：布局采用 4 个 GtkFrame 分组
- **选择**：网络配置 / 静态 IP 配置 / 集群配置 / 系统配置 四组，每组带标题与校验图标位
- **理由**：符合 Anaconda Addon 视觉惯例（参考 com_redhat_kdump），单页内提供层次
- **已考虑 alternative**：Notebook 多页签（过重，Spoke 单页惯例）；Flat Grid 保留（无法解决层次问题）

### D2：实时校验用 changed 信号 + _validation_errors Set 聚合
- **选择**：每 Entry 绑 `changed` 信号，handler 调纯函数校验并切换 GtkImage 图标，错误写入 `_validation_errors` Set；`completed` property 综合必填字段 + Set 为空
- **理由**：错误前置，用户输入即见反馈，避免安装阶段才返工
- **已考虑 alternative**：apply() 提交时统一校验（延迟反馈，体验差）
- **关键取舍**：DHCP 模式下静态 IP 字段免校验，仅 interface 必填，避免误报

### D3：新增 5 个 D-Bus 属性贯穿三层
- **选择**：`role`/`server_url`/`token`/`data_disk`/`root_password` 在 vdi_interface.py（property+setter+watch_property）、vdi.py（私有字段+Signal+kickstart 读写+install_with_tasks 传参）、kickstart.py（默认值+__str__+handle_header）、installation.py（收参+分流）、vdi_network.py+glade（控件绑定）五处同步
- **理由**：新功能必须 D-Bus 全链路贯通，否则 GUI 与安装逻辑脱节
- **已考虑 alternative**：仅 GUI 层硬编码（无法持久化到 kickstart，重装丢失）

### D4：role 分流 server/agent config.yaml
- **选择**：`_write_rke2_config()` 按 `self._role` 分流——server 写完整 config.yaml，agent 写 `server:` + `token:`
- **理由**：agent 节点需指向既有 server 并持有准入 token
- **已考虑 alternative**：双节点模板外部渲染（与 Anaconda 单机安装模型不符）

### D5：敏感字段 __str__ 仅非空时序列化
- **选择**：token / root_password / data_disk 在 `__str__` 仅非空时输出到 `%addon vdi` 行
- **理由**：避免明文密码/token 落入生成的 ks.cfg 造成泄露面
- **已考虑 alternative**：始终输出（泄露风险）

### D6：root 密码用 chpasswd 兜底，避开 rootpw 偶发失效
- **选择**：`_set_root_password()` 在 `_configure_ssh()` 后执行，空则跳过
- **理由**：CLAUDE.md 红线记录 `rootpw --iscrypted` 偶发不生效，Addon Task 兜底
- **已考虑 alternative**：仅依赖 kickstart rootpw（已知不稳定）

### D7：移除 root 密码入口，交 Anaconda 原生 Spoke（覆盖 D6）
- **选择**：GUI 与 installation 兜底全删 root_password，密码完全交 Anaconda 原生 Root 密码 Spoke
- **理由**：实测发现 Anaconda 自带用户/密码设置模块，VDI 重复设置无必要；D6 的兜底也一并移除，避免维护两套密码路径
- **已考虑 alternative**：保留 installation 兜底（缺输入渠道，兜底永不触发，沦为死代码）
- **影响**：vdi.py / vdi_interface.py / kickstart.py / installation.py 全链路删 root_password 属性与 _set_root_password 方法

### D8：Spoke 全面改名 VdiInstallConfig
- **选择**：类名 VdiNetworkSpoke→VdiInstallConfigSpoke，文件 vdi_network.{py,glade}→vdi_install_config.{py,glade}（git mv 保留历史），title 改"VDI 安装配置"，icon 改 preferences-system-symbolic
- **理由**：Spoke 实际承载整个 VDI 配置（网络+集群+系统），叫 Network 名不副实
- **已考虑 alternative**：仅改显示标题（类名/文件名仍 Network，遗留认知偏差）

### D9：放弃自建 ScrolledWindow，回归 Box+Frame 直排
- **选择**：去掉 glade 里的 GtkScrolledWindow/Viewport/config_inner_box 三层包装，4 个 Frame 直接作为 vdi_config_box 子项
- **理由**：自建 ScrolledWindow 在 Anaconda Spoke 窗口里尺寸协商失败，Viewport 内容塌缩导致"界面全揉在一起"；Box+Frame 直排与原版渲染机制一致，Frame 自然展开
- **已考虑 alternative**：给 ScrolledWindow 加 vexpand/min_content_height（仍塌缩，Viewport 与 Spoke 容器高度协商不可控）
- **取舍**：静态 IP 框展开时可能顶出底部内容（问题3），改用紧凑 margin/spacing 缓解，不靠滚动窗口

### D10：默认值手动触发校验
- **选择**：新增 _validate_all_defaults()，refresh() 程序化 set_text 后手动调用，使默认 IP/CIDR 显示绿勾
- **理由**：Gtk 程序化 set_text 不触发 changed 信号，默认值无校验反馈，用户误以为未校验
- **已考虑 alternative**：set_text 后 emit changed 信号（语义不清，易触发副作用）

### D11：非法提示用红色叉
- **选择**：非法改用 gtk-no（红叉）+ LARGE_TOOLBAR 尺寸；glade icon_size 1→3
- **理由**：gtk-dialog-warning 黄三角不够醒目，红叉更符合"错误"直觉
- **已考虑 alternative**：gtk-dialog-error（部分主题缺失）

## Risks / Trade-offs

- [Risk] Glade 整文件重写可能遗漏既有控件 ID → Mitigation: 保留所有原控件 ID 命名，逐个核对 initialize/refresh/apply 引用
- [Risk] 实时校验过严导致合法输入被误拦 → Mitigation: DHCP 模式静态字段免校验；校验函数容错空值
- [Risk] role=agent 但未填 server_url/token → Mitigation: agent 模式下 completed 校验 server_url 非空
- [Trade-off] 5 层同步新增属性，改动面大（6 文件 +849/−439）→ 接受理由：D-Bus 全链路贯通是功能落地的必要代价，且默认值保证向后兼容
- [Trade-off] 敏感字段不序列化则重装无法回放配置 → 接受理由：安全优先于回放便利

## Migration Plan

N/A — 本 change 不涉及部署变更。改动限于 Anaconda Addon 代码层，随 ISO 重建自然生效。回滚方式：git revert 6 文件改动，无数据/配置迁移。

验收条件：
1. `python3 -c "import ast; ast.parse(...)"` 6 文件全过
2. `./scripts/dev-cycle start` + VNC 实测 4 Frame 渲染 / DHCP-Static 显隐 / 非法 IP 红图标 / agent 行显隐 / 数据盘下拉 / 密码校验

## Open Questions

无——决策已在实现中落地，本次为事后补文档。
