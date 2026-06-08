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
        wt = Whiptail(title="存储配置", height=20, width=60)
        config = {}

        # 检测可用磁盘
        available_disks = self._detect_disks()

        wt.msgbox(
            "Longhorn 分布式存储配置\n\n"
            "Longhorn 需要一块专用磁盘用于存储虚拟机镜像数据。\n"
            "建议使用独立的物理磁盘（如 /dev/sdb）。\n\n"
            f"检测到的可用磁盘:\n{available_disks}"
        )

        # Longhorn 专用磁盘
        while True:
            disk = wt.inputbox(
                "请输入 Longhorn 专用磁盘设备路径：\n\n"
                "此磁盘将被格式化并挂载到 Longhorn 数据目录。\n"
                "警告：磁盘上的数据将被清除！",
                default="/dev/sdb"
            )
            if disk is None:
                return None
            valid, msg = validate_disk(disk)
            if valid:
                config["longhorn_disk"] = disk
                break
            wt.msgbox(f"磁盘路径错误: {msg}")

        # 确认磁盘格式化
        if not wt.yesno(
            f"警告：即将格式化磁盘 {disk}\n\n"
            f"磁盘 {disk} 上的所有数据将被清除！\n"
            "确认继续？",
            height=12
        ):
            return None

        # Longhorn 数据目录
        data_dir = wt.inputbox(
            "请输入 Longhorn 数据目录：",
            default="/var/lib/longhorn"
        )
        if data_dir is None:
            return None
        config["longhorn_data_dir"] = data_dir

        # 副本数
        replicas = wt.radiolist(
            "请选择默认副本数：",
            [
                ("2", "2 副本（最少 2 节点）", "OFF"),
                ("3", "3 副本（推荐，最少 3 节点）", "ON"),
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
            return "\n".join(lines[:8]) if lines else "  (未检测到可用磁盘)"
        except Exception:
            return "  (检测失败)"
