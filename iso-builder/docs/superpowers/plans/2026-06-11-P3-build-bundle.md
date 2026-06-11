# P3: build-bundle — manifest 提升顶层 + tar+zstd 镜像改造

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `manifest.yaml` 提升到顶层，创建 `scripts/build-bundle/` 阶段脚本，镜像格式从 OCI 改为 docker-archive + zstd。

**Architecture:** 所有离线资源下载到 `cache/bundle/`，生成 `metadata.yaml` 结构化索引。镜像通过 `skopeo copy docker-archive:` + `zstd -19` 打包。

**Tech Stack:** skopeo, zstd, yq, helm, wget, dpkg-scanpackages

**前置依赖:** P1 完成

---

### Task 3.1: 提升并更新 manifest.yaml

**Files:**
- Move: `iso-builder/offline/manifest.yaml` → `iso-builder/manifest.yaml`

- [ ] **Step 1: 复制 manifest.yaml 到顶层**

```bash
cd /home/zcq/Github/VDI/iso-builder
cp offline/manifest.yaml manifest.yaml
```

注意：暂不删除 `offline/manifest.yaml`，留到 P5 清理阶段统一删除。

- [ ] **Step 2: 提交**

```bash
git add manifest.yaml
git commit -m "refactor(iso-builder): 提升 manifest.yaml 到项目顶层作为唯一真相来源"
```

---

### Task 3.2: 创建 scripts/build-bundle/entry

**Files:**
- Create: `iso-builder/scripts/build-bundle/entry`

- [ ] **Step 1: 创建入口脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/entry << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 阶段 2: build-bundle 入口
# 下载并打包所有离线资源，产出 cache/bundle/ + metadata.yaml

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-v1.0.0}"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
CACHE_DIR="${WORKSPACE}/cache"
BUNDLE_DIR="${CACHE_DIR}/bundle"

echo "============================================"
echo "  阶段 2: build-bundle"
echo "  版本: ${VERSION}"
echo "  清单: ${MANIFEST}"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# 校验 manifest
validate_file "$MANIFEST" "manifest.yaml" || exit 1

mkdir -p "${BUNDLE_DIR}"/{images,binaries,charts,k8s-manifests,packages/deb}

# ========== 下载各类型资源 ==========
step "下载容器镜像"
source "${SCRIPT_DIR}/images.sh"

step "下载二进制工具"
source "${SCRIPT_DIR}/binaries.sh"

step "下载 Helm Charts"
source "${SCRIPT_DIR}/charts.sh"

step "下载 K8s Manifests"
source "${SCRIPT_DIR}/manifests.sh"

step "下载系统 deb 包"
source "${SCRIPT_DIR}/packages.sh"

# ========== 生成元数据 ==========
step "生成 metadata.yaml 索引"
source "${SCRIPT_DIR}/metadata.sh"

# ========== 生成校验和 ==========
step "生成 checksums.sha256"
generate_checksums "${BUNDLE_DIR}" "${BUNDLE_DIR}/checksums.sha256"

# ========== 阶段校验 ==========
validate_file "${BUNDLE_DIR}/metadata.yaml" "metadata.yaml" || exit 1

