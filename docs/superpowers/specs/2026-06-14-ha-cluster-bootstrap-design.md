# VDI 离线 ISO 多节点 HA 集群引导设计

**日期**：2026-06-14
**状态**：已确认设计，待写实现计划
**作者**：brainstorming 会话产出

## 1. 背景（为什么做这个改动）

当前 iso-builder 的 TUI 安装器支持 4 种模式，但**只覆盖单节点 Master 场景**，无法落地 3 Master HA 集群。核心矛盾：

- ISO 装机是**逐台本地**的，每台机器启动 TUI 时只知道自己的信息
- 但 K8s HA 集群需要**全局视图**：VIP、CIDR、版本、CA 证书、etcd 成员、join token
- 当前第二台及以后节点装机时，TUI 完全不知道前序节点的配置——`join_config.py` 靠用户手工填 Master IP + 手工到 Master 上 `kubeadm token create` 抄 token，且**只支持 worker join，无 control-plane join，无 CA 分发，无 etcd 扩容**
- Longhorn 数据盘：`storage_config` 只在 Master 模式有，worker join 模式完全缺这一步，per-node 磁盘拓扑无协调机制

用户目标：ISO 一体化装机落地 **3 Master HA + 多 Worker** 集群。

## 2. 目标与非目标

**目标**：
- 支持严格串行的 3 阶段部署：Bootstrap Master → Join Control-Plane（第 2/3 台 master）→ Join Worker
- 协调信息（VIP / CA / token / etcd 成员）通过 **Master 发现服务**自动传播，消除手工抄 token
- Longhorn 数据盘在所有节点模式统一可选，零集群协调
- 复用现有 curses TUI 框架、`_run_streaming` 流式执行、retry/skip 错误恢复机制

**非目标**：
- 不做滚动升级、节点替换（初期只管首次引导）
- 不做 PXE 免交互批量引导的强制依赖（PXE 降为可选加速器）
- 不做多架构（仅 amd64）
- 不做跨子网/复杂网络拓扑（假设单一二层部署网络）

## 3. 整体架构

### 3.1 Bootstrap Master = 集群真相源

第一台 Master 装机时 TUI 收集的全局参数（VIP / Pod CIDR / Service CIDR / K8s 版本 / kube-vip 网卡）成为**集群级配置**，持久化到 `/etc/vdi/env-config.sh` 并通过发现服务暴露。所有后续节点（含第二三台 Master）向它对齐，禁止手填全局参数以避免不一致。

### 3.2 严格串行 3 阶段时序（HA 固有约束）

```
阶段 A — Bootstrap Master（模式①）
  ISO启动 → TUI 填全局参数+本机IP+选盘
  → os-init → kk create cluster(单节点) → kube-vip(VIP static pod)
  → Kube-OVN / Longhorn / KubeVirt / kagent
  → 启动发现服务 http://0.0.0.0:8090
  → Complete 屏幕显示 VIP + 一次性 install-key

阶段 B — 第 2/3 台 Master（模式② Join Control-Plane）
  ISO启动 → TUI 填 Master VIP + 本机IP + 选盘 + install-key
  → curl /cluster-info (拉全局参数，自动填充，用户确认)
  → curl /cp-join?key=... (拉 control-plane token + certificate-key)
  → os-init → kubeadm join --control-plane --certificate-key=...
  → etcd 自动扩 3 副本（kubeadm 堆叠式）→ kube-vip static pod
  → enable vdi-discovery.service

阶段 C — Worker（模式③）
  ISO启动 → TUI 填 Master VIP + 本机IP + 选盘
  → curl /join-token (拉 worker token，无需 install-key)
  → os-init → kubeadm/kk join
```

### 3.3 kube-vip 是 HA 枢纽

3 台 Master 都跑 kube-vip static pod 抢 `VIP`（如 192.168.220.100），API Server 始终通过 VIP 可达，单台 Master 宕机不影响。后续节点 `curl` 也打 VIP（不是具体某台 Master IP），任意活着的 Master 响应。

## 4. 发现服务 API 与安全模型

### 4.1 组件

`deploy/discovery/server.py`：基于 Python `http.server`（复用现有 PXE 的 http 基础），systemd unit `vdi-discovery.service`，绑 `0.0.0.0:8090`。**每台 Master 都跑**（跟 kube-vip 一样作为 master 标配），通过 VIP 访问实现负载与容错。

### 4.2 API 端点

| 端点 | 敏感度 | 鉴权 | 返回 |
|------|--------|------|------|
| `GET /healthz` | 无 | 无 | 集群就绪状态 + 已加入 master 数 |
| `GET /cluster-info` | 低 | 无 | `vip` / `pod_cidr` / `svc_cidr` / `k8s_version` / `vip_interface` |
| `GET /join-token` | 中 | 无 | worker `token` + `ca_cert_hash` + join 命令（`kubeadm token create`，TTL 15min） |
| `GET /cp-join?key=<install-key>` | **高** | install-key | control-plane `token` + `certificate_key` + `ca_cert_hash` + join 命令（`kubeadm init phase upload-certs`，TTL 2h） |
| `GET /ca?key=<install-key>` | **高** | install-key | CA 证书文件流（兜底，老版本 kubeadm/异常恢复用；主流程靠 certificate-key） |

