"""存储配置界面（模式 1/2）"""
import logging
from utils.whiptail_wrapper import Whiptail
from utils.validator import validate_disk

logger = logging.getLogger("vdi-installer")


class StorageConfigScreen:
    """Longhorn 存储配置界面"""

    def show(self):
        """收集存储配置参数

        返回: dict 或 None（用户取消）
        """
        wt = Whiptail(title="Storage Configuration", height=20, width=60)
        config = {}

        # 检测可用磁盘
        available_disks = self._detect_disks()

        wt.msgbox(
            "Longhorn Distributed Storage\n\n"
            "Longhorn requires a dedicated disk for VM image storage.\n"
            "A separate physical disk (e.g. /dev/sdb) is recommended.\n\n"
            f"Detected available disks:\n{available_disks}"
        )

        # Longhorn 专用磁盘
        while True:
            disk = wt.inputbox(
                "Enter Longhorn dedicated disk device path:\n\n"
                "This disk will be formatted and mounted to\n"
                "Longhorn data directory.\n"
                "WARNING: All data on this disk will be erased!",
                default="/dev/sdb"
            )
            if disk is None:
                return None
            valid, msg = validate_disk(disk)
            if valid:
                config["longhorn_disk"] = disk
                break
            wt.msgbox(f"Invalid disk path: {msg}")

        # 确认磁盘格式化
        if not wt.yesno(
            f"WARNING: Disk {disk} will be formatted!\n\n"
            f"All data on {disk} will be erased!\n"
            "Continue?",
            height=12
        ):
            return None

        # Longhorn 数据目录
        data_dir = wt.inputbox(
            "Enter Longhorn data directory:",
            default="/var/lib/longhorn"
        )
        if data_dir is None:
            return None
        config["longhorn_data_dir"] = data_dir

        # 副本数
        replicas = wt.radiolist(
            "Select default replica count:",
            [
                ("2", "2 replicas (min 2 nodes)", "OFF"),
                ("3", "3 replicas (recommended, min 3 nodes)", "ON"),
            ]
        )
        if replicas is None:
            return None
        config["longhorn_replicas"] = replicas

        logger.info(f"存储配置: disk={disk}, dir={data_dir}, replicas={replicas}")
        return config

    def _detect_disks(self):
        """检测可用磁盘设备"""
        import subprocess
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-o", "NAME,SIZE,TYPE,MOUNTPOINT", "-n"],
                capture_output=True, text=True
            )
            lines = []
            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2 and parts[0].startswith("sd"):
                    lines.append(f"  /dev/{parts[0]}  {parts[1]}")
            return "\n".join(lines[:8]) if lines else "  (No disks detected)"
        except Exception:
            return "  (Detection failed)"
