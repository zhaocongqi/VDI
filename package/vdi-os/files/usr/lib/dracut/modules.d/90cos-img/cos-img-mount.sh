#!/bin/sh
# cos-img pre-pivot hook: 把 COS_STATE 分区内的 cos-img/filename 指向的镜像 loop 挂载，bind 覆盖 /sysroot
# pre-pivot 时 /sysroot 已挂 COS_STATE（含 cOS/active.img），但 COS_STATE 分区本身不是 OS tree（无 os-release）
# 需用 active.img 覆盖 /sysroot，否则 switch-root 因 os-release missing 失败
# 用 bind 而非 umount/move：避免 shared mount 限制 + 不与 systemd 的 sysroot.mount 冲突

type getarg >/dev/null 2>&1 || . /lib/dracut-lib.sh

cos_img=$(getarg cos-img/filename=)
[ -z "$cos_img" ] && return 0

img_path="/sysroot${cos_img}"
[ -f "$img_path" ] || { echo "cos-img: $img_path not found"; return 0; }

mkdir -p /run/cos-img
losetup --show -f "$img_path" > /run/cos-img/loopdev 2>/dev/null || { echo "cos-img: losetup failed"; return 1; }
loopdev=$(cat /run/cos-img/loopdev)

mkdir -p /run/cos-img/root
# rw 挂载：RKE2 运行时需写 /var/lib/rancher、/etc/rancher 等（active.img 内）
mount -o rw "$loopdev" /run/cos-img/root 2>/dev/null || mount -o rw -t ext2 "$loopdev" /run/cos-img/root || { echo "cos-img: mount loop failed"; return 1; }

# bind 覆盖 /sysroot（COS_STATE → active.img 内容），保持 rw
mount --bind /run/cos-img/root /sysroot || { echo "cos-img: bind /sysroot failed"; return 1; }

echo "cos-img: /sysroot bound to $cos_img via $loopdev"
