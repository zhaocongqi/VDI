# vdi-addon-gui 能力规格（变更）

## MODIFIED Requirements

### Requirement: 集群角色配置入口

GUI SHALL 提供集群角色选择，驱动安装任务按角色分流集群落地逻辑。（原：RKE2 server/agent 角色入口）

- 角色选项 SHALL 为 `first-master`（首台控制面）与 `node`（工作节点），替代原 `server`/`agent`
- 选择 `node` 时 SHALL 显示"Master 地址"（ServerUrl）与"集群密钥"（Token）输入行且必填
- 选择 `first-master` 时 SHALL 隐藏"Master 地址"，"集群密钥"必填（作为集群预共享密钥生成端）
- D-Bus 属性名（Role/ServerUrl/Token）SHALL 保持不变，仅语义与 UI 文案重定义

#### Scenario: node 角色字段显隐

- **GIVEN** 用户打开 VDI 配置 Spoke
- **WHEN** 角色选择为 node
- **THEN** "Master 地址"与"集群密钥"输入行可见，为空时 Spoke 不可标记完成

#### Scenario: first-master 角色字段显隐

- **GIVEN** 用户打开 VDI 配置 Spoke
- **WHEN** 角色选择为 first-master
- **THEN** "Master 地址"输入行隐藏，"集群密钥"可见且必填

### Requirement: 数据盘选择入口

GUI SHALL 提供双数据盘选择入口，分别指定 /apps 盘与 Longhorn 盘。（原：单数据盘选择）

- SHALL 提供两个下拉：`/apps 数据盘`与`Longhorn 数据盘`，选项均为 auto 或探测到的非系统盘设备名
- 两个下拉指定为同一设备时 SHALL 校验失败并阻止 Spoke 完成
- 均为 auto 时安装任务 SHALL 按设备名字典序分配第一块为 /apps、第二块为 /var/lib/longhorn