### 4.3 安全模型 — install-key 机制

- Bootstrap Master Complete 屏幕显示**一次性 install key**（随机 24 字符，存 `/etc/vdi/install.key`）
- `/cp-join` 和 `/ca`（control-plane 级权限）必须带 `?key=<install-key>`，否则 403
- `/join-token`（worker）放宽——worker 权限低，且部署网络为内网信任边界
- 所有 token 短 TTL、动态签发（每次 curl 重新 `kubeadm token create`，不预生成不缓存），用完即弃

### 4.4 实现要点

- token 签发：`subprocess` 调 `kubeadm token create` / `kubeadm init phase upload-certs`
- `/cluster-info`：读 `/etc/vdi/env-config.sh` + `kubectl get nodes -l node-role.kubernetes.io/control-plane` 动态拼 masters 列表与 etcd 端点
- 错误：任何端点失败返回 JSON `{"error": "..."}` + 合适 HTTP 码，TUI 解析后友好提示

## 5. TUI 模式重构与 Control-Plane Join

### 5.1 TUI 3 模式（取代当前 4 模式）

| 新模式 | 角色 | TUI 收集 | 全局参数来源 |
|--------|------|---------|-------------|
| **① Bootstrap Master** | 第一台，建集群 | VIP/CIDR/版本/网卡 + 本机IP + 选盘 | 用户填（成为集群真相源） |
| **② Join Control-Plane** | 第 2/3 台 master | Master VIP + 本机IP + 选盘 + install-key | `curl /cluster-info` 自动填充 |
| **③ Join Worker** | worker | Master VIP + 本机IP + 选盘 | `curl /cluster-info` 自动填充 |

原 PXE 模式（④）降级为 Bootstrap Master Complete 屏幕的可选开关（"启用 PXE 批量引导 worker"），不占主模式。原模式 1/2（Fresh/Append）合并为 ①——装机时自动探测是否已装 OS，决定是否跑 OS 安装子步骤。

### 5.2 模式②配置收集（新增 `screens/cp_join_config.py`）

1. Master VIP（validate_ip）
2. 本机 IP + hostname（复用 network_config）
3. install-key（24 字符，从 bootstrap master Complete 屏幕抄）
4. 选盘（复用 storage_config）
5. 自动 `curl http://<VIP>:8090/cluster-info` → 弹确认框显示拉到的全局参数 → 用户确认或返回

### 5.3 Control-Plane Join 执行脚本（新增 `deploy/cp-join/deploy.sh`）

**关键简化**：kubeadm 的 `--certificate-key` 机制**自动从控制平面下载所有必需证书**（ca/etcd/front-proxy/sa），无需手动分发 CA。etcd 扩容也是 kubeadm 堆叠式自动处理，无需手动 `etcdctl member add`。

```bash
#!/bin/bash
set -euo pipefail
# 1. 拉协调信息（install-key 鉴权）
CP=$(curl -sf "http://$VIP:8090/cp-join?key=$INSTALL_KEY")
TOKEN=$(echo "$CP" | jq -r .token)
CERT_KEY=$(echo "$CP" | jq -r .certificate_key)
CA_HASH=$(echo "$CP" | jq -r .ca_cert_hash)

# 2. kubeadm control-plane join（证书 + etcd 自动处理）
kubeadm join "$VIP:6443" --token "$TOKEN" \
  --discovery-token-ca-cert-hash "$CA_HASH" \
  --control-plane --certificate-key "$CERT_KEY"

# 3. kube-vip static pod（抢 VIP，成为 HA 一员）
bash /cdrom/scripts/deploy/kube-vip/deploy-kube-vip.sh

# 4. 启动发现服务 unit（新 master 对外提供发现）
systemctl enable --now vdi-discovery
```

### 5.4 模式② `DEPLOY_STEPS` 序列

`storage-config → os-init → cp-join → kube-vip → enable-discovery`

比 bootstrap 短——集群级组件（Kube-OVN/Longhorn/KubeVirt/kagent）只在 bootstrap master 部署一次。

## 6. 磁盘流程统一与 Worker Join

### 6.1 磁盘流程统一

`storage_config` 从"仅 Master"提升为**所有模式通用步骤**。关键洞察：Longhorn 磁盘是 per-node 自动发现——longhorn-manager 读每台机器的 `/var/lib/longhorn/`，无需 per-node Node CR。所以磁盘协调 = 每台本地选盘 + 格式化挂载到统一路径，**零集群协调**。

