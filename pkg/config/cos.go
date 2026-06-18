package config

import (
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"

	yipSchema "github.com/rancher/yip/pkg/schema"
	"github.com/sirupsen/logrus"
	"gopkg.in/yaml.v3"

	"vdi-installer/pkg/util"
)

var (
	// Allows overriding for tests
	NMConnectionPath = "/etc/NetworkManager/system-connections"
)

const (
	NMConnectionGlobPattern = "*nmconnection"
)

const (
	cosLoginUser        = "rancher"
	ntpdService         = "systemd-timesyncd"
	timeWaitSyncService = "systemd-time-wait-sync"

	rke2ConfigDir    = "/etc/rancher/rke2"
	rke2ManifestsDir = "/var/lib/rancher/rke2/server/manifests"
)

var (
	originalNetworkConfigs        = make(map[string][]byte)
	saveOriginalNetworkConfigOnce sync.Once
)

// refer: https://github.com/rancher/elemental-cli/blob/v0.1.0/config.yaml.example
type ElementalConfig struct {
	Install ElementalInstallSpec `yaml:"install,omitempty"`
}

type ElementalInstallSpec struct {
	Target          string                     `yaml:"target,omitempty"`
	Firmware        string                     `yaml:"firmware,omitempty"`
	PartTable       string                     `yaml:"part-table,omitempty"`
	Partitions      *ElementalDefaultPartition `yaml:"partitions,omitempty"`
	ExtraPartitions []ElementalPartition       `yaml:"extra-partitions,omitempty"`
	CloudInit       string                     `yaml:"cloud-init,omitempty"`
	Tty             string                     `yaml:"tty,omitempty"`
	System          *ElementalSystem           `yaml:"system,omitempty"`
}

type ElementalSystem struct {
	Label string `yaml:"label,omitempty"`
	Size  uint   `yaml:"size,omitempty"`
	FS    string `yaml:"fs,omitempty"`
	URI   string `yaml:"uri,omitempty"`
}

type ElementalDefaultPartition struct {
	OEM        *ElementalPartition `yaml:"oem,omitempty"`
	State      *ElementalPartition `yaml:"state,omitempty"`
	Recovery   *ElementalPartition `yaml:"recovery,omitempty"`
	Persistent *ElementalPartition `yaml:"persistent,omitempty"`
}

type ElementalPartition struct {
	FilesystemLabel string `yaml:"label,omitempty"`
	Size            uint   `yaml:"size,omitempty"`
	FS              string `yaml:"fs,omitempty"`
}

func NewElementalConfig() *ElementalConfig {
	return &ElementalConfig{}
}

func ConvertToElementalConfig(config *VDIConfig) (*ElementalConfig, error) {
	elementalConfig := NewElementalConfig()

	if config.Install.ForceEFI {
		elementalConfig.Install.Firmware = "efi"
	}

	elementalConfig.Install.PartTable = "gpt"
	if !config.Install.ForceGPT {
		elementalConfig.Install.PartTable = "msdos"
	}

	resolvedDevPath, err := filepath.EvalSymlinks(config.Install.Device)
	if err != nil {
		return nil, err
	}
	elementalConfig.Install.Target = resolvedDevPath
	elementalConfig.Install.CloudInit = config.Install.ConfigURL
	elementalConfig.Install.Tty = config.Install.TTY

	return elementalConfig, nil
}

