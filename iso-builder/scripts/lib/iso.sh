#!/bin/bash
# ISO 打包封装函数库
# 参考 Harvester scripts/lib/iso 的 pack_iso 函数

pack_iso() {
    local iso_output="$1"
    local iso_root="$2"
    local efi_img="$3"
    local vol_id="${4:-VDI-INSTALL}"

    echo ">>> 打包 ISO: $(basename "$iso_output")"

    # 查找 isohdpfx 用于 MBR 混合引导
    local isohdpfx=""
    isohdpfx="$(find_isohdpfx)" || true

    # 确保输出路径可用（覆盖已有文件）
    rm -f "$iso_output"

    local xorriso_args=(
        -volid "$vol_id"
        -joliet on
        -padding 0
        -outdev "$iso_output"
        -map "$iso_root" /
        -chmod 0755 --
        -append_partition 2 0xef "$efi_img"
        # BIOS 引导 (isolinux)
        -boot_image isolinux bin_path="isolinux/isolinux.bin"
        -boot_image isolinux cat_path="boot/boot.catalog"
        -boot_image isolinux cat_hidden=on
        -boot_image isolinux load_size=2048
        -boot_image isolinux boot_info_table=on
        # EFI 引导 (第二引导项)
        -boot_image any next
        -boot_image any efi_path="--interval:appended_partition_2:all::"
        -boot_image any platform_id=0xef
        -boot_image any appended_part_as=gpt
        -boot_image any partition_offset=16
    )

    # MBR 混合引导支持
    if [ -n "$isohdpfx" ]; then
        xorriso_args+=(
            -boot_image isolinux system_area="$isohdpfx"
            -boot_image isolinux partition_table=on
        )
    fi

    xorriso "${xorriso_args[@]}"

    echo "    ISO 大小: $(du -sh "$iso_output" | cut -f1)"
}

create_efi_image() {
    local output_img="$1"

    local efi_tmp
    efi_tmp="$(mktemp -d)"
    mkdir -p "${efi_tmp}/EFI/BOOT"

    grub-mkimage -O x86_64-efi \
        -o "${efi_tmp}/EFI/BOOT/BOOTX64.EFI" \
        -p "/boot/grub" \
        -d /usr/lib/grub/x86_64-efi \
        linuxefi linux normal iso9660 part_msdos part_gpt fat \
        search search_fs_file search_fs_uuid search_label \
        serial terminal gfxterm gfxterm_background gfxterm_menu \
        halt reboot configfile echo ls cat chain loadenv

    dd if=/dev/zero of="$output_img" bs=1M count=8 2>/dev/null
    mkfs.vfat -F 12 "$output_img"
    mmd -i "$output_img" ::EFI ::EFI/BOOT
    mcopy -i "$output_img" \
        "${efi_tmp}/EFI/BOOT/BOOTX64.EFI" "::EFI/BOOT/BOOTX64.EFI"

    rm -rf "$efi_tmp"
    echo "    EFI 镜像已创建: $(basename "$output_img")"
}

copy_isolinux_files() {
    local isolinux_dir="$1"
    mkdir -p "$isolinux_dir"

    if [ -d /usr/lib/ISOLINUX ]; then
        cp /usr/lib/ISOLINUX/isolinux.bin "${isolinux_dir}/"
        cp /usr/lib/syslinux/modules/bios/ldlinux.c32 "${isolinux_dir}/" 2>/dev/null || true
        cp /usr/lib/syslinux/modules/bios/libcom32.c32 "${isolinux_dir}/" 2>/dev/null || true
        cp /usr/lib/syslinux/modules/bios/libutil.c32 "${isolinux_dir}/" 2>/dev/null || true
    elif [ -d /usr/lib/syslinux ]; then
        cp /usr/lib/syslinux/isolinux.bin "${isolinux_dir}/"
        cp /usr/lib/syslinux/ldlinux.c32 "${isolinux_dir}/" 2>/dev/null || true
    fi
    echo "    isolinux 文件已复制"
}

find_isohdpfx() {
    for path in /usr/lib/ISOLINUX/isohdpfx.bin /usr/lib/syslinux/mbr/isohdpfx.bin /usr/lib/syslinux/isohdpfx.bin; do
        [ -f "$path" ] && echo "$path" && return 0
    done
    return 1
}
