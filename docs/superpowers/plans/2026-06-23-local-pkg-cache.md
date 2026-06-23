# 离线安装包本地缓存与无代理下载实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `scripts/lib/http` 中的 `get_url` 下载函数，以支持当本地已存在同版本安装包时优先从本地拷贝，否则通过无代理的 curl 从互联网下载。

**Architecture:** 在 `get_url` 函数中，通过查找环境变量 `LOCAL_PKG_DIR`（若未设置则默认为 `${TOP_DIR}/cache/downloads`）中的同名安装包实现本地拷贝；当未命中缓存时，采用无配置代理的 `curl` 进行正常下载。

**Tech Stack:** Bash shell script, git

---

### Task 1: 重构 `scripts/lib/http` 的 `get_url` 函数

**Files:**
- Modify: `scripts/lib/http`

- [ ] **Step 1: 修改 `scripts/lib/http` 的内容**
  重写 `get_url` 函数，增加本地拷贝逻辑及无代理 curl 参数。

修改后代码：
```bash
#!/bin/bash

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

- [ ] **Step 2: 自我代码审查**
  核对重构后的 `get_url` 代码，确保所有的参数、变量名（如 `local_dir`, `pkg_name`, `url_pkg_name`）在使用前已被定义，且语法符合标准 Bash。

---

### Task 2: 编写测试脚本验证 `get_url` 逻辑

**Files:**
- Create: `scripts/test-http-cache.sh`

- [ ] **Step 1: 创建单元测试脚本**
  新建 `scripts/test-http-cache.sh`，内容如下：

```bash
#!/bin/bash
set -e

TOP_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"
source ${TOP_DIR}/scripts/lib/http

# 准备测试清理与目录
TEST_DIR="${TOP_DIR}/cache/test_pkg_cache"
rm -rf "${TEST_DIR}"
mkdir -p "${TEST_DIR}"

MOCK_CACHE_DIR="${TEST_DIR}/mock_cache"
mkdir -p "${MOCK_CACHE_DIR}"
SAVE_DIR="${TEST_DIR}/save"
mkdir -p "${SAVE_DIR}"

# 1. 测试从网络正常下载 (未命中缓存)
export LOCAL_PKG_DIR="${MOCK_CACHE_DIR}"
get_url "https://raw.githubusercontent.com/kubeovn/kube-ovn/master/README.md" "${SAVE_DIR}/kube-ovn-readme.md"

if [ -f "${SAVE_DIR}/kube-ovn-readme.md" ]; then
  echo "Test 1: Network download success."
else
  echo "Test 1: Network download failed."
  exit 1
fi

# 2. 测试命中本地缓存 (目标同名文件匹配)
# 准备缓存文件
echo "mocked-content" > "${MOCK_CACHE_DIR}/kube-ovn-readme.md"
# 清理之前保存的文件
rm -f "${SAVE_DIR}/kube-ovn-readme.md"

get_url "https://raw.githubusercontent.com/kubeovn/kube-ovn/master/README.md" "${SAVE_DIR}/kube-ovn-readme.md"

content=$(cat "${SAVE_DIR}/kube-ovn-readme.md")
if [ "$content" = "mocked-content" ]; then
  echo "Test 2: Cache hit target filename success."
else
  echo "Test 2: Cache hit target filename failed, content is: $content"
  exit 1
fi

# 3. 测试命中本地缓存 (URL 同名文件匹配)
rm -rf "${SAVE_DIR}" "${MOCK_CACHE_DIR}"
mkdir -p "${SAVE_DIR}" "${MOCK_CACHE_DIR}"
# URL 中的文件名是 yq_linux_amd64，但 save_to 是 yq
echo "mocked-yq" > "${MOCK_CACHE_DIR}/yq_linux_amd64"
get_url "https://github.com/mikefarah/yq/releases/download/v4.52.5/yq_linux_amd64" "${SAVE_DIR}/yq"

content=$(cat "${SAVE_DIR}/yq")
if [ "$content" = "mocked-yq" ]; then
  echo "Test 3: Cache hit URL filename success."
else
  echo "Test 3: Cache hit URL filename failed, content is: $content"
  exit 1
fi

# 清理测试数据
rm -rf "${TEST_DIR}"
echo "All tests passed!"
```

- [ ] **Step 2: 赋予测试脚本执行权限**
  运行命令：
  `chmod +x scripts/test-http-cache.sh`

- [ ] **Step 3: 运行测试脚本并确保全部通过**
  运行命令：
  `./scripts/test-http-cache.sh`
  预期输出中应包含以下三行，且最后以 "All tests passed!" 结束：
  ```
  Test 1: Network download success.
  Test 2: Cache hit target filename success.
  Test 3: Cache hit URL filename success.
  All tests passed!
  ```

- [ ] **Step 4: 清理测试脚本**
  测试通过后，删除临时测试脚本：
  `rm -f scripts/test-http-cache.sh`

---

### Task 3: 提交修改到 Git

- [ ] **Step 1: 将修改提交至本地 Git 仓库**
  运行命令：
  ```bash
  git add scripts/lib/http docs/superpowers/plans/2026-06-23-local-pkg-cache.md
  git commit -m "feat(build): 增加离线包本地缓存优先拷贝机制" -m "Why: 对大依赖包下载提供本地优先拷贝选项，并在未命中时进行无代理下载" -m "What: 重构 scripts/lib/http 的 get_url 函数，新增 LOCAL_PKG_DIR 支持及文件同名拷贝判定"
  ```