// ConvertToCOS converts VDIConfig to cOS configuration.
func ConvertToCOS(config *VDIConfig) (*yipSchema.YipConfig, error) {
	cfg, err := config.DeepCopy()
	if err != nil {
		return nil, err
	}

	// Overwrite rootfs layout
	rootfs := yipSchema.Stage{}
	if err := overwriteRootfsStage(config, &rootfs); err != nil {
		return nil, err
	}

	initramfs := yipSchema.Stage{
		Users:     make(map[string]yipSchema.User),
		TimeSyncd: make(map[string]string),
	}

	afterNetwork := yipSchema.Stage{
		Hostname: config.OS.Hostname,
		SSHKeys:  make(map[string][]string),
	}

	initramfs.Users[cosLoginUser] = yipSchema.User{
		PasswordHash: cfg.OS.Password,
	}

	// Use modprobe to load modules as a temporary solution
	for _, module := range cfg.OS.Modules {
		initramfs.Commands = append(initramfs.Commands, "modprobe "+module)
	}
	// Delete the cpu_manager_state file during the initramfs stage. During a reboot, this state file is always reverted
	// because it was originally created during the system installation, becoming part of the root filesystem.
	// As a result, the policy in cpu_manager_state file is "none" (default policy) after reboot. If we've already set
	// the cpu-manager-policy to "static" before reboot, this mismatch can prevent kubelet from starting,
	// and make the entire node unavailable.
	initramfs.Commands = append(initramfs.Commands, "rm -f /var/lib/kubelet/cpu_manager_state")

	initramfs.Sysctl = cfg.OS.Sysctls
	initramfs.Environment = cfg.OS.Environment

	// OS
	for _, ff := range cfg.OS.WriteFiles {
		perm, err := strconv.ParseUint(ff.RawFilePermissions, 8, 32)
		if err != nil {
			logrus.Warnf("fail to parse permission %s, use default permission.", err)
			perm = 0600
		}
		initramfs.Files = append(initramfs.Files, yipSchema.File{
			Path:        ff.Path,
			Content:     ff.Content,
			Encoding:    ff.Encoding,
			Permissions: uint32(perm),
			OwnerString: ff.Owner,
		})
	}

	// write a persistent sysctl drop-in and apply at runtime; persists after reboot
	initramfs.Directories = append(initramfs.Directories, yipSchema.Directory{
		Path:        "/etc/sysctl.d",
		Permissions: 0755,
		Owner:       0,
		Group:       0,
	})
	initramfs.Files = append(initramfs.Files, yipSchema.File{
		Path: "/etc/sysctl.d/zz-harvester-enable-ipv6.conf",
		Content: fmt.Sprintf("# Written by harvester-installer: overrides /etc/sysctl.d/ipv6.conf\n%s = 0\n%s = 0\n%s = 0\n",
			SysctlDisableIPv6All, SysctlDisableIPv6Default, SysctlDisableIPv6Lo),
		Permissions: 0644,
		Owner:       0,
		Group:       0,
	})
	if initramfs.Sysctl == nil {
		initramfs.Sysctl = make(map[string]string)
	}
	initramfs.Sysctl[SysctlDisableIPv6All] = "0"
	initramfs.Sysctl[SysctlDisableIPv6Default] = "0"
	initramfs.Sysctl[SysctlDisableIPv6Lo] = "0"

	// TOP
	if cfg.Install.Mode != ModeInstall {
		if err := initRKE2Stage(config, &initramfs); err != nil {
			return nil, err
		}

		initramfs.Hostname = cfg.OS.Hostname

		if len(cfg.OS.NTPServers) > 0 {
			initramfs.TimeSyncd["NTP"] = strings.Join(cfg.OS.NTPServers, " ")
			initramfs.Systemctl.Enable = append(initramfs.Systemctl.Enable, ntpdService)
			initramfs.Systemctl.Enable = append(initramfs.Systemctl.Enable, timeWaitSyncService)
		}

		err = UpdateManagementInterfaceConfig(cfg.ManagementInterface, cfg.OS.DNSNameservers, NMConnectionPath, false)
		if err != nil {
			return nil, err
		}

		afterNetwork.SSHKeys[cosLoginUser] = cfg.OS.SSHAuthorizedKeys
	}

	cosConfig := &yipSchema.YipConfig{
		Name: "VDI Configuration",
		Stages: map[string][]yipSchema.Stage{
			"rootfs":    {rootfs},
			"initramfs": {initramfs},
			"network":   {afterNetwork},
		},
	}

	// Add after-install-chroot stage
	if len(config.OS.AfterInstallChrootCommands) > 0 {
		afterInstallChroot := yipSchema.Stage{}
		if err := overwriteAfterInstallChrootStage(config, &afterInstallChroot); err != nil {
			return nil, err
		}
		cosConfig.Stages["after-install-chroot"] = []yipSchema.Stage{afterInstallChroot}
	}

	return cosConfig, nil
}