ok "阶段 2 完成: cache/bundle/"
echo "  总大小: $(du -sh "${BUNDLE_DIR}" | cut -f1)"
echo "  文件数: $(find "${BUNDLE_DIR}" -type f ! -name '.gitkeep' ! -name 'checksums.sha256' ! -name 'metadata.yaml' | wc -l)"
echo "============================================"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/entry
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-bundle/entry
git commit -m "feat(iso-builder): 创建 build-bundle 阶段入口脚本"
```

---

### Task 3.3: 创建 scripts/build-bundle/images.sh

**Files:**
- Create: `iso-builder/scripts/build-bundle/images.sh`

**变更:** 镜像格式从 `oci:dir` 改为 `docker-archive:file.tar` + `zstd -19` 压缩。

- [ ] **Step 1: 创建镜像下载脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/images.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 下载容器镜像（docker-archive + zstd 压缩）
# 使用 skopeo 从各 registry 下载，无需 Docker daemon

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"
source "${SCRIPT_DIR}/../lib/image.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
IMAGES_DIR="${WORKSPACE}/cache/bundle/images"

require_cmds skopeo zstd yq

# 从 manifest.yaml 读取所有组件的镜像列表
COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")

total_images=0
downloaded=0
failed=0

for comp in $COMPONENTS; do
    images=$(yq ".components.${comp}.images[]" "$MANIFEST" 2>/dev/null || true)
    [ -z "$images" ] && continue

    mkdir -p "${IMAGES_DIR}/${comp}"

    echo ""
    step "组件 ${comp}: $(echo "$images" | wc -l) 个镜像"

    while IFS= read -r image; do
        [ -z "$image" ] && continue
        total_images=$((total_images + 1))

        safe_name=$(image_safe_name "$image")
        zst_file="${IMAGES_DIR}/${comp}/${safe_name}.tar.zst"

        # 跳过已存在的文件
        if [ -f "$zst_file" ]; then
            info "已存在: ${image}"
            downloaded=$((downloaded + 1))
            continue
        fi

        if image_pull_and_compress "$image" "$IMAGES_DIR" "$comp"; then
            downloaded=$((downloaded + 1))
        else
            failed=$((failed + 1))
        fi
    done <<< "$images"
done

echo ""
echo "镜像下载统计:"
echo "  总计: ${total_images}"
echo "  成功: ${downloaded}"
echo "  失败: ${failed}"

if [ "$failed" -gt 0 ]; then
    warn "有 ${failed} 个镜像下载失败"
fi

ok "镜像下载完成: ${downloaded}/${total_images} 成功"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/images.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-bundle/images.sh
git commit -m "feat(iso-builder): 创建 images.sh 使用 docker-archive + zstd 格式"
```

---

### Task 3.4: 创建 scripts/build-bundle/binaries.sh

**Files:**
- Create: `iso-builder/scripts/build-bundle/binaries.sh`

- [ ] **Step 1: 创建二进制下载脚本**

直接从当前 `scripts/download-binaries` 的逻辑迁移，将路径从 `offline/binaries` 改为 `cache/bundle/binaries`：

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/binaries.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 下载二进制工具
# 从 manifest.yaml 读取二进制列表并下载到 cache/bundle/binaries/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
BINARIES_DIR="${WORKSPACE}/cache/bundle/binaries"

require_cmds wget yq

mkdir -p "$BINARIES_DIR"

# 从 manifest 读取所有组件的二进制列表
COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")

for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.binaries | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue

    step "组件 ${comp}: ${count} 个二进制"

    for i in $(seq 0 $((count - 1))); do
        name=$(yq ".components.${comp}.binaries[${i}].name" "$MANIFEST")
        url=$(yq ".components.${comp}.binaries[${i}].url" "$MANIFEST")
        version=$(yq ".components.${comp}.binaries[${i}].version" "$MANIFEST")

        dest="${BINARIES_DIR}/${name}"

        if [ -f "$dest" ]; then
            info "已存在: ${name} v${version}"
            continue
        fi

        echo -e "  ${YELLOW}[下载]${NC} ${name} v${version}"

        case "$url" in
            *.tar.gz)
                tmpfile="${BINARIES_DIR}/$(basename "$url")"
                download_with_progress "$url" "$tmpfile" "${name}"
                tar -xzf "$tmpfile" -C "$BINARIES_DIR"
                # 查找解压后的二进制
                if [ ! -f "$dest" ]; then
                    found=$(find "$BINARIES_DIR" -name "$name" -type f | head -1)
                    [ -n "$found" ] && mv "$found" "$dest"
                fi
                rm -f "$tmpfile"
                ;;
            *)
                download_with_progress "$url" "$dest" "${name}"
                ;;
        esac
        chmod +x "$dest"
    done
done

# 列出下载的二进制
echo ""
info "已下载的二进制:"
ls -lh "$BINARIES_DIR"

