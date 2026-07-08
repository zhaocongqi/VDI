# KubeVirt + CDI 集成设计

## Context

VDI ISO 已集成 Kube-OVN CNI，节点网络就绪。下一步需集成 KubeVirt（虚拟机运行时）和 CDI（容器化数据导入器），使集群具备创建和管理虚拟机的能力。

KubeVirt 版本 `v1.5.0` 已在 `scripts/version-kubevirt` 定义，CDI 版本 `v1.65.0` 需新增。两者独立发版，版本号不一致。

当前无 GUI 可配置参数需求，采用动态 manifest 生成（与 Kube-OVN 一致），为未来扩展预留空间。

## 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 部署方式 | HelmChart CRD | 与 Kube-OVN 一致，RKE2 helm-controller 自动部署 |
| manifest 生成 | 动态生成（VdiInstallationTask） | 与 Kube-OVN 模式统一，未来加参数时改动小 |
| GUI 参数 | 暂不需要 | KubeVirt/CDI 配置项对装机用户无需自定义 |
| CDI 版本管理 | 独立 `scripts/version-cdi` | CDI 与 KubeVirt 独立发版，版本号不同 |

## 改动清单

### 1. 新增 CDI 版本脚本（`scripts/version-cdi`）

```bash
#!/bin/bash
CDI_VERSION="v1.65.0"
```

### 2. 离线资源下载（`scripts/build-bundle`）

新增：
- `source scripts/version-kubevirt` + `source scripts/version-cdi`
- KubeVirt 镜像列表（tag 用 `KUBEVIRT_VERSION`）：
  - `kubevirt/virt-operator`
  - `kubevirt/virt-controller`
  - `kubevirt/virt-handler`
  - `kubevirt/virt-api`
  - `kubevirt/virt-launcher`
- CDI 镜像列表（tag 用 `CDI_VERSION`）：
  - `kubevirt/cdi-operator`
  - `kubevirt/cdi-controller`
  - `kubevirt/cdi-importer`
  - `kubevirt/cdi-cloner`
  - `kubevirt/cdi-uploadproxy`
  - `kubevirt/cdi-apiserver`
- KubeVirt Helm chart tgz 下载到 `charts/`
- CDI Helm chart tgz 下载到 `charts/`

### 3. 安装任务（`service/installation.py`）

新增两个方法：

**`_write_kubevirt_manifest()`**：写入 `$sysroot/var/lib/rancher/rke2/server/manifests/kubevirt.yaml`

```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: kubevirt
  namespace: kube-system
spec:
  chart: kubevirt
  version: v1.5.0
  targetNamespace: kubevirt
  valuesContent: |
    infra:
      replicas: 1
    workload:
      image:
        repository: kubevirt/virt-launcher
        tag: v1.5.0
    image:
      repository: kubevirt/virt-operator
      tag: v1.5.0
```

**`_write_cdi_manifest()`**：写入 `$sysroot/var/lib/rancher/rke2/server/manifests/cdi.yaml`

```yaml
apiVersion: helm.cattle.io/v1
kind: HelmChart
metadata:
  name: cdi
  namespace: kube-system
spec:
  chart: cdi
  version: v1.65.0
  targetNamespace: cdi
  valuesContent: |
    image:
      repository: kubevirt/cdi-operator
      tag: v1.65.0
```

版本号获取策略：与 Kube-OVN 一致，方法内 import version 脚本，失败时回退硬编码值。

**`run()` 调用顺序：**

```
_write_network_config → _configure_ssh → _setup_data_disk →
_extract_bundle_resources → _write_rke2_config → _write_kube_ovn_manifest →
_write_kubevirt_manifest → _write_cdi_manifest →
_setup_kubectl_convenience → _enable_systemd_services
```

## 不改的文件

- `gui/spokes/vdi_network.glade` + `vdi_network.py`：无 GUI 参数
- `service/vdi_interface.py` + `service/vdi.py`：无新 D-Bus 属性
- `service/kickstart.py`：无新 kickstart 参数
- `_extract_bundle_resources()`：已有通用拷贝逻辑，自动复制 charts/manifests
- RKE2 `config.yaml`：`cni: none` 不变
- `ks.cfg` / `ks-auto.cfg`：无需改模板

## 改动文件总览

| 文件 | 改动类型 |
|------|----------|
| `scripts/version-cdi` | 新增 |
| `scripts/build-bundle` | 修改 |
| `service/installation.py` | 修改 |

## 验证

1. `make build-bundle` — KubeVirt/CDI 镜像 + chart 下载成功
2. `make package-vdi-iso` — ISO 构建含 KubeVirt/CDI 资源
3. 装机后 SSH 验证：
   ```bash
   cat /var/lib/rancher/rke2/server/manifests/kubevirt.yaml
   cat /var/lib/rancher/rke2/server/manifests/cdi.yaml
   kubectl get helmchart -n kube-system
   kubectl get pods -n kubevirt
   kubectl get pods -n cdi
   ```