func overwriteAfterInstallChrootStage(config *VDIConfig, stage *yipSchema.Stage) error {
	content, err := render("cos-after-install-chroot.yaml", config)
	if err != nil {
		return err
	}

	return yaml.Unmarshal([]byte(content), stage)
}

func overwriteRootfsStage(config *VDIConfig, stage *yipSchema.Stage) error {
	content, err := render("cos-rootfs.yaml", config)
	if err != nil {
		return err
	}

	if err := yaml.Unmarshal([]byte(content), stage); err != nil {
		return err
	}

	return nil
}

func setConfigDefaultValues(config *VDIConfig) {
	if config.RKE2Version == "" {
		config.RKE2Version = RKE2Version
	}
}

// initRKE2Stage generates RKE2 config files and HelmChart manifests for the node.
func initRKE2Stage(config *VDIConfig, stage *yipSchema.Stage) error {
	setConfigDefaultValues(config)

	// Ensure RKE2 config directory exists
	stage.Directories = append(stage.Directories,
		yipSchema.Directory{
			Path:        rke2ConfigDir,
			Permissions: 0700,
			Owner:       0,
			Group:       0,
		})

	// Render and write RKE2 config (server or agent)
	if config.ServerURL == "" {
		// First node: render server config
		rke2Config, err := render("rke2-server.yaml", config)
		if err != nil {
			return err
		}
		stage.Files = append(stage.Files,
			yipSchema.File{
				Path:        filepath.Join(rke2ConfigDir, "config.yaml"),
				Content:     rke2Config,
				Permissions: 0600,
				Owner:       0,
				Group:       0,
			},
		)

		// Generate HelmChart manifests for the first node
		if config.Install.Role == RoleFirst {
			helmcharts, err := genBootstrapResources(config)
			if err != nil {
				return err
			}
			for fileName, fileContent := range helmcharts {
				stage.Files = append(stage.Files,
					yipSchema.File{
						Path:        filepath.Join(rke2ManifestsDir, fileName),
						Content:     fileContent,
						Permissions: 0644,
						Owner:       0,
						Group:       0,
					},
				)
			}
		}
	} else {
		// Join node: render agent config
		rke2Config, err := render("rke2-agent.yaml", config)
		if err != nil {
			return err
		}
		rke2Config = strings.TrimSpace(rke2Config)
		stage.Files = append(stage.Files,
			yipSchema.File{
				Path:        filepath.Join(rke2ConfigDir, "config.yaml"),
				Content:     rke2Config,
				Permissions: 0600,
				Owner:       0,
				Group:       0,
			},
		)
	}

	return nil
}

func wipeNMConnectionProfiles(configPath string) error {
	paths, err := filepath.Glob(fmt.Sprintf("%s/%s", configPath, NMConnectionGlobPattern))
	if err != nil {
		return err
	}
	for _, path := range paths {
		if err := os.Remove(path); err != nil {
			return err
		}
	}
	return nil
}

// RestoreOriginalNetworkConfig restores the previous state of network
// configurations saved by `SaveOriginalNetworkConfig`.
func RestoreOriginalNetworkConfig() error {
	if len(originalNetworkConfigs) == 0 {
		return nil
	}

	if err := wipeNMConnectionProfiles(NMConnectionPath); err != nil {
		return err
	}

	for name, bytes := range originalNetworkConfigs {
		if err := os.WriteFile(name, bytes, os.FileMode(0600)); err != nil {
			return err
		}
	}
	return nil
}

