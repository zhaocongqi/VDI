package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"vdi-installer/pkg/util"
)

// KickstartRender 把 VDIConfig 渲染成完整 kickstart ks.cfg，替代手写静态模板。
// anaconda 按 ks 无人值守装机：分区/装包/%post 装 RKE2 + 写 config/manifests。
// MVP3a：动态注入 network/rootpw/hostname/磁盘/RKE2 role + config。
// 复杂网络（bond/bridge/vlan）与组件栈 manifests 留 MVP4。
func KickstartRender(cfg *VDIConfig) (string, error) {
	var b strings.Builder

	// 静态头
	b.WriteString("# VDI kickstart（由 pkg/config/kickstart.go 从 VDIConfig 渲染）\n")
	b.WriteString("text\n")
	b.WriteString("cdrom\n")
	b.WriteString("keyboard --vckeymap=us --xlayouts='us'\n")
	b.WriteString("lang zh_CN.UTF-8\n")
	b.WriteString("timezone Asia/Shanghai --isUtc --utc\n")
	b.WriteString("selinux --permissive\n")
	b.WriteString("firewall --disabled\n")
	b.WriteString("reboot --eject\n")

	// 网络（ks network 指令做基础；bond/bridge/vlan 留 MVP4 %post 写 NM profiles）
	b.WriteString(kickstartNetwork(cfg) + "\n")

	// 磁盘：清盘 + LVM autopart，通过 Go 运行时动态探测物理主盘，防范异构设备不存在崩溃
	installDev, dataDev, err := detectInstallAndDataDisk(cfg)
	if err != nil {
		return "", fmt.Errorf("detect disk: %w", err)
	}
	// ignoredisk --only-use=<主盘>：仅允许 anaconda 看到/使用主盘。
	// 数据盘因此对 clearpart/autopart 不可见 → clearpart --all 只清主盘，数据盘原样保留，
	// 由 %post chroot 单独 mkfs.ext4 + 挂载 /var/lib/longhorn。
	// 注意：ignoredisk 只影响 anaconda 分区阶段视角，%post chroot 后 /dev/<数据盘> 仍可见可 mkfs。
	b.WriteString(fmt.Sprintf("ignoredisk --only-use=%s\n", installDev))
	b.WriteString("clearpart --all --initlabel\n")
	b.WriteString("autopart --type=lvm --fstype=ext4\n")
	b.WriteString("bootloader --append=\"console=ttyS0,115200 console=tty1\"\n")

	// root 密码：cfg.OS.Password 统一存明文（交互 TUI/自动模式/cloud-init 均明文）。
	// 渲染时用 Go 生成一次 sha512 crypt hash，rootpw --iscrypted 与 %post sed 共用同一 hash，
	// 避免 anaconda 与 %post 各自加密致 hash 不一致。anaconda 36 rootpw 偶发不生效，%post 兜底。
	rootHash := ""
	if cfg.OS.Password != "" {
		h, err := util.GetEncryptedPasswd(cfg.OS.Password)
		if err != nil {
			return "", fmt.Errorf("encrypt root password: %w", err)
		}
		rootHash = h
		b.WriteString(fmt.Sprintf("rootpw --iscrypted %s\n", rootHash))
	} else {
		b.WriteString("rootpw --lock\n")
	}

	// 包
	b.WriteString(kickstartPackages())

	// %post --nochroot 单 section：先复制 bundle，再解压 rke2/config/manifests/enable
	rke2Cfg, err := RenderRKE2Config(cfg)
	if err != nil {
		return "", fmt.Errorf("render rke2 config: %w", err)
	}
	manifests, err := RenderRKE2Manifests(cfg)
	if err != nil {
		return "", fmt.Errorf("render rke2 manifests: %w", err)
	}
	chrootBody := kickstartPostChroot(cfg, rke2Cfg, manifests, dataDev, rootHash)
	b.WriteString(kickstartPostNochroot(chrootBody))

	return b.String(), nil
}