ok "二进制工具下载完成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/binaries.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-bundle/binaries.sh
git commit -m "feat(iso-builder): 创建 binaries.sh 二进制下载脚本"
```

---

### Task 3.5: 创建 scripts/build-bundle/charts.sh

**Files:**
- Create: `iso-builder/scripts/build-bundle/charts.sh`

- [ ] **Step 1: 从 download-charts 迁移，路径改为 cache/bundle/charts**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/charts.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 下载 Helm Chart
# - Kube-OVN: 从本地 deploy/kube-ovn/chart/ 复制
# - Longhorn: 从远程 helm repo 拉取
# - kagent: 从 OCI registry 拉取或源码构建

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
VDI_ROOT="$(cd "${WORKSPACE}/.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
CHARTS_DIR="${WORKSPACE}/cache/bundle/charts"

require_cmds helm yq

mkdir -p "$CHARTS_DIR"

# ========== Kube-OVN（本地 chart）==========
step "Kube-OVN: 复制本地 Helm chart"
KUBEOVN_SRC="${VDI_ROOT}/deploy/kube-ovn/chart"
KUBEOVN_DST="${CHARTS_DIR}/kube-ovn"

if [ -d "$KUBEOVN_SRC" ]; then
    rm -rf "$KUBEOVN_DST"
    cp -r "$KUBEOVN_SRC" "$KUBEOVN_DST"
    ok "Kube-OVN chart 已复制"
else
    info "deploy/kube-ovn/chart/ 不存在，跳过"
fi

# ========== Longhorn（远程 chart）==========
step "Longhorn: 下载远程 Helm chart"
LH_VERSION=$(yq '.components.longhorn.version' "$MANIFEST" 2>/dev/null || echo "")
LH_DST="${CHARTS_DIR}/longhorn"

if [ -n "$LH_VERSION" ]; then
    helm repo add longhorn https://charts.longhorn.io 2>/dev/null || true
    helm repo update longhorn
    helm pull "longhorn/longhorn" \
        --version "${LH_VERSION#v}" \
        --destination "$CHARTS_DIR"
    mkdir -p "$LH_DST"
    tar -xzf "${CHARTS_DIR}/longhorn-${LH_VERSION#v}.tgz" -C "$CHARTS_DIR"
    ok "Longhorn chart 已下载"
else
    info "manifest 中未定义 Longhorn 版本"
fi

# ========== kagent（远程 chart 或本地构建）==========
step "kagent: 准备 Helm chart"
KAGENT_VERSION=$(yq '.components.kagent.version' "$MANIFEST" 2>/dev/null || echo "")
KAGENT_DST="${CHARTS_DIR}/kagent"

if [ -n "$KAGENT_VERSION" ]; then
    if helm pull "oci://ghcr.io/kagent-dev/charts/kagent" \
        --version "${KAGENT_VERSION}" \
        --destination "$CHARTS_DIR" 2>/dev/null; then
        mkdir -p "$KAGENT_DST"
        tar -xzf "${CHARTS_DIR}/kagent-${KAGENT_VERSION}.tgz" -C "$CHARTS_DIR"
        ok "kagent chart 已从 OCI 拉取"
    else
        info "OCI 拉取失败，尝试从源码构建"
        KAGENT_SRC="${VDI_ROOT}/kagent/helm"
        if [ -d "$KAGENT_SRC" ]; then
            cp -r "$KAGENT_SRC" "$KAGENT_DST"
            [ -f "${KAGENT_DST}/Chart.yaml" ] && helm dependency update "$KAGENT_DST" 2>/dev/null || true
            ok "kagent chart 已从源码构建"
        else
            info "kagent 源码目录不存在"
        fi
    fi
else
    info "manifest 中未定义 kagent 版本"
fi

ok "Helm Chart 下载完成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/charts.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-bundle/charts.sh
git commit -m "feat(iso-builder): 创建 charts.sh Helm Chart 下载脚本"
```

---

### Task 3.6: 创建 scripts/build-bundle/manifests.sh

**Files:**
- Create: `iso-builder/scripts/build-bundle/manifests.sh`

- [ ] **Step 1: 从 download-manifests 迁移**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/manifests.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 下载 K8s Manifest YAML

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
MANIFESTS_DIR="${WORKSPACE}/cache/bundle/k8s-manifests"