// SaveOriginalNetworkConfig saves the current state of network configurations.
// It can only be invoked once for the whole lifetime of this program.
func SaveOriginalNetworkConfig() error {
	var err error

	saveOriginalNetworkConfigOnce.Do(func() {
		save := func(pattern string) error {
			filepaths, err := filepath.Glob(pattern)
			if err != nil {
				return err
			}
			for _, path := range filepaths {
				bytes, err := os.ReadFile(path) //nolint:gosec
				if err != nil {
					return err
				}
				originalNetworkConfigs[path] = bytes

			}
			return nil
		}

		err = save(fmt.Sprintf("%s/%s", NMConnectionPath, NMConnectionGlobPattern))
	})

	return err
}

// UpdateManagementInterfaceConfig generates NetworkManager connection profiles.
// It restarts networking and waits for the connection to be up if applyConfig is true.
func UpdateManagementInterfaceConfig(mgmtInterface Network, dnsNameServers []string, configPath string, applyConfig bool) error {
	if len(mgmtInterface.Interfaces) == 0 {
		return errors.New("no slave defined for management network bond")
	}

	switch mgmtInterface.Method {
	case NetworkMethodDHCP, NetworkMethodStatic, NetworkMethodNone:
	default:
		return fmt.Errorf("unsupported network method %s", mgmtInterface.Method)
	}

	// Just in case path doesn't exist (e.g. when run from installer binary during upgrade)
	if err := os.MkdirAll(configPath, 0755); err != nil {
		return err
	}
	// If there's any existing profiles, we need to remove them before creating new ones
	if err := wipeNMConnectionProfiles(configPath); err != nil {
		return err
	}

	bondMgmt := Network{
		Interfaces:  mgmtInterface.Interfaces,
		Method:      NetworkMethodNone,
		BondOptions: mgmtInterface.BondOptions,
		MTU:         mgmtInterface.MTU,
		VlanID:      mgmtInterface.VlanID,
	}

	if err := updateBond(MgmtBondInterfaceName, &bondMgmt, configPath); err != nil {
		return err
	}

	if err := updateBridge(MgmtInterfaceName, &mgmtInterface, dnsNameServers, configPath); err != nil {
		return err
	}

	if applyConfig && !testing.Testing() {
		// We need to turn networking off first, in order to bring down any
		// existing interfaces, before reloading the updated connections.
		// Then we can start networking again.  If we don't turn networking
		// off first, and only reload connections, then it's possible if the
		// user selected a static IP in the installer, then went back and
		// changed to DHCP, that the static IP would still be up.
		output, err := exec.Command("nmcli", "networking", "off").CombinedOutput()
		if err != nil {
			logrus.Error(err, string(output))
			return err
		}
		output, err = exec.Command("nmcli", "connection", "reload").CombinedOutput()
		if err != nil {
			logrus.Error(err, string(output))
			return err
		}
		output, err = exec.Command("nmcli", "networking", "on").CombinedOutput()
		if err != nil {
			logrus.Error(err, string(output))
			return err
		}
		// This next command waits up to 30 seconds to ensure there's
		// a connection.  Without this, it's possible that a slow DHCP
		// server won't return in time, and the installer will subsequently
		// fail the check for a default route.
		output, err = exec.Command("nm-online", "-x").CombinedOutput()
		if err != nil {
			logrus.Error(err, string(output))
			return err
		}
	}

	return nil
}

