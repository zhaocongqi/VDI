"""参数校验工具"""
import re
import os
import logging

logger = logging.getLogger("vdi-installer")


def validate_ip(ip_str):
    """校验 IPv4 地址格式"""
    if not ip_str:
        return False, "IP address cannot be empty"
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip_str)
    if not match:
        return False, "Invalid IP address format"
    for octet in match.groups():
        if int(octet) > 255:
            return False, f"Invalid IP octet: {octet}"
    return True, ""


def validate_cidr(cidr_str):
    """校验 CIDR 格式"""
    if not cidr_str:
        return False, "CIDR cannot be empty"
    pattern = r'^(\d{1,3}\.){3}\d{1,3}/(\d{1,2})$'
    if not re.match(pattern, cidr_str):
        return False, "Invalid CIDR format (e.g. 10.16.0.0/16)"
    prefix = int(cidr_str.split('/')[1])
    if prefix < 8 or prefix > 32:
        return False, "CIDR prefix range: 8-32"
    return True, ""


def validate_hostname(hostname):
    """校验主机名"""
    if not hostname:
        return False, "Hostname cannot be empty"
    if len(hostname) > 63:
        return False, "Hostname must not exceed 63 characters"
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$'
    if not re.match(pattern, hostname):
        return False, "Hostname must contain only letters, digits and hyphens"
    return True, ""


def validate_disk(disk_path):
    """校验磁盘设备路径"""
    if not disk_path:
        return False, "Disk path cannot be empty"
    # 在 Live 系统中检查
    if os.path.exists(disk_path):
        return True, ""
    # 路径格式检查
    if disk_path.startswith("/dev/"):
        return True, ""  # 可能在部署时才存在
    return False, "Disk path must start with /dev/"


def validate_port(port_str):
    """校验端口号"""
    try:
        port = int(port_str)
        if 1 <= port <= 65535:
            return True, ""
        return False, "Port range: 1-65535"
    except ValueError:
        return False, "Port must be a number"


def validate_required_fields(config, required_keys):
    """校验必填字段"""
    missing = []
    for key in required_keys:
        if not config.get(key):
            missing.append(key)
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"
    return True, ""
