# 离线安装包本地缓存与无代理下载设计说明书

## 1. 背景与需求
在构建自研云桌面（VDI）系统的离线包及相关组件时，常常需要从外部网络下载大量的第三方安装包（例如 RKE2 运行镜像、Kube-OVN/Longhorn 的 Helm Chart 等）。
在离线或特定受限的网络环境中：
1. **优先本地拷贝**：若本地已存在所需安装包且版本一致（表现为文件名完全一致），应当优先从本地目录拷贝，避免重复的网络下载开销。
2. **网络回退与无代理**：若本地未找到匹配的安装包，应通过 `curl` 进行正常下载，且下载过程中不配置任何代理（即不传入代理参数），保证网络行为的纯净性。

---

## 2. 详细设计方案

### 2.1 缓存检索目录定义
- 支持通过环境变量 `LOCAL_PKG_DIR` 来由用户手动指定宿主机或运行环境的本地包缓存路径。
- 如果用户未配置该环境变量，则默认使用项目内的 `${TOP_DIR}/cache/downloads` 目录。

### 2.2 重构目标
经分析，项目中的所有大依赖包（如 Charts、RKE2 归档）在执行 `scripts/build-bundle` 时都是使用公共库 [`scripts/lib/http`](file:///../../../../scripts/lib/http) 中的 `get_url` 函数完成的。
我们将重构该函数：
1. 优先校验 `$save_to` 对应路径是否存在文件，若存在则直接跳过。
2. 计算期望的本地包名称（对于保存的文件名和 URL 文件名都做匹配判定）。
3. 检查本地包目录 `LOCAL_PKG_DIR`，如果存在匹配的文件，则直接 `cp` 拷贝至目的地。
4. 若不满足本地匹配，则执行纯净的 `curl -sfL` 逻辑下载，不带任何代理参数。

### 2.3 `get_url` 重构伪代码
```bash
get_url()
{
  local from=$1
  local save_to=$2

  if [ -f "$save_to" ]; then
    echo "File already exists: ${save_to}"
    return 0
  fi

  local local_dir="${LOCAL_PKG_DIR:-${TOP_DIR}/cache/downloads}"
  local pkg_name=$(basename "$save_to")
  local url_pkg_name=$(basename "$from")

  if [ -d "$local_dir" ]; then
    if [ -f "$local_dir/$pkg_name" ]; then
      echo "Found local package matching target filename: $local_dir/$pkg_name"
      mkdir -p "$(dirname "$save_to")"
      cp "$local_dir/$pkg_name" "$save_to"
      return 0
    elif [ -f "$local_dir/$url_pkg_name" ]; then
      echo "Found local package matching URL filename: $local_dir/$url_pkg_name"
      mkdir -p "$(dirname "$save_to")"
      cp "$local_dir/$url_pkg_name" "$save_to"
      return 0
    fi
  fi

  echo "Download ${from} to ${save_to}..."
  mkdir -p "$(dirname "$save_to")"
  curl -sfL "$from" -o "$save_to"
}
```

---

## 3. 验证与测试用例

### 3.1 本地缓存命中测试
1. 在 `cache/downloads` 目录（或自定义的 `LOCAL_PKG_DIR` 目录）下预先放入一个伪造的包（如 `kube-ovn-v1.12.0.tgz`，内容为 `mocked-kubeovn`）。
2. 执行带有下载该包逻辑的构建脚本（如 `build-bundle` 中拉取 Kube-OVN 处）。
3. 观察日志输出是否打印 `Found local package...`，并检查最终 Chart 目录下的对应包内容是否为 `mocked-kubeovn`。

### 3.2 本地缓存未命中回退测试
1. 移除缓存目录下的对应文件。
2. 运行构建脚本，观测是否正常打印 `Download ...`，并通过 `curl` 从网络拉取到最新的真实包。

### 3.3 无代理行为核验
1. 检查所有的修改，确保在 `get_url` 的 `curl` 中不包含任何形如 `-x` 或 `--proxy` 的代理参数。
