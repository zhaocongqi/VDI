"""日志工具模块"""
import logging
import os


def setup_logger(name="vdi-installer", log_dir="/var/log/vdi-deploy"):
    """配置并返回 logger 实例"""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "installer.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 文件处理器（详细日志）
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)

    return logger
