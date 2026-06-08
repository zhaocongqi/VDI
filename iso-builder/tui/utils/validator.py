"""参数校验工具"""
import re
import os
import logging

logger = logging.getLogger("vdi-installer")


def validate_ip(ip_str):
    """校验 IPv4 地址格式"""
    if not ip_str:
        return False, "IP 地址不能为空"
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip_str)
    if not match:
        return False, "IP 地址格式不正确"
    for octet in match.groups():
        if int(octet) > 255:
            return False, f"无效的 IP 地址段: {octet}"
    return True, ""


def validate_cidr(cidr_str):
    """校验 CIDR 格式"""
    if not cidr_str:
        return False, "CIDR 不能为空"
    pattern = r'^(\d{1,3}\.){3}\d{1,3}/(\d{1,2})$'
    if not re.match(pattern, cidr_str):
        return False, "CIDR 格式不正确（例如 10.16.0.0/16）"
    prefix = int(cidr_str.split('/')[1])
    if prefix < 8 or prefix > 32:
        return False, "CIDR 前缀范围: 8-32"
    return True, ""


def validate_hostname(hostname):
    """校验主机名"""
    if not hostname:
        return False, "主机名不能为空"
    if len(hostname) > 63:
        return False, "主机名长度不能超过 63 字符"
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$'
    if not re.match(pattern, hostname):
        return False, "主机名只能包含字母、数字和连字符"
    return True, ""


def validate_disk(disk_path):
    """校验磁盘设备路径"""
    if not disk_path:
        return False, "磁盘路径不能为空"
    # 在 Live 系统中检查
    if os.path.exists(disk_path):
        return True, ""
    # 路径格式检查
    if disk_path.startswith("/dev/"):
        return True, ""  # 可能在部署时才存在
    return False, "磁盘路径应以 /dev/ 开头"


def validate_port(port_str):
    """校验端口号"""
    try:
        port = int(port_str)
        if 1 <= port <= 65535:
            return True, ""
        return False, "端口范围: 1-65535"
    except ValueError:
        return False, "端口必须是数字"


def validate_required_fields(config, required_keys):
    """校验必填字段"""
    missing = []
    for key in required_keys:
        if not config.get(key):
            missing.append(key)
    if missing:
        return False, f"缺少必填字段: {', '.join(missing)}"
    return True, ""
