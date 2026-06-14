"""磁盘分区配置界面（所有模式 — 装机必备）

用户选择目标磁盘和分区方案，装机脚本据此执行分区→格式化→写盘。
"""
import curses
import json
import logging
import subprocess
from widgets import inputbox, msgbox, yesno, radiolist

logger = logging.getLogger("vdi-installer")


class DiskConfigScreen:
    """磁盘分区配置界面"""

    def show(self, stdscr, default_hostname="vdi-node-01"):
        """收集磁盘分区配置

        Returns:
            dict 或 None（用户取消）
        """
        # 检测可用磁盘
        disks = self._detect_disks()
        if not disks:
            msgbox(stdscr, "No Disk Found",
                   "No available disks detected.\n\n"
                   "OS installation requires at least one disk.")
            return None

        config = {}

        # 展示可用磁盘列表
        disk_list = "\n".join(
            f"  /dev/{d['name']}  {d['size']}  {d.get('model', '')}"
            for d in disks
        )
        msgbox(stdscr, "Disk Selection",
               f"Available disks:\n\n{disk_list}\n\n"
               "WARNING: The selected disk will be ERASED completely!")

        # 选择目标磁盘
        disk_dev = self._select_disk(stdscr, disks)
        if disk_dev is None:
            return None
        config["install_disk"] = disk_dev

        # 选择分区方案
        scheme = radiolist(stdscr,
                           title="Partition Scheme",
                           text="Select partition layout:\n\n"
                                "Auto: EFI(512M) + swap(auto) + /(rest)\n"
                                "Minimal: EFI(512M) + /(rest, no swap)",
                           items=[
                               ("auto", "Auto (EFI + swap + root)", "ON"),
                               ("minimal", "Minimal (EFI + root only)", "OFF"),
                           ])
        if scheme is None:
            return None
        config["partition_scheme"] = scheme

        # swap 大小（仅 auto 方案）
        if scheme == "auto":
            swap_size = inputbox(stdscr,
                                 title="Swap Configuration",
                                 text="Enter swap partition size (e.g. 4G, 8G, 16G):\n\n"
                                      "Recommended: equal to RAM size",
                                 default="8G")
            if swap_size is None:
                return None
            config["swap_size"] = swap_size
        else:
            config["swap_size"] = "0"

        # 主机名
        hostname = inputbox(stdscr,
                            title="System Configuration",
                            text="Enter hostname for the installed system:",
                            default=default_hostname)
        if hostname is None:
            return None
        config["hostname"] = hostname

        # 确认 — 最终警告
        if not yesno(stdscr,
                     title="CONFIRM DISK ERASE",
                     text=f"WARNING: ALL DATA on {disk_dev} will be DESTROYED!\n\n"
                          f"Disk: {disk_dev}\n"
                          f"Scheme: {scheme}\n"
                          f"Swap: {config['swap_size']}\n"
                          f"Hostname: {config['hostname']}\n\n"
                          "This action CANNOT be undone. Continue?"):
            return None

        logger.info(f"磁盘配置: disk={disk_dev} scheme={scheme} swap={config['swap_size']}")
        return config

    def _detect_disks(self):
        """通过 lsblk 检测可用磁盘，排除 Live 介质和 CD-ROM"""
        try:
            result = subprocess.run(
                ["lsblk", "-d", "-J", "-o", "NAME,SIZE,TYPE,ROTA,MODEL,MOUNTPOINT"],
                capture_output=True, text=True
            )
            data = json.loads(result.stdout)
        except Exception:
            logger.exception("磁盘检测失败")
            return []

        # 检测 Live 介质所在设备（通常是 sr0 或挂载 /cdrom 的设备）
        live_dev = self._get_live_device()

        disks = []
        for dev in data.get("blockdevices", []):
            name = dev["name"]
            # 排除 CD-ROM（sr*）、Live 介质、回环设备
            if name.startswith("sr") or name.startswith("loop"):
                continue
            if live_dev and name == live_dev:
                continue
            # 只取磁盘类型
            if dev.get("type") != "disk":
                continue
            disks.append({
                "name": name,
                "size": dev.get("size", "unknown"),
                "model": dev.get("model", "").strip(),
                "rotational": dev.get("rota", "1"),
            })
        return disks

    def _select_disk(self, stdscr, disks):
        """让用户从可用磁盘列表中选择"""
        if len(disks) == 1:
            d = disks[0]
            msgbox(stdscr, "Auto Selected",
                   f"Only one disk found:\n\n"
                   f"  /dev/{d['name']}  {d['size']}  {d.get('model', '')}\n\n"
                   "This disk will be used for installation.")
            return f"/dev/{d['name']}"

        items = []
        for d in disks:
            label = f"/dev/{d['name']}  {d['size']}"
            if d.get("model"):
                label += f"  ({d['model']})"
            items.append((f"/dev/{d['name']}", label, "OFF"))
        items[0] = (items[0][0], items[0][1], "ON")

        selected = radiolist(stdscr,
                             title="Select Install Disk",
                             text="Choose the target disk for OS installation:\n\n"
                                  "WARNING: Selected disk will be ERASED!",
                             items=items)
        return selected

    def _get_live_device(self):
        """检测 Live 介质底层设备名（排除用）"""
        try:
            result = subprocess.run(
                ["lsblk", "-no", "PKNAME", "/cdrom"],
                capture_output=True, text=True
            )
            return result.stdout.strip() or None
        except Exception:
            return None
