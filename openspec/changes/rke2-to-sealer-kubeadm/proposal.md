## Why

当前 ISO 内嵌 RKE2（用户视角等同 k3s 级别的封装发行版），其 API 聚合层、存储编排与升级路径已无法满足 VDI 场景对完整 K8s 能力的需求。客户提供了基于 kubeadm 的 EKI Kubernetes 发行版（v1.34.3-eki.2606.0，sealer 部署工具链），需将安装器的集群底座整体替换。现在处理，是因为 EKI 发行版与部署方案已交付可用，且现有 RKE2 链路的 join 参数（role/server_url/token）与新架构可直接映射，迁移窗口成熟。

## What Changes

**集群底座：RKE2 → kubeadm (sealer)**
- From: RKE2 server/agent 自治首启，token 互认
- To: sealer 编排 kubeadm；首台 master 执行 `sealer apply` 单机集群，worker 由 master 上守护进程执行 `sealer join` 纳入
- Reason: RKE2 不满足 K8s 需求；EKI 发行版为客户指定底座
- Impact: **breaking**——`bundle/vdi/{binaries,images}` 中 RKE2 二进制与系统镜像整体移除，替换为集群镜像 tar + sealer 二进制

**节点角色与加入协议（新增 vdi-clusterd / vdi-join-agent）**
- From: RKE2 原生 server/agent token 机制
- To: master 首启运行 `vdi-clusterd`（HTTP 监听，类比 rke2 supervisor）；worker 首启运行 `vdi-join-agent`（oneshot，类比 rke2-agent），携带 master IP + 预共享密钥上报，server 校验后串行执行 `sealer join`
- Reason: sealer 是 SSH 中心编排，无节点自治通道；批量/异步装机需收敛端点
- Impact: non-breaking 语义复用——GUI/D-Bus/kickstart 的 `role`/`server_url`/`token` 字段保留，语义重定义（role: first-master/node；server_url: vdi-clusterd 地址；token: 预共享密钥）

**License 准入插件**
- From: （新增项，EKI 特有）
- To: Clusterfile env 固定写入 `ENABLE_CLUSTER_LICENSE=false`，kubeadm 模板据此渲染 `disable-admission-plugins: ClusterLicense`
- Reason: 商业授权流程（24h 宽限期 + max_nodes 配额）不纳入装机链路；已在镜像 kubeadm.yml.tmpl:28 实证该开关存在
- Impact: non-breaking，规避宽限期后集群只读与扩容锁死

**CNI 与组件栈发布**
- From: RKE2 helm-controller 加载 `server/{charts,manifests}`，vdi-apply-cr.service 延迟 apply CR
- To: Kube-OVN 于 master 首启 sealer apply 完成后自动安装（集群首个 CNI）；KubeVirt/CDI/Longhorn/kagent 经 sealer PostGuest SHELL Plugin 发布；组件镜像 `nerdctl load` 后推入集群内嵌 sealer-registry
- Reason: kubeadm 集群无 helm-controller/manifests 自动加载通道；EKI 集群镜像为 noncni 变体，CNI 必须后装
- Impact: breaking——`_write_kube_ovn_manifest`、`_copy_operator_cr_manifests`、`_create_cr_apply_service` 等 RKE2 专属逻辑移除/重写

**数据盘布局**
- From: 单数据盘自动探测，mkfs.ext4 挂 `/var/lib/longhorn`
- To: 双数据盘：第一块挂 `/apps`（EKI 要求：etcd 位于 /apps/data/etcd），第二块挂 `/var/lib/longhorn`
- Reason: EKI 部署文档硬性要求 /apps 独立挂载
- Impact: breaking——`_setup_data_disk()` 重写为多盘探测分流

**重试语义**
- worker 有限重试（约 10 分钟窗口）上报 master，失败放弃并留可诊断日志，管理员可 `systemctl start vdi-join-agent` 手动重触发

## Capabilities

### New Capabilities
- `vdi-installer`: VDI 安装器的集群生命周期能力——以 sealer/kubeadm 为底座的 master 自举、worker 自动扩容（vdi-clusterd/vdi-join-agent 协议）、CNI 与 VDI 组件栈发布、License 关闭、双数据盘布局

### Modified Capabilities
- `vdi-addon-gui`: 角色语义重定义（server/agent → first-master/node），Server URL/Token 字段含义切换为 vdi-clusterd 地址与预共享密钥；数据盘选择扩展为双盘指定

## Impact

- **代码**：
  - `service/installation.py`——移除 `_extract_rke2_binary`/`_write_rke2_config`/`_write_kube_ovn_manifest`/`_copy_operator_cr_manifests`/`_create_cr_apply_service`/`_create_kubeconfig_service`；新增 sealer 落地（集群镜像/sealer 二进制拷贝）、vdi-clusterd/vdi-join-agent unit 生成、Kube-OVN 与组件栈发布脚本注入、双盘 `_setup_data_disk`
  - `service/{vdi,vdi_interface,kickstart}.py`——role 枚举值与字段语义重定义，D-Bus 属性保留
  - `gui/spokes/vdi_install_config.py` + glade——角色下拉选项与字段文案调整，双数据盘选择入口
- **构建**：`scripts/build-bundle` 移除 RKE2 下载，新增集群镜像 tar（~930MB）与 sealer_amd64（47MB）注入；ISO 体积 4.2G → ~5.2G（DVD9 上限内）
- **外部输入**：新增客户制品 `/home/zcq/tmp/kubernetes_v1.34.3-eki.2606.0-noncni-amd64/`（集群镜像 tar + sealer 二进制 + Clusterfile 模板参考）
- **运行依赖**：master 节点新增 vdi-clusterd 常驻进程（HTTP 端口待设计定稿）；组件栈依赖集群内嵌 sealer-registry 可用性
- **移除能力**：RKE2 特有便利（`vdi-kubeconfig.service` 等）以 kubeadm 等价物替代（/etc/kubernetes/admin.conf）
- **不影响**：Anaconda Addon 三层架构、ISO 构建红线（xorriso/卷标/ks 时序）、网络/Bond/SSH 配置写入链路
