package console

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"syscall"

	"vdi-installer/pkg/config"
	"vdi-installer/pkg/version"
)

// AutoInstall bypasses TUI and directly calls doInstall with a default config.
// For automated testing in qemu (no TTY interaction needed).
func AutoInstall() error {
	cfg := config.NewVDIConfig()
	cfg.Install.Role = config.RoleFirst
	cfg.Install.Mode = config.ModeCreate
	cfg.Install.Device = "/dev/vda"
	cfg.Install.PersistentPartitionSize = "150Gi"
	cfg.Install.SkipChecks = true
	cfg.OS.Hostname = "vdi-node1"
	cfg.OS.Password = "vdi123"
	cfg.Token = "vdi123"
	cfg.Install.Vip = "10.0.2.100"
	cfg.Install.ManagementInterface = config.Network{
		Interfaces: []config.NetworkInterface{{Name: "enp0s2"}},
		Method:     config.NetworkMethodDHCP,
	}

	// Generate elemental config
	cosConfig, err := config.ConvertToCOS(cfg)
	if err != nil {
		return fmt.Errorf("ConvertToCOS: %w", err)
	}
	cosConfigFile, err := saveTemp(cosConfig, "cos")
	if err != nil {
		return fmt.Errorf("save cos config: %w", err)
	}

	hvstConfigFile, err := saveTemp(cfg, "vdi")
	if err != nil {
		return fmt.Errorf("save vdi config: %w", err)
	}

	cfg.Install.ConfigURL = cosConfigFile
	elementalConfig, err := config.ConvertToElementalConfig(cfg)
	if err != nil {
		return fmt.Errorf("ConvertToElementalConfig: %w", err)
	}

	elementalConfig = config.CreateRootPartitioningLayoutSeparateDataDisk(elementalConfig)

	elementalConfigDir, elementalConfigFile, err := saveElementalConfig(elementalConfig)
	if err != nil {
		return fmt.Errorf("save elemental config: %w", err)
	}

	env := append(os.Environ(),
		fmt.Sprintf("HARVESTER_CONFIG=%s", hvstConfigFile),
		fmt.Sprintf("HARVESTER_INSTALLATION_LOG=%s", defaultLogFilePath),
		fmt.Sprintf("ELEMENTAL_CONFIG=%s", elementalConfigFile),
		fmt.Sprintf("ELEMENTAL_CONFIG_DIR=%s", elementalConfigDir),
	)

	// Render RKE2 config
	rke2ConfigContent, err := config.RenderRKE2Config(cfg)
	if err != nil {
		return fmt.Errorf("render RKE2 config: %w", err)
	}
	rke2ConfigFile, err := os.CreateTemp("/tmp", "rke2-config.")
	if err != nil {
		return fmt.Errorf("create RKE2 config temp file: %w", err)
	}
	if _, err := rke2ConfigFile.WriteString(rke2ConfigContent); err != nil {
		rke2ConfigFile.Close()
		return fmt.Errorf("write RKE2 config: %w", err)
	}
	rke2ConfigFile.Close()
	env = append(env, fmt.Sprintf("VDI_RKE2_CONFIG=%s", rke2ConfigFile.Name()))

	// Render manifests
	manifests, err := config.RenderRKE2Manifests(cfg)
	if err != nil {
		return fmt.Errorf("render RKE2 manifests: %w", err)
	}
	manifestsDir, err := os.MkdirTemp("/tmp", "rke2-manifests.")
	if err != nil {
		return fmt.Errorf("create RKE2 manifests temp dir: %w", err)
	}
	for name, content := range manifests {
		if err := os.WriteFile(manifestsDir+"/"+name, []byte(content), 0644); err != nil {
			return fmt.Errorf("write RKE2 manifest %s: %w", name, err)
		}
	}
	env = append(env, fmt.Sprintf("VDI_RKE2_MANIFESTS_DIR=%s", manifestsDir))

	// Execute vdi-install
	fmt.Println("Starting vdi-install...")
	installCmd := exec.CommandContext(context.TODO(), "/usr/sbin/vdi-install")
	installCmd.Env = env
	installCmd.Stdin = os.Stdin
	installCmd.Stdout = os.Stdout
	installCmd.Stderr = os.Stderr
	installCmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	return installCmd.Run()
}

// Ensure version package is referenced
var _ = version.Version
