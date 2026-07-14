## Why

VdiNetworkSpoke 将 13 个参数平铺在单层 GtkGrid，无分组无层次；IP/VIP/CIDR 零实时校验，错误延迟到安装阶段才暴露；缺少 RKE2 角色、数据盘选择、root 密码三个关键入口，agent 模式与多盘场景只能事后手工补救。现在处理，是因为这些缺陷直接影响现场装机一次成功率与可回溯性，且 D-Bus 三层架构已稳定，是补齐 GUI 交互与功能入口的合适时机。

## What Changes

**布局结构**
- From: 13 字段平铺单 GtkGrid
- To: 4 个 GtkFrame 分组（网络配置 / 静态 IP 配置 / 集群配置 / 系统配置），每组带标题与校验图标位
- Reason: 消除层次缺失，突出关键决策项
- Impact: non-breaking，Glade 整文件重写

**输入校验**
- From: 零校验，错误延迟到 VdiInstallationTask.run() 暴露
- To: 每字段 changed 信号实时校验（IPv4/CIDR/Netmask/密码），`_validation_errors` Set 聚合驱动 completed
- Reason: 安装阶段才报错返工成本高
- Impact: non-breaking，DHCP 模式下静态字段免校验

**RKE2 角色入口**
- From: 仅隐式 server 模式，无 agent 选择
- To: 新增 role（server/agent）D-Bus 属性，GUI 角色下拉 + agent 时显隐 Server URL/Token 行，installation 按 role 分流 config.yaml
- Reason: 支持 agent 节点加入既有集群
- Impact: non-breaking，默认 server

**数据盘选择**
- From: 仅自动探测
- To: 新增 data_disk 属性（auto/设备名），GUI 下拉列出可用盘，installation 优先用指定盘
- Reason: 多盘场景需手动指定
- Impact: non-breaking，默认 auto

**Root 密码**
- From: 依赖 kickstart rootpw（偶发不生效）
- To: 新增 root_password 属性，GUI 密码+确认双框，installation 用 chpasswd 兜底设置
- Reason: CLAUDE.md 红线记录 rootpw --iscrypted 偶发不生效
- Impact: non-breaking，空则跳过

## Capabilities

### New Capabilities
- `vdi-addon-gui`: VDI Anaconda Addon 的 GUI 交互层——分组布局、实时校验、角色/数据盘/密码功能入口及三层贯通

### Modified Capabilities
<!-- openspec/specs/ 当前为空，无既有 capability 的需求在变 -->

## Impact

- **代码**：6 个文件——`gui/spokes/vdi_network.{py,glade}`、`service/{vdi,vdi_interface,kickstart,installation}.py`
- **D-Bus**：新增 5 个属性（Role/ServerUrl/Token/DataDisk/RootPassword）到 `org.fedoraproject.Anaconda.Addons.Vdi`
- **kickstart**：`%addon vdi` 段新增 `--role/--server-url/--token/--data-disk/--root-password` 参数，敏感字段仅非空时序列化
- **安装链路**：`VdiInstallationTask.__init__` 扩参，新增 `_set_root_password()`，`_write_rke2_config`/`_setup_data_disk` 分流
- **依赖**：无新增，校验用 Python 标准库
- **系统**：不影响 RKE2/HelmChart CRD 部署链路