require_cmds wget yq

mkdir -p "$MANIFESTS_DIR"

COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")

for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.manifests | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue

    step "组件 ${comp}: ${count} 个 manifest"

    for i in $(seq 0 $((count - 1))); do
        name=$(yq ".components.${comp}.manifests[${i}].name" "$MANIFEST")
        path=$(yq ".components.${comp}.manifests[${i}].path" "$MANIFEST")
        url=$(yq ".components.${comp}.manifests[${i}].url // \"\"" "$MANIFEST" 2>/dev/null || echo "")

        dest="${MANIFESTS_DIR}/$(basename "$path")"

        if [ -f "$dest" ]; then
            info "已存在: ${name}"
            continue
        fi

        if [ -n "$url" ]; then
            echo -e "  ${YELLOW}[下载]${NC} ${name}: ${url}"
            download_with_progress "$url" "$dest" "$name"
        else
            info "无 URL 定义: ${name}"
        fi
    done
done

ok "K8s Manifest 下载完成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/manifests.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-bundle/manifests.sh
git commit -m "feat(iso-builder): 创建 manifests.sh K8s Manifest 下载脚本"
```

---

### Task 3.7: 创建 scripts/build-bundle/packages.sh

**Files:**
- Create: `iso-builder/scripts/build-bundle/packages.sh`

- [ ] **Step 1: 从 download-packages 迁移**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/packages.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 下载系统 deb 包并创建本地 APT 仓库

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
DEB_DIR="${WORKSPACE}/cache/bundle/packages/deb"

require_cmds apt-get dpkg-scanpackages yq

mkdir -p "$DEB_DIR"

PACKAGES=$(yq '.packages.deb[]' "$MANIFEST" 2>/dev/null || true)
if [ -z "$PACKAGES" ]; then
    info "manifest.yaml 中无 deb 包定义"
    exit 0
fi

step "更新 APT 索引"
apt-get update -qq

for pkg in $PACKAGES; do
    info "下载: ${pkg}"
    cd "$DEB_DIR"
    apt-get download "$pkg" 2>/dev/null || {
        info "包 ${pkg} 下载失败，跳过"
        continue
    }

    # 下载依赖
    deps=$(apt-cache depends --recurse --no-recommends --no-suggests \
        --no-conflicts --no-breaks --no-replaces --no-enhances \
        "$pkg" 2>/dev/null | grep "Depends:" | cut -d: -f2 | tr -d ' ' || true)
    for dep in $deps; do
        apt-get download "$dep" 2>/dev/null || true
    done
done

# 生成仓库元数据
step "生成 APT 仓库元数据"
cd "$DEB_DIR"
dpkg-scanpackages . /dev/null 2>/dev/null | gzip -9c > Packages.gz

DEB_COUNT=$(ls "$DEB_DIR"/*.deb 2>/dev/null | wc -l)
info "已下载 ${DEB_COUNT} 个 deb 包"

ok "系统包下载完成"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/packages.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-bundle/packages.sh
git commit -m "feat(iso-builder): 创建 packages.sh deb 包下载脚本"
```

---

### Task 3.8: 创建 scripts/build-bundle/metadata.sh

**Files:**
- Create: `iso-builder/scripts/build-bundle/metadata.sh`

**职责:** 扫描 `cache/bundle/` 生成结构化的 `metadata.yaml` 索引（参考 Harvester 的 bundle metadata）。

- [ ] **Step 1: 创建 metadata 生成脚本**

