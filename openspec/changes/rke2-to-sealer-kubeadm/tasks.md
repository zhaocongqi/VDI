## 1. 构建链路改造

- [x] 1.1 新增 `scripts/version-eki-k8s`（EKI_K8S_VERSION="v1.34.3-eki.2606.0"）与 `scripts/version-sealer`，删除 `scripts/version-rke2`
- [x] 1.2 改造 `scripts/build-bundle`：移除 RKE2 二进制/系统镜像下载；新增集群镜像 tar 与 sealer_amd64/black_white 拷贝（来源 `LOCAL_PKG_DIR` 或 `cache/downloads`，登记外部输入路径 `/home/zcq/tmp/kubernetes_v1.34.3-eki.2606.0-noncni-amd64/`）；保留 Longhorn/KubeVirt/Kube-OVN/kagent 组件镜像 skopeo 拉取与 charts/manifests 打包
- [x] 1.3 bundle 补充 helm 二进制（D4 关键取舍——若组件安装脚本确定用 helm；否则任务改为组件 manifest 纯静态化渲染）
- [x] 1.4 `scripts/package-vdi-iso` 适配新 bundle 结构（binaries/ 内容变更），验证 ISO 体积 ~5.2G 在 xorriso 重建与测试环境内存约束内

## 2. D-Bus 与 kickstart 语义重定义

- [x] 2.1 `service/kickstart.py`：role 枚举值 `server/agent` → `first-master/node`（含旧值解析兼容或直接 breaking，与 GUI 同步定稿）；token/server_url 字段文案与序列化不变
- [x] 2.2 `service/vdi.py`：role 默认值与校验逻辑更新；`install_with_tasks()` 传参对齐新 Task 签名
- [x] 2.3 `service/vdi_interface.py`：Role/ServerUrl/Token 属性 docstring 语义更新（vdi-clusterd 地址 / 预共享密钥）
- [x] 2.4 `ks.cfg`/`ks-auto.cfg`：`%addon vdi` 段参数样例更新（role=first-master / node），ks-auto 无人值守流验证

## 3. installation.py 重写（核心）

- [x] 3.1 移除 RKE2 专属方法：`_extract_rke2_binary`、`_write_rke2_config`、`_write_kube_ovn_manifest`、`_copy_operator_cr_manifests`、`_create_cr_apply_service`、`create_kubeconfig_service`（RKE2 版）
- [x] 3.2 `_setup_data_disk()` 重写：双盘探测（第一块 VDI_APPS→/apps，第二块 VDI_LH_DEFAULT→/var/lib/longhorn），GUI 指定盘优先；单盘场景 log.error 并跳过挂载
- [x] 3.3 新增 `_extract_sealer_resources()`：集群镜像 tar、sealer_amd64（→/usr/bin/sealer）、black_white（→/etc/sudoers.d/）释放到 sysroot；master 追加 `/opt/vdi/{images,charts,manifests,scripts}` 组件资产
- [x] 3.4 新增 `_write_cluster_identity()`：master 写 `/etc/vdi/cluster-token`（0600）；worker 写 `/etc/vdi/join.conf`（server_url/token，0600）；master 另写 `/etc/vdi/sealer-join.conf`（worker root 密码，0600）
- [x] 3.5 新增 `_render_clusterfile()`：模板渲染 Clusterfile（本机 IP 单 master、ENABLE_CLUSTER_LICENSE=false、CNI_TYPE=noncni、IPV4_AUTODETECTION_METHOD、LABEL/ClearSSH/MyShell Plugin、PostGuest 组件安装 Plugin）
- [x] 3.6 新增 `_create_clusterd_service()`：vdi-clusterd.service unit（ExecStartPre=bootstrap 脚本：sealer load + apply；ExecStart=clusterd HTTP 服务）
- [x] 3.7 新增 `_create_join_agent_service()`：vdi-join-agent.service oneshot unit（worker），含有限重试与 stamp 幂等逻辑
- [x] 3.8 `_enable_systemd_services()` 更新：master enable sshd/iscsid/vdi-clusterd；worker enable sshd/vdi-join-agent；移除 rke2-server/rke2-agent/vdi-apply-cr wants
- [x] 3.9 `vdi-kubeconfig.service` 重写：等待 /etc/kubernetes/admin.conf 生成后拷贝至 /root/.kube/config

## 4. vdi-clusterd 守护进程（新组件）

- [x] 4.1 实现 HTTP 服务（Python 标准库 http.server，端口 9345）：`POST /join`（token 校验 + 入队 + 202）、`GET /join/status?ip=`（pending/joining/done/failed）
- [x] 4.2 串行 join worker：队列消费执行 `sealer join --nodes <ip> --user root --passwd <密码>`，超时与失败状态机落盘 `/var/lib/vdi/join-state/<ip>`
- [x] 4.3 join 成功后 `kubectl label node <name> node-role.kubernetes.io/node=`（kubeconfig=/etc/kubernetes/admin.conf）
- [x] 4.4 部署形态：单文件 Python 脚本 `/usr/local/bin/vdi-clusterd`（随 addon bundle 释放），日志 journald

## 5. 组件栈发布脚本（PostGuest Plugin 承载）

- [x] 5.1 `/opt/vdi/scripts/install-components.sh`：nerdctl load 组件镜像 → tag → push sealer-registry（含 registry Up 检查与 nerdctl start 兜底）
- [x] 5.2 Kube-OVN 安装：镜像地址渲染为 registry 地址后 helm install / kubectl apply（CNI 首个装，验证节点 Ready）
- [x] 5.3 KubeVirt/CDI operator apply + CRD Established 等待 + CR apply（吸收原 vdi-apply-cr.service 的延迟语义）
- [x] 5.4 Longhorn + kagent 安装；全程 set -euo pipefail + 失败日志 /apps/logs/vdi-components.log

## 6. GUI 调整

- [x] 6.1 `gui/spokes/vdi_install_config.py` + glade：角色下拉改为 first-master/node；Server URL 标签改"Master 地址"；Token 标签改"集群密钥"；数据盘选择扩展为 /apps 盘 + Longhorn 盘双入口
- [x] 6.2 校验逻辑：node 角色必填 server_url/token；first-master 必填 token（作为集群密钥）；双盘指定去重（不可同盘）

## 7. 验证

- [ ] 7.1 `INTERACTIVE=1 ./scripts/qemu-test-ks <iso> uefi`：master 交互装机 → 首启后 `kubectl get node` Ready、Kube-OVN 运行、组件栈 Pod 就绪、`kubectl get ns kube-system` 无 License 只读表现
- [ ] 7.2 双 VM 端到端：VM1 master 装机完成 → VM2 worker（GUI 填 VM1 IP + 密钥）装机 → 首启后 10 分钟内 `kubectl get node` 出现 VM2 且 Ready
- [ ] 7.3 负路径：worker 填错 master IP → 10 分钟后放弃，日志可诊断，`systemctl start vdi-join-agent` 重触发成功；填错密钥 → server 拒绝（403）agent 快速失败
- [ ] 7.4 双盘验证：qemu 挂 3 盘（系统+2 数据盘），确认 /apps 与 /var/lib/longhorn 各就其位；单数据盘场景确认报错日志
- [ ] 7.5 `./scripts/qemu-test-ks <iso> uefi` 无人值守（ks-auto.cfg role=first-master）回归