每台机器（①②③）装机都跑：`lsblk` 列盘 → 用户选 → `mkfs.ext4` + 挂载 `/var/lib/longhorn/` + 幂等 fstab。Longhorn helm install 只在 bootstrap master 做一次，所有节点 longhorn-manager 自动纳入本地挂载点。

### 6.2 Worker Join（模式③）

```bash
JOIN=$(curl -sf "http://$VIP:8090/join-token")   # 无需 install-key
TOKEN=$(echo "$JOIN" | jq -r .token)
CA_HASH=$(echo "$JOIN" | jq -r .ca_cert_hash)
kubeadm join "$VIP:6443" --token "$TOKEN" --discovery-token-ca-cert-hash "$CA_HASH"
```

`DEPLOY_STEPS`：`storage-config → os-init → worker-join`。不装 kube-vip/discovery（worker 不需要）。

## 7. 错误处理（复用现有 retry/skip + 实时日志）

| 场景 | 处理 |
|------|------|
| 发现服务不可达 | curl 超时 → "无法连接 VIP:8090，确认 Master 已就绪" → retry / 改 VIP |
| install-key 错误（403） | → "install-key 无效，到 Bootstrap Master Complete 屏幕重新获取" |
| control-plane join 失败 | ErrorScreen 显示 kubeadm 实时输出 + retry/skip（继承现有 `_execute_step_with_ui` 机制） |
| kube-vip 抢 VIP 失败 | 节点 join 成功但告警 VIP 不可用 |

token 动态签发（每次 curl 都新的），不存在过期问题。

## 8. 测试策略与限制说明

### 8.1 PTY 单元测试（CI 可跑）

- mock 发现服务（假 http.server 返回固定 JSON），验证模式②③的 curl 解析、配置自动填充、kubeadm 命令拼接
- `cp_join_config.py` / `worker_join_config.py` 的输入收集逻辑
- 复用现有 PTY 测试框架（`_execute_step_with_ui` 已验证）

### 8.2 单节点全流程（现有 VMware 回归）

模式①单台跑通（bootstrap master 单节点集群）——保证不破坏现有能力。

### 8.3 多节点 HA 验证（关键，需 3+ 台 VM）

- VM1 模式① → 记 VIP + install-key
- VM2/VM3 模式② → join control-plane → `kubectl get nodes` 验证 3 master Ready + etcd 3 副本
- VM4 模式③ → join worker
- 故障注入：杀一台 master 验证 VIP 仍可达、集群仍工作

### 8.4 限制说明

**HA 必须真机验证，PTY 只覆盖 UI/解析逻辑**。kubeadm control-plane join、etcd 扩容、kube-vip 选举这些无法在单 PTY 里真实模拟，依赖 8.3 的多 VM 手动验证。

## 9. 实现阶段建议（给 writing-plans 的输入）

设计可解耦为 3 个递进阶段，建议分阶段实现与验证：

1. **阶段一：发现服务 + Bootstrap Master 增强** — `deploy/discovery/server.py` + systemd unit + install-key 生成；bootstrap master Complete 屏幕显示 VIP/install-key；启动发现服务作为新部署步骤。可在单 VM 验证（curl 各端点）。
2. **阶段二：TUI 模式重构 + Control-Plane Join** — welcome.py 3 模式重构；`cp_join_config.py` + `deploy/cp-join/deploy.sh`；certificate-key 流程。需 3 VM 验证。
3. **阶段三：Worker Join 重构 + 磁盘统一** — worker join 走发现服务；storage_config 提升为所有模式通用步骤。需 4+ VM 验证。

## 10. 影响文件清单

**新增**：
- `deploy/discovery/server.py` — 发现服务
- `deploy/discovery/vdi-discovery.service` — systemd unit
- `tui/screens/cp_join_config.py` — 模式②配置收集
- `deploy/cp-join/deploy.sh` — control-plane join 脚本

**修改**：
- `tui/screens/welcome.py` — 4 模式 → 3 模式
- `tui/screens/join_config.py` — 重构为模式③（curl 拉 token）
- `tui/screens/storage_config.py` — 提升为所有模式通用
- `tui/screens/complete.py` — bootstrap 显示 VIP + install-key
- `tui/screens/progress.py` — `DEPLOY_STEPS` 增加模式②③序列
- `tui/installer.py` — 模式路由 + 配置收集流程
- `tui/backend/deploy.py` — 新增 `cp-join` / `worker-join` / `enable-discovery` step_id
- `tui/backend/config_generator.py` — 模式②③不生成集群级 config（拉取 bootstrap 的）
- `deploy/skills/os-init/scripts/init.sh` — 安装 vdi-discovery unit（master 模式）
- `rootfs/package-lists/tui.list.chroot` — 确认 jq（curl/jq 解析 JSON）

**ISO 打包**：
- `scripts/package-iso/entry` — 把 `deploy/discovery/` 和 `deploy/cp-join/` 一并打入 ISO
