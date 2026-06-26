#!/bin/bash
# dracut module: cos-img
# 处理内核参数 cos-img/filename=/cOS/active.img：把 root=LABEL= 分区内的镜像文件 loop 挂载到 /sysroot
# 对齐 elemental-toolkit cos 引导机制（harvester SUSE MicroOS 自带，BCLinux 需手动注入）

# called by dracut
check() {
    return 255
}

# called by dracut
depends() {
    return 0
}

# called by dracut
installkernel() {
    instmods loop
}

# called by dracut
install() {
    inst_multiple losetup mount grep
    inst_hook pre-pivot 90 "$moddir/cos-img-mount.sh"
}

