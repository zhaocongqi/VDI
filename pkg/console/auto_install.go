package console

import (
	"fmt"
	"os"

	"vdi-installer/pkg/config"
	"vdi-installer/pkg/version"
)

// AutoInstall renders a kickstart ks.cfg from a default VDIConfig and writes it
// to KSOutPath (default /tmp/ks-rendered.cfg), then exits.
//
// kickstart 链路下，vdi-installer 不再 exec elemental/vdi-install 落地，而是把
// VDIConfig 渲染成 ks.cfg，供 package-vdi-iso 构建期嵌入 ISO（静态 ks）或 %pre
// 动态生成（MVP3b）。anaconda 按 ks 装机 + %post 装 RKE2。
//
// 默认配置面向 qemu 自动化验证（首节点/DHCP/单盘）。TUI 模式（RunConsole）收集
// 用户配置后同样调 config.KickstartRender 渲染。
func AutoInstall(ksOutPath string) error {
	cfg := defaultQemuConfig()

	ks, err := config.KickstartRender(cfg)
	if err != nil {
		return fmt.Errorf("render kickstart: %w", err)
	}

	if ksOutPath == "" {
		ksOutPath = "/tmp/ks-rendered.cfg"
	}
	if err := os.WriteFile(ksOutPath, []byte(ks), 0644); err != nil {
		return fmt.Errorf("write ks to %s: %w", ksOutPath, err)
	}
	fmt.Printf("kickstart 渲染完成: %s (%d 行)\n", ksOutPath, len(splitLines(ks)))
	return nil
}

// defaultQemuConfig 是 qemu --auto-install 验证用的默认 VDIConfig（首节点单机）
func defaultQemuConfig() *config.VDIConfig {
	cfg := config.NewVDIConfig()
	cfg.Install.Role = config.RoleFirst
	cfg.Install.Mode = config.ModeCreate
	cfg.Install.Device = "/dev/vda"
	cfg.Install.SkipChecks = true
	cfg.OS.Hostname = "vdi-node1"
	cfg.OS.Password = "vdi123"
	cfg.Token = "vdi123"
	cfg.Install.Vip = "10.0.2.100"
	// 集群网络默认值（对齐 cos.go setConfigDefaultValues，避免 rke2 config 空值）
	cfg.Install.ClusterPodCIDR = "10.52.0.0/16"
	cfg.Install.ClusterServiceCIDR = "10.53.0.0/16"
	cfg.Install.ClusterDNS = "10.53.0.10"
	cfg.Install.ManagementInterface = config.Network{
		Interfaces: []config.NetworkInterface{{Name: "enp0s2"}},
		Method:     config.NetworkMethodDHCP,
	}
	return cfg
}

func splitLines(s string) []string {
	var lines []string
	start := 0
	for i, c := range s {
		if c == '\n' {
			lines = append(lines, s[start:i])
			start = i + 1
		}
	}
	if start < len(s) {
		lines = append(lines, s[start:])
	}
	return lines
}

// Ensure version package is referenced
var _ = version.Version