// detectInstallAndDataDisk 在 Go 运行时（%pre 阶段）探测主盘与数据盘设备名（不含 /dev/ 前缀）。
// KickstartRender 在 %pre 阶段执行，此时看到的 /sys/block/* 与装机后目标系统磁盘拓扑一致
// （同一台物理机），故 %pre 探测结果可作为字面量嵌入 %post 脚本，避免 %post chroot 依赖 lsblk。
//   - 主盘：优先用 cfg.Install.Device（若在 /sys/block 存在），否则取首个物理盘
//   - 数据盘：优先用 cfg.Install.DataDisk（若存在），否则取"非主盘"的首个物理盘
//
// 主盘探测不到（无任何物理盘）返回 error，调用方应中止装机而非让 anaconda 盲选设备。
func detectInstallAndDataDisk(cfg *VDIConfig) (installDev, dataDev string, err error) {
	disks := detectPhysicalDisks()
	if len(disks) == 0 {
		return "", "", fmt.Errorf("no physical disk detected under /sys/block (sd*/vd*/nvme*)")
	}

	// 主盘
	want := strings.TrimPrefix(cfg.Install.Device, "/dev/")
	if want != "" {
		if _, statErr := os.Stat("/sys/block/" + want); statErr == nil {
			installDev = want
		}
	}
	if installDev == "" {
		installDev = disks[0]
	}

	// 数据盘
	wantData := strings.TrimPrefix(cfg.Install.DataDisk, "/dev/")
	if wantData != "" {
		if _, statErr := os.Stat("/sys/block/" + wantData); statErr == nil {
			dataDev = wantData
		}
	}
	if dataDev == "" {
		for _, d := range disks {
			if d != installDev {
				dataDev = d
				break
			}
		}
	}
	return installDev, dataDev, nil
}

// detectPhysicalDisks 扫描 /sys/block/ 返回 sd*/vd*/nvme* 物理盘设备名（按内核枚举顺序）。
func detectPhysicalDisks() []string {
	files, err := filepath.Glob("/sys/block/*")
	if err != nil {
		return nil
	}
	var disks []string
	for _, f := range files {
		name := filepath.Base(f)
		if strings.HasPrefix(name, "sd") || strings.HasPrefix(name, "vd") || strings.HasPrefix(name, "nvme") {
			disks = append(disks, name)
		}
	}
	return disks
}

// kickstartNetwork 渲染 ks network 指令（装机期 DHCP/静态 IP，拿地址供 anaconda）
// VDI 管理网络 bond/bridge 在 %post 由 NetworkManager profiles 接管（MVP4）
// hostname 一并写入同一条 network 指令（anaconda 对多条 network 行为不一致，单条最稳）
func kickstartNetwork(cfg *VDIConfig) string {
	mgmt := cfg.Install.ManagementInterface
	dev := "link"
	if len(mgmt.Interfaces) > 0 && mgmt.Interfaces[0].Name != "" {
		dev = mgmt.Interfaces[0].Name
	}
	var line string
	switch mgmt.Method {
	case NetworkMethodStatic:
		mask := mgmt.SubnetMask
		line = fmt.Sprintf("network --bootproto=static --device=%s --ip=%s --netmask=%s --gateway=%s --activate",
			dev, mgmt.IP, mask, mgmt.Gateway)
	default: // dhcp / none 都用 dhcp 拿装机期地址
		line = fmt.Sprintf("network --bootproto=dhcp --device=%s --activate", dev)
	}
	if cfg.OS.Hostname != "" {
		line += " --hostname=" + cfg.OS.Hostname
	}
	return line
}

func kickstartPackages() string {
	var b strings.Builder
	b.WriteString("%packages\n")
	b.WriteString("@core\n@base\n")
	b.WriteString("iptables\niproute\nipset\nebtables\nnet-tools\nbind-utils\nnfs-utils\npolicycoreutils-python-utils\n")
	b.WriteString("open-iscsi\n")
	b.WriteString("-firmware-*\n-iwl*-firmware\n")
	b.WriteString("%end\n")
	return b.String()
}

