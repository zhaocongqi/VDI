"""日志工具模块"""
import logging
import os
import sys


def setup_logger(name="vdi-installer", log_dir="/var/log/vdi-deploy"):
    """配置并返回 logger 实例"""
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        pass  # 目录可能已存在或权限不足，忽略

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 文件处理器（详细日志）
    try:
        log_file = os.path.join(log_dir, "installer.log")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)
    except OSError:
        pass  # 无法写日志文件时降级为仅 stderr

    # stderr 处理器（关键错误输出到终端）
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(sh)

    return logger
