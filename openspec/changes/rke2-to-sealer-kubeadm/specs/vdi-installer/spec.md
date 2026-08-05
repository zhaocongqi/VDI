# vdi-installer 能力规格（新增）

本规格描述 VDI 安装器的集群生命周期能力：以 sealer/kubeadm 为底座的 master 自举、worker 自动扩容、组件栈发布与数据盘布局。

## ADDED Requirements

### Requirement: master 节点集群自举

装机角色为 first-master 的节点，系统首启后 SHALL 自动完成集群创建，无需人工介入。

- 首启时 SHALL 执行 `sealer load` 导入集群镜像，渲染单 master Clusterfile 并执行 `sealer apply`
- Clusterfile env SHALL 固定包含 `ENABLE_CLUSTER_LICENSE=false`，使 kubeadm 渲染 `disable-admission-plugins: ClusterLicense`
- Clusterfile env SHALL 包含 `CNI_TYPE=noncni`（集群镜像为 noncni 变体）
- `sealer apply` 成功后 SHALL 自动安装 Kube-OVN 作为集群首个 CNI
- sealer apply 失败 SHALL 在 journald 与 `/apps/logs/` 留下可诊断日志，且不进入 worker 监听状态

#### Scenario: 首台 master 无人值守自举

- **GIVEN** ISO 装机时 role=first-master 且已填写集群密钥
- **WHEN** 系统首次启动完成
- **THEN** `kubectl get nodes` 显示本机 Ready，Kube-OVN 组件 Running
- **AND** `kubectl logs -n kube-system kube-apiserver-*` 无 ClusterLicense 准入拦截记录

### Requirement: worker 节点自动扩容

装机角色为 node 的节点，系统首启后 SHALL 通过 vdi-join-agent 向 master 的 vdi-clusterd 上报并自动加入集群。

- agent SHALL 以约 30 秒间隔重试上报，总窗口约 10 分钟（20 次），失败 SHALL 放弃并留下可诊断日志
- agent 失败后 SHALL 支持 `systemctl start vdi-join-agent` 手动重触发
- join 成功后 SHALL 写 stamp 文件（/var/lib/vdi/joined.stamp），后续启动幂等跳过
- server SHALL 校验预共享密钥，不匹配 SHALL 返回 403
- server SHALL 串行执行 `sealer join`（单并发），join 成功后 SHALL 为节点打 `node-role.kubernetes.io/node=` label

#### Scenario: worker 正常加入

- **GIVEN** master 集群已就绪且 vdi-clusterd 监听中
- **AND** worker ISO 装机时 role=node，填写 master IP 与正确集群密钥
- **WHEN** worker 首次启动完成
- **THEN** 10 分钟内 master 上 `kubectl get nodes` 出现该 worker 且 Ready

#### Scenario: master 地址不可达

- **GIVEN** worker 装机时填写的 master IP 错误
- **WHEN** worker 首次启动完成且重试窗口耗尽
- **THEN** agent 放弃并在 journald 留下失败原因
- **AND** 修正配置后 `systemctl start vdi-join-agent` 可重新触发并成功加入

### Requirement: 组件镜像经集群内嵌 registry 分发

VDI 组件栈（KubeVirt/CDI/Longhorn/Kube-OVN/kagent）的容器镜像 SHALL 经 master 上集群内嵌 sealer-registry 统一分发。

- 装机时组件镜像 tar 包 SHALL 仅释放到 master 节点 `/opt/vdi/images/`
- 组件安装脚本 SHALL 执行 nerdctl load、tag 并推送至 sealer-registry，推送前 SHALL 检查 registry 运行状态
- 组件 manifest/chart 的 image 引用 SHALL 渲染为 sealer-registry 地址

### Requirement: 组件栈经 sealer PostGuest Plugin 发布

VDI 组件栈的安装 SHALL 由 Clusterfile 中 `action: PostGuest` 的 SHELL Plugin 触发，在 `sealer apply` 流程内闭环。

- 组件安装顺序 SHALL 为：镜像推送 → Kube-OVN → KubeVirt/CDI（operator → 等 CRD Established → CR）→ Longhorn → kagent
- 安装失败 SHALL 记录至 `/apps/logs/vdi-components.log`

### Requirement: 双数据盘布局

节点存在两块及以上非系统数据盘时，安装任务 SHALL 分别挂载 /apps 与 /var/lib/longhorn。

- 第一块数据盘（或 GUI 指定盘）SHALL 格式化为 ext4（label VDI_APPS）并挂载 `/apps`
- 第二块数据盘（或 GUI 指定盘）SHALL 格式化为 ext4（label VDI_LH_DEFAULT）并挂载 `/var/lib/longhorn`
- 仅存在单块数据盘时 SHALL 记录错误日志并跳过（EKI 要求 /apps 独立挂载，不满足时不静默降级为单盘混挂）
- GUI 指定的两块盘 SHALL 不得为同一设备

### Requirement: RKE2 资产整体移除

ISO bundle 与安装任务 SHALL 不再包含 RKE2 二进制、系统镜像与相关 systemd 单元。

- bundle SHALL 不含 `binaries/rke2.linux-*.tar.gz` 与 RKE2 `images/*.tar.zst`
- 安装任务 SHALL NOT 写入 `/etc/rancher/` 配置，SHALL NOT 创建 rke2-server/rke2-agent wants 链接
- kubeconfig 便利服务 SHALL 改为拷贝 `/etc/kubernetes/admin.conf` 至 `/root/.kube/config`
