package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
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
	b.WriteString(fmt.Sprintf("timezone Asia/Shanghai --utc\n"))
	b.WriteString("selinux --permissive\n")
	b.WriteString("firewall --disabled\n")
	b.WriteString("reboot --eject\n")

	// 网络（ks network 指令做基础；bond/bridge/vlan 留 MVP4 %post 写 NM profiles）
	b.WriteString(kickstartNetwork(cfg) + "\n")

	// 磁盘：清盘 + LVM autopart，通过 Go 运行时动态探测物理主盘，防范异构设备不存在崩溃
	installDev, dataDev := detectInstallAndDataDisk(cfg)
	if installDev != "" {
		b.WriteString(fmt.Sprintf("ignoredisk --only-use=%s\n", installDev))
	}
	// 显式排除数据盘，防止 clearpart/autopart 扫描或 LVM 误伤（多盘隔离防线）
	if dataDev != "" {
		b.WriteString(fmt.Sprintf("ignoredisk --drives=%s\n", dataDev))
	}
	b.WriteString("clearpart --all --initlabel\n")
	b.WriteString("autopart --type=lvm --fstype=ext4\n")
	b.WriteString("bootloader --append=\"console=ttyS0,115200 console=tty1\"\n")

	// root 密码：明文兜底（%post chpasswd 再设一次，anaconda 36 rootpw 偶发不生效）
	b.WriteString(fmt.Sprintf("rootpw %s\n", cfg.OS.Password))

	// hostname
	if cfg.OS.Hostname != "" {
		b.WriteString(fmt.Sprintf("network --hostname=%s\n", cfg.OS.Hostname))
	}

	// 包
	b.WriteString(kickstartPackages())

	// %post --nochroot：从 ISO 复制 bundle（镜像/二进制/charts）
	b.WriteString(kickstartPostNochroot())

	// %post chroot：解压 RKE2 + config + manifests + enable
	rke2Cfg, err := RenderRKE2Config(cfg)
	if err != nil {
		return "", fmt.Errorf("render rke2 config: %w", err)
	}
	manifests, err := RenderRKE2Manifests(cfg)
	if err != nil {
		return "", fmt.Errorf("render rke2 manifests: %w", err)
	}
	b.WriteString(kickstartPostChroot(cfg, rke2Cfg, manifests, dataDev))

	return b.String(), nil
}