func updateBond(name string, network *Network, configPath string) error {
	// Adding default NIC bonding options if no options are provided (usually happened under PXE
	// installation). Missing them would make bonding interfaces unusable.
	if network.BondOptions == nil {
		logrus.Infof("Adding default NIC bonding options for \"%s\"", name)
		network.BondOptions = map[string]string{
			"mode":   BondModeActiveBackup,
			"miimon": "100",
		}
	}

	bondData := map[string]interface{}{
		"Bond":       network,
		"BondName":   MgmtBondInterfaceName,
		"BridgeName": MgmtInterfaceName,
	}

	nmcon, err := render("nm-bond-master.nmconnection", bondData)
	if err != nil {
		return err
	}

	// bond master
	if err := os.WriteFile(fmt.Sprintf("%s/bond-mgmt.nmconnection", configPath), []byte(nmcon), 0600); err != nil {
		return err
	}

	// bond slaves
	for _, iface := range network.Interfaces {
		ifaceData := map[string]interface{}{
			"Iface":    iface,
			"BondName": MgmtBondInterfaceName,
		}
		nmcon, err := render("nm-bond-slave.nmconnection", ifaceData)
		if err != nil {
			return err
		}
		if err := os.WriteFile(fmt.Sprintf("%s/bond-slave-%s.nmconnection", configPath, iface.Name), []byte(nmcon), 0600); err != nil {
			return err
		}
	}

	return nil
}

func updateBridge(name string, mgmtNetwork *Network, dnsNameServers []string, configPath string) error {
	// add Bridge named MgmtInterfaceName and attach Bond named MgmtBondInterfaceName to bridge

	// pvid is always 1, if vlan id is 1, it means untagged vlan.
	needVlanInterface := mgmtNetwork.VlanID >= 2 && mgmtNetwork.VlanID <= 4094

	bridgeMgmt := Network{
		Interfaces:   mgmtNetwork.Interfaces,
		Method:       mgmtNetwork.Method,
		IP:           mgmtNetwork.IP,
		SubnetMask:   mgmtNetwork.SubnetMask,
		Gateway:      mgmtNetwork.Gateway,
		DefaultRoute: !needVlanInterface,
		MTU:          mgmtNetwork.MTU,
		VlanID:       mgmtNetwork.VlanID,
	}

	maskToCIDR := func(mask string) (cidr string) {
		// If set, mask is guaranteed to be valid at this point
		if mask != "" {
			ones, _ := net.IPMask(net.ParseIP(mask).To4()).Size()
			cidr = strconv.Itoa(ones)
		}
		return
	}

	// NetworkManager config needs CIDRs
	bridgeMgmt.SubnetMask = maskToCIDR(bridgeMgmt.SubnetMask)

	if needVlanInterface {
		bridgeMgmt.Method = NetworkMethodNone
	}
	// add bridge
	bridgeData := map[string]interface{}{
		"Bridge":     bridgeMgmt,
		"BridgeName": MgmtInterfaceName,
		"DNSServers": "",
	}
	if !needVlanInterface && len(dnsNameServers) > 0 {
		bridgeData["DNSServers"] = strings.Join(dnsNameServers, ";") + ";"
	}
	var nmcon string
	nmcon, err := render("nm-bridge.nmconnection", bridgeData)
	if err != nil {
		return err
	}
	if err := os.WriteFile(fmt.Sprintf("%s/bridge-mgmt.nmconnection", configPath), []byte(nmcon), 0600); err != nil {
		return err
	}

	// add vlan interface
	if needVlanInterface {
		vlanMgmt := *mgmtNetwork // Copy mgmtNetwork so we don't mess with it
		vlanMgmt.DefaultRoute = true
		vlanMgmt.SubnetMask = maskToCIDR(vlanMgmt.SubnetMask)

		vlanData := map[string]interface{}{
			"BridgeName": name,
			"Vlan":       vlanMgmt,
			"DNSServers": "",
		}
		if len(dnsNameServers) > 0 {
			vlanData["DNSServers"] = strings.Join(dnsNameServers, ";") + ";"
		}
		nmcon, err = render("nm-vlan.nmconnection", vlanData)
		if err != nil {
			return err
		}
		if err := os.WriteFile(fmt.Sprintf("%s/vlan-mgmt.nmconnection", configPath), []byte(nmcon), 0600); err != nil {
			return err
		}
	}

	return nil
}

