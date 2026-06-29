package config

import (
	"fmt"
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

	// 磁盘：清盘 + LVM autopart，排除数据盘以防被 Anaconda 强占或污染
	if cfg.Install.DataDisk != "" {
		dataDev := strings.TrimPrefix(cfg.Install.DataDisk, "/dev/")
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
	b.WriteString(kickstartPostChroot(cfg, rke2Cfg, manifests))

	return b.String(), nil
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
func kickstartPostChroot(cfg *VDIConfig, rke2Cfg string, manifests map[string]string) string {
	var b strings.Builder
	b.WriteString("%post --interpreter=/bin/bash\n")
	b.WriteString("set -x\n")
	// root 密码 + sshd
	b.WriteString("echo \"root:" + cfg.OS.Password + "\" | chpasswd\n")
	b.WriteString("passwd -u root 2>/dev/null || true\n")
	b.WriteString("mkdir -p /etc/ssh/sshd_config.d\ncat > /etc/ssh/sshd_config.d/00-vdi-root-login.conf <<'SSHD'\nPermitRootLogin yes\nPasswordAuthentication yes\nSSHD\n")
	b.WriteString("systemctl enable sshd 2>/dev/null || ln -sf /usr/lib/systemd/system/sshd.service /etc/systemd/system/multi-user.target.wants/sshd.service\n")

	// 数据盘处理 (MVP4)
	dev := cfg.Install.Device
	dataDev := cfg.Install.DataDisk
	b.WriteString(fmt.Sprintf(`
# ----------------- 数据盘处理 (MVP4) -----------------
SYS_DEV_NAME="%s"
DATA_DISK="%s"
if [ -z "${DATA_DISK}" ]; then
    DATA_DISK=$(lsblk -d -n -o NAME,TYPE | grep disk | awk '{print "/dev/"$1}' | grep -v -E "(${SYS_DEV_NAME}|$(basename ${SYS_DEV_NAME}))" | head -n 1)
fi

if [ -n "${DATA_DISK}" ] && [ -b "${DATA_DISK}" ]; then
    echo "发现数据盘 ${DATA_DISK}，正在对其执行 ext4 格式化与 Longhorn 卷标处理..."
    mkfs.ext4 -F -L VDI_LH_DEFAULT "${DATA_DISK}"
    mkdir -p /var/lib/longhorn
    echo "LABEL=VDI_LH_DEFAULT /var/lib/longhorn ext4 defaults,noatime,nofail 0 2" >> /etc/fstab
fi
`, dev, dataDev))

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