// detectInstallAndDataDisk 在 Go 运行时（%pre 阶段）探测主盘与数据盘设备名（不含 /dev/ 前缀）。
// KickstartRender 在 %pre 阶段执行，此时看到的 /sys/block/* 与装机后目标系统磁盘拓扑一致
// （同一台物理机），故 %pre 探测结果可作为字面量嵌入 %post 脚本，避免 %post chroot 依赖 lsblk。
//   - 主盘：优先用 cfg.Install.Device（若在 /sys/block 存在），否则取首个物理盘
//   - 数据盘：优先用 cfg.Install.DataDisk（若存在），否则取"非主盘"的首个物理盘
//
// 任一探测失败返回空串，调用方据此决定是否写 ignoredisk 行。
func detectInstallAndDataDisk(cfg *VDIConfig) (installDev, dataDev string) {
	disks := detectPhysicalDisks()

	// 主盘
	want := strings.TrimPrefix(cfg.Install.Device, "/dev/")
	if want != "" {
		if _, err := os.Stat("/sys/block/" + want); err == nil {
			installDev = want
		}
	}
	if installDev == "" && len(disks) > 0 {
		installDev = disks[0]
	}

	// 数据盘
	wantData := strings.TrimPrefix(cfg.Install.DataDisk, "/dev/")
	if wantData != "" {
		if _, err := os.Stat("/sys/block/" + wantData); err == nil {
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
	return installDev, dataDev
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
func kickstartNetwork(cfg *VDIConfig) string {
	mgmt := cfg.Install.ManagementInterface
	dev := "link"
	if len(mgmt.Interfaces) > 0 && mgmt.Interfaces[0].Name != "" {
		dev = mgmt.Interfaces[0].Name
	}
	switch mgmt.Method {
	case NetworkMethodStatic:
		mask := mgmt.SubnetMask
		return fmt.Sprintf("network --bootproto=static --device=%s --ip=%s --netmask=%s --gateway=%s --activate",
			dev, mgmt.IP, mask, mgmt.Gateway)
	default: // dhcp / none 都用 dhcp 拿装机期地址
		return fmt.Sprintf("network --bootproto=dhcp --device=%s --activate", dev)
	}
}

func kickstartPackages() string {
	var b strings.Builder
	b.WriteString("%packages\n")
	b.WriteString("@core\n@base\n")
	b.WriteString("iptables\niproute\nipset\nebtables\nnet-tools\nbind-utils\nnfs-utils\npolicycoreutils-python-utils\n")
	b.WriteString("-firmware-*\n-iwl*-firmware\n")
	b.WriteString("%end\n")
	return b.String()
}

// kickstartPostNochroot：%post --nochroot 从 ISO 复制离线 bundle 到目标盘
// anaconda 装机时 ISO 挂在 /run/install/repo，目标盘在 /mnt/sysroot
func kickstartPostNochroot() string {
	return `%post --nochroot --interpreter=/bin/bash
set -x
REPO=/run/install/repo
SYSROOT=/mnt/sysroot
BUNDLE=${REPO}/bundle/vdi
mkdir -p ${SYSROOT}/var/lib/rancher/rke2/agent/images
cp -f ${BUNDLE}/images/*.tar.zst ${SYSROOT}/var/lib/rancher/rke2/agent/images/ 2>/dev/null || echo "WARN: 无 rke2 images"
cp -f ${BUNDLE}/binaries/rke2.linux-*.tar.gz ${SYSROOT}/tmp/rke2.tar.gz
mkdir -p ${SYSROOT}/var/lib/rancher/rke2/server/charts
cp -f ${BUNDLE}/charts/*.tgz ${SYSROOT}/var/lib/rancher/rke2/server/charts/ 2>/dev/null || echo "WARN: 无 charts"
sync
%end
`
}

// kickstartPostChroot：%post chroot 解压 RKE2 + 写 config/manifests + enable
// rke2Cfg/manifests 由 RenderRKE2Config/Manifests 渲染，嵌入 heredoc
func kickstartPostChroot(cfg *VDIConfig, rke2Cfg string, manifests map[string]string, dataDev string) string {
	var b strings.Builder
	b.WriteString("%post --interpreter=/bin/bash\n")
	b.WriteString("set -x\n")
	// root 密码 + sshd
	b.WriteString("echo \"root:" + cfg.OS.Password + "\" | chpasswd\n")
	b.WriteString("passwd -u root 2>/dev/null || true\n")
	b.WriteString("mkdir -p /etc/ssh/sshd_config.d\ncat > /etc/ssh/sshd_config.d/00-vdi-root-login.conf <<'SSHD'\nPermitRootLogin yes\nPasswordAuthentication yes\nSSHD\n")
	b.WriteString("sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin yes/g' /etc/ssh/sshd_config || true\n")
	b.WriteString("sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication yes/g' /etc/ssh/sshd_config || true\n")
	b.WriteString("systemctl enable sshd 2>/dev/null || ln -sf /usr/lib/systemd/system/sshd.service /etc/systemd/system/multi-user.target.wants/sshd.service\n")

	// 数据盘处理 (MVP4)：dataDev 由 detectInstallAndDataDisk 在 %pre 阶段用 Go 读
	// /sys/block/* 探测得到（含用户显式指定），作为字面量嵌入 %post，不再依赖 lsblk。
	dataDiskPath := ""
	if dataDev != "" {
		dataDiskPath = "/dev/" + dataDev
	}
	b.WriteString(fmt.Sprintf(`
# ----------------- 数据盘处理 (MVP4) -----------------
DATA_DISK="%s"

if [ -n "${DATA_DISK}" ] && [ -b "${DATA_DISK}" ]; then
    echo "发现数据盘 ${DATA_DISK}，正在对其执行 ext4 格式化与 Longhorn 卷标处理..."
    mkfs.ext4 -F -L VDI_LH_DEFAULT "${DATA_DISK}"
    mkdir -p /var/lib/longhorn
    echo "LABEL=VDI_LH_DEFAULT /var/lib/longhorn ext4 defaults,noatime,nofail 0 2" >> /etc/fstab
fi
`, dataDiskPath))

	// 解压 RKE2 二进制
	b.WriteString("tar xzf /tmp/rke2.tar.gz -C /usr/local\nrm -f /tmp/rke2.tar.gz\nchmod +x /usr/local/bin/rke2\n")
	// RKE2 config（heredoc，引用变量需转义避免 shell 展开）
	b.WriteString("mkdir -p /etc/rancher/rke2\ncat > /etc/rancher/rke2/config.yaml <<'RKE2CFG'\n")
	b.WriteString(rke2Cfg)
	b.WriteString("\nRKE2CFG\n")
	// 首节点写 HelmChart manifests
	if cfg.Install.Role == RoleFirst {
		b.WriteString("mkdir -p /var/lib/rancher/rke2/server/manifests\n")
		for name, content := range manifests {
			b.WriteString(fmt.Sprintf("cat > /var/lib/rancher/rke2/server/manifests/%s <<'MANIFEST'\n%s\nMANIFEST\n", name, content))
		}
	}
	// enable rke2-server（首节点/Master控制平面）或 rke2-agent（Worker/Witness工作节点）
	service := "rke2-server"
	if cfg.Install.Role == RoleWorker || cfg.Install.Role == RoleWitness {
		service = "rke2-agent"
	} else if cfg.Install.Role == "" && cfg.ServerURL != "" {
		service = "rke2-agent"
	}
	b.WriteString(fmt.Sprintf("systemctl enable %s 2>/dev/null || ln -sf /usr/local/lib/systemd/system/%s.service /etc/systemd/system/multi-user.target.wants/%s.service\n", service, service, service))
	b.WriteString("%end\n")
	return b.String()
}
