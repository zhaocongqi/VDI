# Kube-OVN 集成设计

## Context

当前 VDI ISO 已支持 RKE2 安装，但 `config.yaml` 中 `cni: none` 导致节点 NotReady。需要集成 Kube-OVN 作为 CNI 插件，使集群网络就绪。

Kube-OVN 版本 `v1.16.2` 已在 `scripts/version-kubeovn` 定义，但离线资源下载、安装配置、HelmChart CRD manifest 均未实现。

## 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 部署方式 | HelmChart CRD | 与 Longhorn/KubeVirt/kagent 一致，RKE2 helm-controller 自动部署 |
| Underlay 模式 | 物理网卡直接作 underlay | Kube-OVN 官方推荐的生产模式，配置简单 |
| 网络参数配置 | GUI Spoke 输入 + kickstart 覆盖 | 生产装机时用户改不了 ks.cfg，必须在 GUI 可配置 |
| HelmChart CRD 生成 | VdiInstallationTask 动态生成 | underlay 接口需与 Spoke 的 interface/bond 一致 |

## 改动清单

### 1. 离线资源下载（`scripts/build-bundle`）

- `source scripts/version-kubeovn` 获取版本号
- 用 `skopeo` 拉取 Kube-OVN 核心镜像并打包为 tar.zst：
  - `kubeovn/kube-ovn:v1.16.2`
  - `kubeovn/vpc-nat-gateway:v1.16.2`
  - `kubeovn/kube-ovn-app:v1.16.2`
- 用 `curl` 下载 Kube-OVN Helm chart tgz 到 `charts/`

### 2. GUI Spoke（`gui/spokes/vdi_network.glade` + `vdi_network.py`）

在 config_grid 追加 3 行输入控件（row 10-12），始终可见：

| 控件 ID | 标签 | 默认值 |
|---------|------|--------|
| `pod_cidr_entry` | POD CIDR: | `10.16.0.0/16` |
| `service_cidr_entry` | SERVICE CIDR: | `10.96.0.0/12` |
| `join_cidr_entry` | JOIN CIDR: | `100.64.0.0/16` |

`builderObjects` + `__init__` + `initialize` + `refresh` + `apply` 对应绑定。

### 3. D-Bus 层（`service/vdi_interface.py` + `service/vdi.py`）

新增 3 个 D-Bus 属性：`PodCidr` / `ServiceCidr` / `JoinCidr`

- `vdi_interface.py`：getter/setter + `@emits_properties_changed` + `watch_property`
- `vdi.py`：`_pod_cidr`/`_service_cidr`/`_join_cidr` 状态 + property + Signal
- `process_kickstart` / `setup_kickstart` / `install_with_tasks` 传递新参数

### 4. Kickstart 数据（`service/kickstart.py`）

`VdiKickstartData` 新增字段：

- `pod_cidr = "10.16.0.0/16"`
- `service_cidr = "10.96.0.0/12"`
- `join_cidr = "100.64.0.0/16"`

`handle_header` 新增 argparse 参数：`--pod-cidr` / `--service-cidr` / `--join-cidr`

`__str__` 序列化新字段到 `%addon vdi` 行。

### 5. 安装任务（`service/installation.py`）

构造函数新增 `pod_cidr` / `service_cidr` / `join_cidr` 参数。

新增 `_write_kube_ovn_manifest()` 方法，动态生成 HelmChart CRD YAML：

- 写入位置：`$sysroot/var/lib/rancher/rke2/server/manifests/kube-ovn.yaml`
- `spec.valuesContent` 包含：
  - `POD_CIDR` / `SERVICE_CIDR` / `JOIN_CIDR`：来自 Spoke/ks
  - `NETWORK_TYPE: "geneve"`
  - `VLAN_INTERFACE`：单网卡取 `self._interface`，bond 取 `bond0`
  - `VLAN_ID: "0"`
  - `ENABLE_LB: "true"` / `ENABLE_NP: "true"`
  - `image.repository` / `image.tag`

`run()` 调用顺序：`_write_network_config` → `_configure_ssh` → `_setup_data_disk` → `_extract_bundle_resources` → `_write_rke2_config` → **`_write_kube_ovn_manifest`** → `_setup_kubectl_convenience` → `_enable_systemd_services`

## 不改的文件

- `_extract_bundle_resources()`：已通用拷贝 charts/manifests，无需改动
- RKE2 `config.yaml`：已有 `cni: none`，无需改动
- `ks.cfg` / `ks-auto.cfg`：默认值在 `VdiKickstartData` argparse 中，无需改 ks 模板

## 验证

1. `make build-bundle` — Kube-OVN 镜像 + chart 下载成功
2. `make package-vdi-iso` — ISO 构建含 Kube-OVN 资源
3. 交互装机 → VDI Spoke 中 POD/SERVICE/JOIN CIDR 输入框可见且默认值正确
4. 装机后 SSH 验证：
   ```bash
   cat /var/lib/rancher/rke2/server/manifests/kube-ovn.yaml  # HelmChart CRD
   kubectl get helmchart kube-ovn -n kube-system
   kubectl get pods -n kube-system | grep ovn
   kubectl get nodes  # 节点 Ready
   ```
