<!-- 新建 capability：vdi-addon-gui -->
<!-- 仅 ADDED Requirements，定义 GUI 交互层的行为契约 -->

## ADDED Requirements

### Requirement: 分组布局结构

VdiNetworkSpoke SHALL 将配置字段组织为 4 个 GtkFrame 分组：网络配置、静态 IP 配置、集群配置、系统配置，每组带标题标签，每个可校验 Entry 右侧 SHALL 预留校验图标位。

#### Scenario: 进入 Spoke 显示 4 个分组

- **WHEN** 用户从 Hub 进入 VdiNetworkSpoke
- **THEN** 界面 SHALL 显示 4 个带标题的 GtkFrame（网络配置 / 静态 IP 配置 / 集群配置 / 系统配置），而非平铺单层 Grid

#### Scenario: DHCP 模式隐藏静态 IP 分组

- **WHEN** 网络模式为 DHCP
- **THEN** "静态 IP 配置" Frame SHALL 隐藏；切回 Static 时 SHALL 重新显示

---

### Requirement: 实时输入校验

系统 SHALL 对 IP/VIP/网关/DNS/CIDR/密码字段在用户输入时实时校验，非法输入 SHALL 显示红色警告图标，合法输入 SHALL 显示绿色确认图标。校验错误 SHALL 聚合到内部错误集合并驱动 completed 状态。

#### Scenario: 非法 IP 触发警告

- **WHEN** 用户在管理 IPv4 字段输入 "999.999.999.999"
- **THEN** 该字段右侧 SHALL 显示红色警告图标，且 completed 状态 SHALL 为 False

#### Scenario: 合法 IP 触发确认

- **WHEN** 用户在管理 IPv4 字段输入 "192.168.10.10"
- **THEN** 该字段右侧 SHALL 显示绿色确认图标

#### Scenario: DHCP 模式静态字段免校验

- **WHEN** 网络模式为 DHCP 且静态 IP 分组隐藏
- **THEN** 静态 IP 字段的校验状态 SHALL 不影响 completed，仅 interface 必填生效

#### Scenario: 密码确认不一致

- **WHEN** 用户在 root 密码与确认框输入不一致的值
- **THEN** 确认字段 SHALL 显示红色警告图标，completed 状态 SHALL 为 False

---

### Requirement: RKE2 角色配置

系统 SHALL 支持 server 与 agent 两种 RKE2 角色配置，role 属性 SHALL 通过 D-Bus 贯通 GUI、kickstart 与安装任务。agent 角色时 SHALL 显示 Server URL 与 Token 输入入口，installation SHALL 按 role 分流生成 config.yaml。

#### Scenario: 默认角色为 server

- **WHEN** 未显式配置 role
- **THEN** role SHALL 默认为 "server"，且 Server URL/Token 入口 SHALL 隐藏

#### Scenario: 切换到 agent 显示准入字段

- **WHEN** 用户将角色切换为 agent
- **THEN** Server URL 与 Token 输入行 SHALL 显示；且 Server URL 非空 SHALL 纳入 completed 校验

#### Scenario: agent 生成 server+token 配置

- **WHEN** role 为 agent 且执行安装任务
- **THEN** `_write_rke2_config` SHALL 写入 `server: <server_url>` 与 `token: "<token>"`，而非完整 server 配置

---

### Requirement: 数据盘选择

系统 SHALL 支持自动探测与手动指定两种数据盘选择方式，data_disk 属性 SHALL 通过 D-Bus 贯通。GUI SHALL 列出可用磁盘供选择，installation SHALL 优先使用指定磁盘。

#### Scenario: 默认自动探测

- **WHEN** 未显式配置 data_disk
- **THEN** data_disk SHALL 默认为 "auto"，installation SHALL 走自动探测逻辑

#### Scenario: 列出可用磁盘

- **WHEN** Spoke refresh 时扫描 /sys/block/
- **THEN** 数据盘下拉 SHALL 列出可用磁盘名，并默认选中 "自动探测"

#### Scenario: 指定磁盘直接使用

- **WHEN** data_disk 为具体设备名
- **THEN** `_setup_data_disk` SHALL 对该设备直接 mkfs.ext4 -L VDI_LH_DEFAULT

---

### Requirement: Root 密码兜底设置

系统 SHALL 提供 root 密码设置入口，root_password 属性 SHALL 通过 D-Bus 贯通。installation SHALL 在 SSH 配置后用 chpasswd 兜底设置密码，空密码 SHALL 跳过。

#### Scenario: 设置密码

- **WHEN** root_password 非空且执行安装任务
- **THEN** `_set_root_password` SHALL 通过 chpasswd 写入 root 密码

#### Scenario: 空密码跳过

- **WHEN** root_password 为空
- **THEN** `_set_root_password` SHALL 跳过，不影响安装流程

---

### Requirement: Kickstart 参数序列化

系统 SHALL 在 %addon vdi 段支持 --role/--server-url/--token/--data-disk/--root-password 参数的解析与序列化。敏感字段（token、root_password）SHALL 仅在非空时写入 kickstart 文本。

#### Scenario: 解析新参数

- **WHEN** kickstart 含 `--role agent --server-url https://x:9345 --token abc`
- **THEN** handle_header SHALL 解析出 role=agent、server_url、token 并存入数据模型

#### Scenario: 敏感字段非空才序列化

- **WHEN** token 与 root_password 为空
- **THEN** `__str__` 输出的 %addon vdi 行 SHALL 不包含 --token 与 --root-password

#### Scenario: 向后兼容默认值

- **WHEN** kickstart 未指定新参数
- **THEN** 各参数 SHALL 取默认值（role=server, server_url="", token="", data_disk=auto, root_password=""），行为等同旧版
