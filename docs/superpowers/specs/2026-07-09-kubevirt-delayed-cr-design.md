# KubeVirt/CDI 延迟 CR 应用设计

## Context

RKE2 的 deploy controller 同时处理 manifests 目录下的所有 YAML 文件。当前 `kubevirt-operator.yaml`（含 CRD）和 `kubevirt-cr.yaml`（含 KubeVirt CR）是两个独立文件，deploy controller 可能在 CRD 尚未注册时处理 CR，导致 `the server could not find the requested resource` 错误。KubeVirt/CDI 使用 Operator 模式，正确流程是 operator 先运行、CRD 就绪后再创建 CR。

同时，QEMU 测试环境 4G/2vCPU 不足以运行 Kube-OVN controller + KubeVirt/CDI operator，导致 OutOfCPU。

## 方案：CR 延迟应用 + QEMU 资源调整

### 1. KubeVirt/CDI CR 延迟应用

**operator.yaml** → 正常复制到 RKE2 manifests 目录，由 deploy controller 自动处理。
**cr.yaml** → 存储到 `$sysroot/etc/vdi/cr/`，由 systemd oneshot 服务延迟 apply。

**新增 `_create_cr_apply_service()` 方法**：

脚本 `/usr/local/bin/vdi-apply-cr.sh`：
```bash
#!/bin/bash
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export PATH="$PATH:/var/lib/rancher/rke2/bin"

# 等待 API server 就绪
until kubectl get nodes 2>/dev/null; do sleep 5; done

# 等待 KubeVirt CRD Established
kubectl wait --for=condition=Established crd/kubevirts.kubevirt.io --timeout=300s 2>/dev/null || true

# 等待 CDI CRD Established
kubectl wait --for=condition=Established crd/cdis.cdi.kubevirt.io --timeout=300s 2>/dev/null || true

# Apply CR
for f in /etc/vdi/cr/*.yaml; do
  [ -f "$f" ] || continue
  kubectl apply -f "$f" 2>/dev/null || true
done
```

Systemd unit `vdi-apply-cr.service`：
```ini
[Unit]
Description=Apply KubeVirt/CDI CR after CRD ready
After=rke2-server.service
Requires=rke2-server.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/vdi-apply-cr.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

### 2. 修改 `_copy_kubevirt_manifests()` 和 `_copy_cdi_manifests()`

- `kubevirt-operator.yaml` → `$sysroot/var/lib/rancher/rke2/server/manifests/`
- `kubevirt-cr.yaml` → `$sysroot/etc/vdi/cr/`
- `cdi-operator.yaml` → `$sysroot/var/lib/rancher/rke2/server/manifests/`
- `cdi-cr.yaml` → `$sysroot/etc/vdi/cr/`

### 3. `_enable_systemd_services()` 增加 wants 链接

```python
cr_link = os.path.join(wants_dir, "vdi-apply-cr.service")
if not os.path.exists(cr_link):
    os.symlink("/etc/systemd/system/vdi-apply-cr.service", cr_link)
```

### 4. QEMU 资源调整

`scripts/qemu-test-ks`：
- `QEMU_MEM`: 4096 → 8192
- `QEMU_SMP`: 2 → 4

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `service/installation.py` | `_copy_kubevirt_manifests()`/`_copy_cdi_manifests()` CR 分流到 `/etc/vdi/cr/`；新增 `_create_cr_apply_service()`；`_enable_systemd_services()` 增加 wants 链接；`run()` 增加 step |
| `scripts/qemu-test-ks` | QEMU_MEM 8192, QEMU_SMP 4 |

## 验证

1. 重建 ISO + 自动装机
2. SSH 检查：
   - `kubectl get crd kubevirts.kubevirt.io` — CRD 已注册
   - `kubectl get kubevirt -n kubevirt` — CR 已创建
   - `kubectl get pods -n kubevirt` — virt-operator Running
   - `kubectl get cdi cdi -n cdi` — CDI CR 已创建
   - `kubectl get pods -n cdi` — cdi-operator Running
   - `kubectl get pods -A | grep kube-ovn-controller` — Running（资源充足）
