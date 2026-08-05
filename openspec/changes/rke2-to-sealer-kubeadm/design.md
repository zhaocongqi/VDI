## Context

VDI 离线安装器当前以 RKE2 为集群底座：`VdiInstallationTask.run()` 在 Anaconda task queue 阶段释放 RKE2 二进制/镜像/charts，写 `config.yaml` 按 server/agent 角色分流，首启由 RKE2 自治完成集群组建与组件加载。

客户交付的替代底座位于 `/home/zcq/tmp/kubernetes_v1.34.3-eki.2606.0-noncni-amd64/`：
- `kubernetes_v1.34.3-eki.2606.0-noncni-amd64.tar`（~930MB）：sealer 集群镜像，内含 `bin/`（kubectl/nerdctl/sealer/ipvsadm）、`cri/`（containerd rpm+service）、`etc/kubeadm.yml.tmpl`、`manifests/`（coredns/metrics-server）、`registry/`（内嵌 OCI registry，含 cmss/* 系统组件镜像）、`charts/localdns`、`scripts/`
- `sealer_amd64`（47MB）+ `black_white`（sudoers.d 配置）
- Clusterfile 模板：sealer.cloud/v2 Cluster + sealer.cmss.com/v1 Plugin（LABEL/TAINT/HOSTNAME/SHELL）

已实证的关键事实：
- `etc/kubeadm.yml.tmpl:27-28` 存在 `{{if eq .ENABLE_CLUSTER_LICENSE "false"}}disable-admission-plugins: ClusterLicense{{end}}` 开关；License 准入插件编译在 cmss/kube-apiserver 二进制内，不可移除但可禁用
- EKI 部署要求 `/apps` 独立数据盘（etcd 位于 /apps/data/etcd），`sealer join --masters/--nodes` 为官方扩容命令
- sealer 是 SSH 中心编排器：apply/join 均由首个 master 发起，目标节点无需预置集群凭据

约束：
- Anaconda 36 task queue 机制与 WindowWrapper 红线不变
- ISO 构建红线不变（xorriso、卷标 BCLinux.x86_64、%include 时序）
- 单 master 拓扑（无 etcd 扩成员/控制面 HA 场景）
- 装机顺序：先 master 后 worker，时序有保证

## Goals / Non-Goals

**Goals:**
- ISO 装完首台 master 后自动完成 sealer apply（单机集群）+ Kube-OVN + VDI 组件栈，集群开箱可用
- 后续节点 ISO 装完后经 vdi-join-agent → vdi-clusterd 协议自动 `sealer join` 扩容
- License 准入插件关闭（ENABLE_CLUSTER_LICENSE=false）
- 复用现有 GUI/D-Bus/kickstart 字段承载新语义，交互改动最小
- 双数据盘布局（/apps + /var/lib/longhorn）

**Non-Goals:**
- 不支持多 master / 控制面 HA（sealer join --masters 保留为手动运维路径）
- 不处理 License 注入/续期流程（已关闭）
- 不支持 worker 子角色区分（计算/存储分离）
- 不改造 sealer 二进制或 EKI 集群镜像内容（不重构建 Kubefile）
- 不覆盖 arm64（sealer_arm64 已交付但本期不接线）

## Decisions

### D1：master 自举——vdi-clusterd 首启引导 sealer apply 后转常驻
- **选择**：`vdi-clusterd.service` 分两段：bootstrap 段（ExecStartPre）执行 `sealer load -i <集群镜像tar>` → 渲染 Clusterfile（本机 IP 为唯一 master，env 含 `ENABLE_CLUSTER_LICENSE=false`、`CNI_TYPE=noncni`、`IPV4_AUTODETECTION_METHOD=can-reach=<本机IP>`）→ `sealer apply -f Clusterfile`；常驻段启动 HTTP 监听（端口 9345，对齐 RKE2 supervisor 心智模型）等待 worker 上报
- **理由**：单机集群先行可用（装机顺序保证 master 先装），避免等待全部拓扑的就绪死锁；bootstrap 与常驻同一 unit 简化依赖编排
- **已考虑 alternative**：分两个 unit（bootstrap oneshot + clusterd 常驻，Requires 串联）——更清晰但多一个 unit 编排面；sealer apply 全量 Clusterfile 等待所有节点 SSH 可达（违反装机顺序约束，死锁）
- **关键取舍**：sealer apply 单机集群时 hosts 仅含本机；LABEL Plugin data 同样仅渲染本机行

### D2：worker 加入协议——HTTP 上报 + server 端串行 sealer join
- **选择**：
  - agent（worker，`vdi-join-agent.service` oneshot）：首启读取 `/etc/vdi/join.conf`（装机时由 Task 写入 server_url/token），向 `http://<master>:9345/join` POST `{ip, hostname, token}`；有限重试（间隔 30s × 20 次 ≈ 10 分钟），成功收到 202 后轮询 `GET /join/status?ip=`，终态 done/failed 写 stamp `/var/lib/vdi/joined.stamp` 后退出；失败保留日志，支持 `systemctl start vdi-join-agent` 手动重触发（stamp 存在则幂等跳过）
  - server（master，vdi-clusterd 常驻段）：校验 token（与 `/etc/vdi/cluster-token` 比对）→ 串行队列执行 `sealer join --nodes <ip> --user root --passwd <root密码>` → 完成后 `kubectl label node <name> node-role.kubernetes.io/node=`
- **理由**：sealer 无节点自治通道，必须自建收敛端点；串行队列规避并发 join 的 kubeadm 锁竞争与 registry 推送冲突
- **已考虑 alternative**：agent 自治 kubeadm join（绕开 EKI 定制流程，偏离厂商支持路径）；master 侧轮询发现新节点（无反向通道，被动等待不可行）
- **关键取舍**：sealer join 需要目标节点 root 密码——复用装机 GUI 的 root_password（master 端 `/etc/vdi/sealer-join.conf` 持有，权限 0600）；若现场允许节点密码各异，退化为手动 sealer join（文档化）

### D3：认证模型——预共享密钥单因子
- **选择**：GUI/ks 的 `token` 字段语义重定义为集群预共享密钥；master 装机写入 `/etc/vdi/cluster-token`（0600），worker 装机写入 `/etc/vdi/join.conf`；server 仅做等值比对，HTTP 明文（内网装机场景，与 RKE2 token 同级）
- **理由**：与现有字段同构，GUI 零新增控件；装机场景为隔离内网
- **已考虑 alternative**：来源 IP 网段二次校验（复用 join_cidr——但 join_cidr 是 Kube-OVN 隧道网段语义，不混用）；TLS 双向（装机阶段证书分发复杂度不值）

### D4：组件栈发布——sealer PostGuest SHELL Plugin 承载
- **选择**：装机 Task 在 master 上预置 `/opt/vdi/components/`（charts、manifests、镜像 tar 包、安装脚本），Clusterfile 追加 SHELL Plugin `action: PostGuest`，data 调用安装脚本：nerdctl load 组件镜像 → tag 推送 sealer-registry → helm/kubectl 安装 Kube-OVN（CNI 先行）→ KubeVirt/CDI operator + CR → Longhorn → kagent
- **理由**：组件安装编排与 sealer 生命周期绑定，厂商工具链内闭环
- **已考虑 alternative**：vdi-clusterd 兼管（进程职责膨胀）；独立 vdi-components.service（与 sealer 状态耦合弱，apply 失败时组件脚本仍会跑）
- **关键取舍**：helm 二进制不在集群镜像 `bin/` 内（已核实仅 kubectl/nerdctl/sealer/ipvsadm）——bundle 需补充 helm 二进制，或组件安装改写为纯 kubectl apply + 模板渲染，实施任务中定稿
- **风险**：sealer Plugin 语法（sealer.cmss.com/v1）为厂商定制 fork，升级 sealer 版本时需回归验证

### D5：镜像分发——组件镜像推入集群内嵌 sealer-registry
- **选择**：build-bundle 继续 skopeo 拉取 Longhorn/KubeVirt/Kube-OVN/kagent 组件镜像打 tar；master 装机拷贝至 `/opt/vdi/images/`；PostGuest 脚本 `nerdctl load` + tag + push 至 `localhost:<sealer-registry端口>`；各组件 manifest 的 image 字段渲染为 registry 地址
- **理由**：registry 已随集群存在，kubelet 拉取路径与系统组件统一；组件镜像与 930MB 集群镜像解耦，独立升级
- **已考虑 alternative**：重构建集群镜像内嵌（升级耦合，否定）；各节点本地 load + IfNotPresent（漏装节点 ImagePullBackOff 排查绕弯，否定）

### D6：数据盘——双盘探测分流
- **选择**：`_setup_data_disk()` 重写：探测非系统盘，第一块（按设备名字典序）mkfs.ext4 `-L VDI_APPS` 挂 `/apps`，第二块 `-L VDI_LH_DEFAULT` 挂 `/var/lib/longhorn`；GUI 数据盘选择扩展为两个下拉（/apps 盘、Longhorn 盘，均可 auto/指定）；单盘场景报错提示（EKI /apps 为硬要求）
- **理由**：EKI 文档硬性要求 /apps 独立挂载；Longhorn 与 etcd IO 隔离
- **已考虑 alternative**：单盘分区拆分（装机 partition 阶段已过，Task 阶段改分区表风险高）

### D7：RKE2 资产清理——整体移除不保留
- **选择**：bundle 移除 `binaries/rke2.linux-*.tar.gz` 与 `images/*.tar.zst`；installation.py 移除 RKE2 相关五个方法；`vdi-kubeconfig.service` 重写为 kubeadm 等价（拷贝 /etc/kubernetes/admin.conf → /root/.kube/config）
- **理由**：双底座并存增加 ISO 体积与维护面，无共存场景
- **关键取舍**：`scripts/version-rke2` 删除，新增 `scripts/version-eki-k8s`（集群镜像版本 v1.34.3-eki.2606.0）与 `scripts/version-sealer`

## 架构视图

```
装机阶段 (Anaconda task queue, VdiInstallationTask.run)
┌────────────────────────────────────────────────────────┐
│ master (role=first-master)      worker (role=node)     │
│  · 网络/Bond/SSH（复用不变）      · 网络/Bond/SSH（复用） │
│  · 双盘挂载 /apps + longhorn    · 双盘挂载              │
│  · 释放 sealer + 集群镜像tar     · 写 /etc/vdi/join.conf│
│  · 写 /etc/vdi/cluster-token      (server_url/token)   │
│  · 预置 /opt/vdi/components/*   ·  enable              │
│  · enable vdi-clusterd.service    vdi-join-agent.svc   │
└────────────────────────────────────────────────────────┘

首启阶段
┌────────────────────────────────────────────────────────┐
│ master: vdi-clusterd              worker: vdi-join-agent│
│  ① sealer load + apply (单机)  ◄──┐ ① POST /join 重试   │
│  ② PostGuest Plugin:            │   (30s×20, ~10min)    │
│     镜像 load+push registry     │ ② 轮询 /join/status   │
│     Kube-OVN → VDI 组件栈       │ ③ done → stamp 退出   │
│  ③ HTTP :9345 常驻监听 ─────────┘                       │
│  ④ 串行 sealer join --nodes <worker ip>                 │
│  ⑤ kubectl label node-role.kubernetes.io/node=         │
└────────────────────────────────────────────────────────┘
```
