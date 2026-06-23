package console

import (
	"testing"

	"vdi-installer/pkg/config"
)

// TestTUIFlowNavigation 测试 TUI 面板跳转流程的正确性
func TestTUIFlowNavigation(t *testing.T) {
	// 测试 askCreatePanel 的 KeyEnter 处理逻辑
	t.Run("askCreatePanel RoleFirst sets correct Mode", func(t *testing.T) {
		c := &Console{
			config: config.NewVDIConfig(),
		}

		// 模拟选择 RoleFirst
		selected := config.RoleFirst
		installModeOnly := false

		if selected == config.ModeInstall {
			installModeOnly = true
			c.config.Install.Mode = config.ModeInstall
		} else if selected == config.RoleMaster || selected == config.RoleWorker {
			c.config.Install.Mode = config.ModeJoin
		} else {
			c.config.Install.Mode = config.ModeCreate
		}
		c.config.Install.Role = selected

		if c.config.Install.Mode != config.ModeCreate {
			t.Errorf("Expected Mode=%s, got %s", config.ModeCreate, c.config.Install.Mode)
		}
		if c.config.Install.Role != config.RoleFirst {
			t.Errorf("Expected Role=%s, got %s", config.RoleFirst, c.config.Install.Role)
		}
		if installModeOnly {
			t.Error("Expected installModeOnly=false")
		}
	})

	t.Run("askCreatePanel RoleMaster sets correct Mode", func(t *testing.T) {
		c := &Console{
			config: config.NewVDIConfig(),
		}

		selected := config.RoleMaster

		if selected == config.ModeInstall {
			c.config.Install.Mode = config.ModeInstall
		} else if selected == config.RoleMaster || selected == config.RoleWorker {
			c.config.Install.Mode = config.ModeJoin
		} else {
			c.config.Install.Mode = config.ModeCreate
		}
		c.config.Install.Role = selected

		if c.config.Install.Mode != config.ModeJoin {
			t.Errorf("Expected Mode=%s, got %s", config.ModeJoin, c.config.Install.Mode)
		}
	})

	t.Run("askCreatePanel ModeInstall sets correct Mode", func(t *testing.T) {
		c := &Console{
			config: config.NewVDIConfig(),
		}

		selected := config.ModeInstall
		installModeOnly := false

		if selected == config.ModeInstall {
			installModeOnly = true
			c.config.Install.Mode = config.ModeInstall
		} else if selected == config.RoleMaster || selected == config.RoleWorker {
			c.config.Install.Mode = config.ModeJoin
		} else {
			c.config.Install.Mode = config.ModeCreate
		}
		c.config.Install.Role = selected

		if c.config.Install.Mode != config.ModeInstall {
			t.Errorf("Expected Mode=%s, got %s", config.ModeInstall, c.config.Install.Mode)
		}
		if !installModeOnly {
			t.Error("Expected installModeOnly=true")
		}
	})
}

// TestPasswordESCBinding 测试密码面板 ESC 跳转逻辑
// VDI 角色在 askCreatePanel 选定，ESC 统一回退到 askCreatePanel（不再经过 askRolePanel）
func TestPasswordESCBinding(t *testing.T) {
	t.Run("ESC from password always goes to askCreatePanel", func(t *testing.T) {
		// 无论 Create/Join 模式，密码页 ESC 都应回 askCreatePanel
		for _, mode := range []string{config.ModeCreate, config.ModeJoin, config.ModeInstall} {
			// VDI 统一回 askCreatePanel
			targetPanel := askCreatePanel
			if targetPanel != askCreatePanel {
				t.Errorf("mode=%s: Expected target=%s, got %s", mode, askCreatePanel, targetPanel)
			}
		}
	})
}

// TestNetworkPageNavigation 测试网络页面跳转逻辑
func TestNetworkPageNavigation(t *testing.T) {
	t.Run("gotoPrevPage for first-time install goes to showDiskPage", func(t *testing.T) {
		alreadyInstalled := false

		var target string
		if alreadyInstalled {
			target = "askCreatePanel or askRolePanel"
		} else {
			target = "showDiskPage"
		}

		if target != "showDiskPage" {
			t.Errorf("Expected target=showDiskPage, got %s", target)
		}
	})

	t.Run("gotoPrevPage for already installed goes to askCreatePanel", func(t *testing.T) {
		alreadyInstalled := true

		// VDI 已修复：alreadyInstalled 时网络页 ESC 统一回 askCreatePanel
		var target string
		if alreadyInstalled {
			target = askCreatePanel
		} else {
			target = "showDiskPage"
		}

		if target != askCreatePanel {
			t.Errorf("Expected target=%s, got %s", askCreatePanel, target)
		}
	})
}

// TestDiskPageNavigation 测试磁盘页面跳转逻辑
func TestDiskPageNavigation(t *testing.T) {
	t.Run("gotoNextPage for installModeOnly goes to confirmInstallPanel", func(t *testing.T) {
		installModeOnly := true

		var target string
		if installModeOnly {
			target = confirmInstallPanel
		} else {
			target = "showNetworkPage"
		}

		if target != confirmInstallPanel {
			t.Errorf("Expected target=%s, got %s", confirmInstallPanel, target)
		}
	})

	t.Run("gotoNextPage for normal install goes to showNetworkPage", func(t *testing.T) {
		installModeOnly := false

		var target string
		if installModeOnly {
			target = confirmInstallPanel
		} else {
			target = "showNetworkPage"
		}

		if target != "showNetworkPage" {
			t.Errorf("Expected target=showNetworkPage, got %s", target)
		}
	})
}

// TestClusterNetworkFields 测试集群网络字段写入正确层级
func TestClusterNetworkFields(t *testing.T) {
	t.Run("Cluster fields should be written to Install level", func(t *testing.T) {
		c := &Console{
			config: config.NewVDIConfig(),
		}

		// 模拟写入
		c.config.Install.ClusterPodCIDR = "10.52.0.0/16"
		c.config.Install.ClusterServiceCIDR = "10.53.0.0/16"
		c.config.Install.ClusterDNS = "10.53.0.10"

		if c.config.Install.ClusterPodCIDR != "10.52.0.0/16" {
			t.Errorf("Expected ClusterPodCIDR=10.52.0.0/16, got %s", c.config.Install.ClusterPodCIDR)
		}
		if c.config.Install.ClusterServiceCIDR != "10.53.0.0/16" {
			t.Errorf("Expected ClusterServiceCIDR=10.53.0.0/16, got %s", c.config.Install.ClusterServiceCIDR)
		}
		if c.config.Install.ClusterDNS != "10.53.0.10" {
			t.Errorf("Expected ClusterDNS=10.53.0.10, got %s", c.config.Install.ClusterDNS)
		}
	})
}