// kickstartPostNochroot：%post --nochroot 单 section，先从 ISO 复制离线 bundle，
// 再拼接 kickstartPostChroot 的 body（解压 rke2/config/manifests/enable），
// 所有写盘操作在一个 %post --nochroot section 内完成（避免 anaconda 36 多 section 丢写入）。
// anaconda 装机时 ISO 挂在 /run/install/repo，目标盘在 /mnt/sysroot
func kickstartPostNochroot(chrootBody string) string {
	return `%post --nochroot --interpreter=/bin/bash
set -x
echo ">>> [vdi] %post --nochroot START" > /dev/ttyS0
REPO=/run/install/repo
SYSROOT=/mnt/sysroot
BUNDLE=${REPO}/bundle/vdi
mkdir -p ${SYSROOT}/var/lib/rancher/rke2/agent/images
cp -f ${BUNDLE}/images/*.tar.zst ${SYSROOT}/var/lib/rancher/rke2/agent/images/ 2>/dev/null || echo "WARN: 无 rke2 images"
# RKE2 二进制 tar：缺失则 chroot 解压会失败，但不在此 exit（anaconda 各 %post 段独立，
# exit 1 会让本段中止但 chroot 段仍跑；为统一诊断，缺失仅 WARN，chroot 段自检后处理）
cp -f ${BUNDLE}/binaries/rke2.linux-*.tar.gz ${SYSROOT}/tmp/rke2.tar.gz 2>/dev/null || echo "WARN: 缺 rke2.linux-*.tar.gz（路径=${BUNDLE}/binaries/）"
ls -l ${SYSROOT}/tmp/rke2.tar.gz 2>/dev/null || echo "WARN: rke2.tar.gz 未复制到 sysroot"
mkdir -p ${SYSROOT}/var/lib/rancher/rke2/server/charts
cp -f ${BUNDLE}/charts/*.tgz ${SYSROOT}/var/lib/rancher/rke2/server/charts/ 2>/dev/null || echo "WARN: 无 charts"
# kubevirt operator 多文档 manifest：放 server/manifests/ 让 RKE2 首启自动 apply
# （operator 装好后处理 helmchart-kubevirt.yaml 的 KubeVirt CR）
mkdir -p ${SYSROOT}/var/lib/rancher/rke2/server/manifests
cp -f ${BUNDLE}/manifests/*.yaml ${SYSROOT}/var/lib/rancher/rke2/server/manifests/ 2>/dev/null || echo "WARN: 无 operator manifests"
echo ">>> [vdi] %post --nochroot END（接 sysroot 段）" > /dev/ttyS0
` + chrootBody + `
sync
echo ">>> [vdi] %post 全部完成 sync" > /dev/ttyS0
%end
`
}

