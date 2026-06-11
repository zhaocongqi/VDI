#!/bin/bash
# 构建脚本共享函数库

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 步骤标题
step() {
    echo -e "${BLUE}>>> $1${NC}"
}

# 信息
info() {
    echo -e "${YELLOW}[INFO] $1${NC}"
}

# 成功
ok() {
    echo -e "${GREEN}[OK] $1${NC}"
}

# 警告
warn() {
    echo -e "${YELLOW}[WARN] $1${NC}" >&2
}

# 错误
error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
}

# 检查命令是否存在
require_cmd() {
    local cmd=$1
    if ! command -v "$cmd" &>/dev/null; then
        error "需要 ${cmd}，但未安装"
        exit 1
    fi
}

# 批量检查命令
require_cmds() {
    for cmd in "$@"; do
        require_cmd "$cmd"
    done
}

# 带进度显示的下载
download_with_progress() {
    local url=$1
    local output=$2
    local desc="${3:-下载中}"

    echo -e "${YELLOW}[下载] ${desc}: $(basename "$output")${NC}"
    wget --progress=bar:force:noscroll -O "$output" "$url" 2>&1 || {
        error "下载失败: $url"
        return 1
    }
}

# 计算文件 SHA256
sha256_file() {
    sha256sum "$1" | cut -d' ' -f1
}

# source 所有共享函数库
source_libs() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    local lib_dir="${script_dir}/lib"
    if [ ! -d "$lib_dir" ] && [ -d "${script_dir}/../lib" ]; then
        lib_dir="${script_dir}/../lib"
    fi
    for lib in "${lib_dir}"/*.sh; do
        [ -f "$lib" ] && source "$lib"
    done
}

# 阶段校验：验证必需文件存在
validate_file() {
    local file="$1"
    local desc="${2:-文件}"
    if [ ! -f "$file" ]; then
        error "${desc}不存在: ${file}"
        return 1
    fi
}

# 阶段校验：验证必需目录存在
validate_dir() {
    local dir="$1"
    local desc="${2:-目录}"
    if [ ! -d "$dir" ]; then
        error "${desc}不存在: ${dir}"
        return 1
    fi
}

# 计算目录下所有文件的 sha256 并生成校验和文件
generate_checksums() {
    local base_dir="$1"
    local output="$2"
    (
        cd "$base_dir"
        find . -type f \
            ! -name 'checksums.sha256' \
            ! -name '.gitkeep' \
            ! -name 'metadata.yaml' \
            -exec sha256sum {} \;
    ) > "$output"
}