```bash
cat > /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/metadata.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail

# 生成 cache/bundle/metadata.yaml 结构化索引
# 参考 Harvester 的 bundle/metadata.yaml 格式

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-v1.0.0}"

source "${SCRIPT_DIR}/../common.sh"

MANIFEST="${WORKSPACE}/manifest.yaml"
BUNDLE_DIR="${WORKSPACE}/cache/bundle"
META_FILE="${BUNDLE_DIR}/metadata.yaml"

require_cmds yq zstd

# 开始构建 metadata
cat > "$META_FILE" << HEADER
# VDI 离线资源索引
# 由 build-bundle 自动生成，请勿手动编辑
version: "${VERSION}"
created: "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
platform: amd64
HEADER

# ========== 镜像索引 ==========
echo "images:" >> "$META_FILE"

COMPONENTS=$(yq '.components | keys | .[]' "$MANIFEST")
for comp in $COMPONENTS; do
    images=$(yq ".components.${comp}.images[]" "$MANIFEST" 2>/dev/null || true)
    [ -z "$images" ] && continue

    while IFS= read -r image; do
        [ -z "$image" ] && continue
        safe_name=$(echo "$image" | sed 's|[/:]|_|g')
        zst_file="${BUNDLE_DIR}/images/${comp}/${safe_name}.tar.zst"
        rel_path="images/${comp}/${safe_name}.tar.zst"

        if [ -f "$zst_file" ]; then
            digest=$(sha256_file "$zst_file")
            # 提取 name 和 tag
            name="${image%:*}"
            tag="${image##*:}"
            cat >> "$META_FILE" << ENTRY
  - name: "${name}"
    tag: "${tag}"
    file: "${rel_path}"
    digest: "sha256:${digest}"
ENTRY
        fi
    done <<< "$images"
done

# ========== 二进制索引 ==========
echo "binaries:" >> "$META_FILE"

for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.binaries | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue

    for i in $(seq 0 $((count - 1))); do
        name=$(yq ".components.${comp}.binaries[${i}].name" "$MANIFEST")
        version=$(yq ".components.${comp}.binaries[${i}].version" "$MANIFEST")
        bin_file="${BUNDLE_DIR}/binaries/${name}"

        if [ -f "$bin_file" ]; then
            digest=$(sha256_file "$bin_file")
            cat >> "$META_FILE" << ENTRY
  - name: "${name}"
    version: "${version}"
    file: "binaries/${name}"
    digest: "sha256:${digest}"
ENTRY
        fi
    done
done

# ========== Chart 索引 ==========
echo "charts:" >> "$META_FILE"

for comp in $COMPONENTS; do
    count=$(yq ".components.${comp}.charts | length" "$MANIFEST" 2>/dev/null || echo "0")
    [ "$count" = "0" ] && continue

    for i in $(seq 0 $((count - 1))); do
        chart_name=$(yq ".components.${comp}.charts[${i}].name" "$MANIFEST")
        chart_dir="${BUNDLE_DIR}/charts/${chart_name}"

        if [ -d "$chart_dir" ] && [ -f "${chart_dir}/Chart.yaml" ]; then
            chart_version=$(yq '.version' "${chart_dir}/Chart.yaml" 2>/dev/null || echo "unknown")
            # 打包为 tgz 计算 digest
            tgz_file="${BUNDLE_DIR}/charts/${chart_name}-${chart_version}.tgz"
            if [ ! -f "$tgz_file" ]; then
                tar -czf "$tgz_file" -C "${BUNDLE_DIR}/charts" "${chart_name}"
            fi
            digest=$(sha256_file "$tgz_file")
            cat >> "$META_FILE" << ENTRY
  - name: "${chart_name}"
    version: "${chart_version}"
    file: "charts/${chart_name}-${chart_version}.tgz"
    digest: "sha256:${digest}"
ENTRY
        fi
    done
done

ok "metadata.yaml 已生成: ${META_FILE}"
SCRIPT
chmod +x /home/zcq/Github/VDI/iso-builder/scripts/build-bundle/metadata.sh
```

- [ ] **Step 2: 提交**

```bash
git add scripts/build-bundle/metadata.sh
git commit -m "feat(iso-builder): 创建 metadata.sh 生成结构化 bundle 索引"
```

---

## P3 完成标准

- [ ] `manifest.yaml` 在项目顶层
- [ ] `scripts/build-bundle/entry` 可被 Makefile 正确调用
- [ ] 镜像下载为 `docker-archive` + `.tar.zst` 格式
- [ ] `cache/bundle/metadata.yaml` 包含所有镜像/二进制/chart 的索引
- [ ] `cache/bundle/checksums.sha256` 校验和文件正确生成
- [ ] `make build-bundle` 可完整执行