// kickstartPostChroot：解压 RKE2 + 写 config/manifests + enable（落到目标系统根）
// rke2Cfg/manifests 由 RenderRKE2Config/Manifests 渲染，嵌入 heredoc。
//
// ⚠️ chroot 红线（踩坑修复）：BCLinux anaconda 36 的 %post（不带 --nochroot）实测不会
// chroot 到 /mnt/sysroot，所有相对路径操作（/etc /usr/local /var/lib）落在装机 ramdisk，
// 重启后全部丢失（实测 rke2 二进制/config/manifests/sshd drop-in 无一落地，root 仅靠
// anaconda rootpw 兜底）。故改用 --nochroot + $SYSROOT(/mnt/sysroot) 绝对前缀显式写盘；
// 需目标系统工具（chpasswd）的用 `chroot $SYSROOT ...`。
//
// ⚠️ 多 %post section 红线：BCLinux anaconda 36 对多个 %post --nochroot section 的执行
// 不稳定（首段写入保留，后续段写入偶发丢失，致 rke2/config/manifests 落盘失败但诊断
// 显示成功）。故本函数不再独立成 section，由 kickstartPostNochroot 在同一 %post --nochroot
// section 内 %end 前拼接本函数 body，确保所有写盘操作在一个 section 内原子完成。
func kickstartPostChroot(cfg *VDIConfig, rke2Cfg string, manifests map[string]string, dataDev string, rootHash string) string {
	var b strings.Builder
	b.WriteString("echo \">>> [vdi] %post sysroot START\" > /dev/ttyS0\n")
	// root 密码（anaconda rootpw 偶发不生效，%post 兜底）。
	// rootHash 由 KickstartRender 渲染时用 Go sha512_crypt 生成（对 cfg.OS.Password 明文加密一次），
	// 直接 sed 替换 sysroot /etc/shadow root 行。完全绕过 chpasswd/PAM/pwquality（纯数字/短密码
	// 经 chpasswd 会被 pam_chauthtok 拒）与 chroot（%post --nochroot 下 /proc 未挂 PAM 易失败）。
	if rootHash != "" {
		// hash 含 $（如 $6$salt$hash），%post 在 shell 双引号下执行，$ 会被当变量展开致 hash 残缺。
		// 转义 $ 为 \$ 后嵌入 sed 替换串。
		escHash := strings.ReplaceAll(rootHash, "$", `\$`)
		b.WriteString(fmt.Sprintf("sed -i -e \"s|^root:[^:]*:|root:%s:|\" $SYSROOT/etc/shadow\n", escHash))
		b.WriteString("echo \">>> [vdi] %post rootpw set via sed (sha512 from renderer)\" > /dev/ttyS0\n")
		b.WriteString("chroot $SYSROOT passwd -u root 2>/dev/null || true\n")
	}
	// sshd：允许 root + 密码登录，关 UseDNS/GSSAPI（避免 qemu user 网下 reverse DNS 致 SSH banner 超时）
	b.WriteString("mkdir -p $SYSROOT/etc/ssh/sshd_config.d\n")
	b.WriteString("cat > $SYSROOT/etc/ssh/sshd_config.d/00-vdi-root-login.conf <<'SSHD'\nPermitRootLogin yes\nPasswordAuthentication yes\nUseDNS no\nGSSAPIAuthentication no\nSSHD\n")
	b.WriteString("sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin yes/g' $SYSROOT/etc/ssh/sshd_config || true\n")
	b.WriteString("sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication yes/g' $SYSROOT/etc/ssh/sshd_config || true\n")
	b.WriteString("mkdir -p $SYSROOT/etc/systemd/system/multi-user.target.wants\n")
	b.WriteString("ln -sf /usr/lib/systemd/system/sshd.service $SYSROOT/etc/systemd/system/multi-user.target.wants/sshd.service\n")
	// longhorn-manager 需宿主机 iscsiadm（open-iscsi）+ iscsid 运行，否则 nsenter 调 iscsiadm 失败
	b.WriteString("ln -sf /usr/lib/systemd/system/iscsid.service $SYSROOT/etc/systemd/system/multi-user.target.wants/iscsid.service 2>/dev/null || true\n")

	// 数据盘处理 (MVP4)：dataDev 由 detectInstallAndDataDisk 在 %pre 阶段用 Go 读
	// /sys/block/* 探测得到（含用户显式指定），作为字面量嵌入 %post，不再依赖 lsblk。
	// mkfs 操作裸设备不需 chroot；mkdir/fstab 写到 $SYSROOT。
	dataDiskPath := ""
	if dataDev != "" {
		dataDiskPath = "/dev/" + dataDev
	}
	b.WriteString(fmt.Sprintf(`
# ----------------- 数据盘处理 (MVP4) -----------------
DATA_DISK="%s"

if [ -n "${DATA_DISK}" ] && [ -b "${DATA_DISK}" ]; then
    echo ">>> [vdi] mkfs 数据盘 ${DATA_DISK}" > /dev/ttyS0
    mkfs.ext4 -F -L VDI_LH_DEFAULT "${DATA_DISK}"
    mkdir -p $SYSROOT/var/lib/longhorn
    echo "LABEL=VDI_LH_DEFAULT /var/lib/longhorn ext4 defaults,noatime,nofail 0 2" >> $SYSROOT/etc/fstab
fi
`, dataDiskPath))

	// 解压 RKE2 二进制到 $SYSROOT/usr/local（tar -C 绝对前缀，不需 chroot）
	b.WriteString("echo \">>> [vdi] tar 解压 rke2 前，文件存在性:\" > /dev/ttyS0\n")
	b.WriteString("ls -l $SYSROOT/tmp/rke2.tar.gz > /dev/ttyS0 2>&1\n")
	b.WriteString("tar xzf $SYSROOT/tmp/rke2.tar.gz -C $SYSROOT/usr/local && echo \">>> [vdi] tar 解压 OK\" > /dev/ttyS0 || echo \">>> [vdi] tar 解压失败\" > /dev/ttyS0\n")
	b.WriteString("rm -f $SYSROOT/tmp/rke2.tar.gz\n")
	b.WriteString("echo \">>> [vdi] rke2 二进制:\" > /dev/ttyS0\n")
	b.WriteString("ls -l $SYSROOT/usr/local/bin/rke2 > /dev/ttyS0 2>&1\n")
	// RKE2 config（heredoc，引用变量需转义避免 shell 展开）
	b.WriteString("mkdir -p $SYSROOT/etc/rancher/rke2\ncat > $SYSROOT/etc/rancher/rke2/config.yaml <<'RKE2CFG'\n")
	b.WriteString(rke2Cfg)
	b.WriteString("\nRKE2CFG\n")
	// 首节点写 HelmChart manifests
	if cfg.Install.Role == RoleFirst {
		b.WriteString("mkdir -p $SYSROOT/var/lib/rancher/rke2/server/manifests\n")
		for name, content := range manifests {
			b.WriteString(fmt.Sprintf("cat > $SYSROOT/var/lib/rancher/rke2/server/manifests/%s <<'MANIFEST'\n%s\nMANIFEST\n", name, content))
		}
		// RKE2 v1.31 helm-controller 对 spec.chart 本地路径不注入 chart content Secret，
		// helm-install job pod 报 "path ... not found"。改用 spec.chartContent（base64 内联）
		// 绕过本地路径读取：对每个 helmchart-*.yaml，将 spec.chart 行替换为 spec.chartContent
		// + base64 编码的 tgz 内容（从已复制的 server/charts/ 读取）。
		b.WriteString("for mf in $SYSROOT/var/lib/rancher/rke2/server/manifests/helmchart-*.yaml; do\n")
		b.WriteString("  [ -f \"$mf\" ] || continue\n")
		b.WriteString("  chart_path=$(sed -n 's/^  chart: //p' \"$mf\" 2>/dev/null)\n")
		b.WriteString("  [ -n \"$chart_path\" ] || continue\n")
		b.WriteString("  chart_file=$SYSROOT$chart_path\n")
		b.WriteString("  [ -f \"$chart_file\" ] || continue\n")
		b.WriteString("  b64=$(base64 -w0 \"$chart_file\" 2>/dev/null)\n")
		b.WriteString("  [ -n \"$b64\" ] || continue\n")
		b.WriteString("  sed -i \"/^  chart: /c\\  chartContent: ${b64}\" \"$mf\"\n")
		b.WriteString("  echo \">>> [vdi] helmchart $(basename $mf) chart→chartContent 注入\" > /dev/ttyS0\n")
		b.WriteString("done\n")
	}
	// enable rke2-server（首节点/Master控制平面）或 rke2-agent（Worker/Witness工作节点）
	// ln -sf 创建 wants 链接：链接文件内写开机后绝对路径（/usr/local/lib/...），链接位置在 $SYSROOT
	service := "rke2-server"
	if cfg.Install.Role == RoleWorker || cfg.Install.Role == RoleWitness {
		service = "rke2-agent"
	} else if cfg.Install.Role == "" && cfg.ServerURL != "" {
		service = "rke2-agent"
	}
	b.WriteString(fmt.Sprintf("ln -sf /usr/local/lib/systemd/system/%s.service $SYSROOT/etc/systemd/system/multi-user.target.wants/%s.service\n", service, service))
	b.WriteString(fmt.Sprintf("echo \">>> [vdi] enable %s 完成\" > /dev/ttyS0\n", service))
	b.WriteString("echo \">>> [vdi] %post sysroot END\" > /dev/ttyS0\n")
	return b.String()
}