func (c *VDIConfig) ToCosInstallEnv() ([]string, error) {
	return ToEnv("VDI_", c.Install)
}

// genBootstrapResources generates HelmChart manifests for the first node.
// map: fileName -> fileContent
func genBootstrapResources(config *VDIConfig) (map[string]string, error) {
	helmcharts := make(map[string]string)

	templates := []string{
		"helmchart-kube-ovn.yaml",
		"helmchart-longhorn.yaml",
		"helmchart-kubevirt.yaml",
		"helmchart-kagent.yaml",
	}

	for _, templateName := range templates {
		rendered, err := render(templateName, config)
		if err != nil {
			return nil, err
		}
		helmcharts[templateName] = rendered
	}

	return helmcharts, nil
}

func calcCosPersistentPartSize(diskSizeGiB uint64, partSize string, skipChecks bool) (uint64, error) {
	size, err := util.ParsePartitionSize(util.GiToByte(diskSizeGiB), partSize, skipChecks)
	if err != nil {
		return 0, err
	}
	return util.ByteToMi(size), nil
}

func CreateRootPartitioningLayoutSeparateDataDisk(elementalConfig *ElementalConfig) *ElementalConfig {
	elementalConfig.Install.Partitions = &ElementalDefaultPartition{
		OEM: &ElementalPartition{
			FilesystemLabel: "COS_OEM",
			Size:            DefaultCosOemSizeMiB,
			FS:              "ext4",
		},
		State: &ElementalPartition{
			FilesystemLabel: "COS_STATE",
			Size:            DefaultCosStateSizeMiB,
			FS:              "ext4",
		},
		Recovery: &ElementalPartition{
			FilesystemLabel: "COS_RECOVERY",
			Size:            DefaultCosRecoverySizeMiB,
			FS:              "ext4",
		},
		Persistent: &ElementalPartition{
			FilesystemLabel: "COS_PERSISTENT",
			Size:            0,
			FS:              "ext4",
		},
	}
	return elementalConfig
}

func CreateRootPartitioningLayoutSharedDataDisk(elementalConfig *ElementalConfig, hvstConfig *VDIConfig) (*ElementalConfig, error) {
	diskSizeBytes, err := util.GetDiskSizeBytes(hvstConfig.Install.Device)
	if err != nil {
		return nil, err
	}

	persistentSize := hvstConfig.Install.PersistentPartitionSize
	if persistentSize == "" {
		persistentSize = fmt.Sprintf("%dGi", PersistentSizeMinGiB)
	}
	cosPersistentSizeMiB, err := calcCosPersistentPartSize(util.ByteToGi(diskSizeBytes), persistentSize, hvstConfig.SkipChecks)
	if err != nil {
		return nil, err
	}

	logrus.Infof("Calculated COS_PERSISTENT partition size: %d MiB", cosPersistentSizeMiB)
	elementalConfig.Install.Partitions = &ElementalDefaultPartition{
		OEM: &ElementalPartition{
			FilesystemLabel: "COS_OEM",
			Size:            DefaultCosOemSizeMiB,
			FS:              "ext4",
		},
		State: &ElementalPartition{
			FilesystemLabel: "COS_STATE",
			Size:            DefaultCosStateSizeMiB,
			FS:              "ext4",
		},
		Recovery: &ElementalPartition{
			FilesystemLabel: "COS_RECOVERY",
			Size:            DefaultCosRecoverySizeMiB,
			FS:              "ext4",
		},
		Persistent: &ElementalPartition{
			FilesystemLabel: "COS_PERSISTENT",
			Size:            uint(cosPersistentSizeMiB),
			FS:              "ext4",
		},
	}

	elementalConfig.Install.ExtraPartitions = []ElementalPartition{
		{
			FilesystemLabel: "HARV_LH_DEFAULT",
			Size:            0,
			FS:              "ext4",
		},
	}

	return elementalConfig, nil
}
