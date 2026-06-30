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

	"github.com/sirupsen/logrus"
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



// RenderRKE2Config 渲染 RKE2 config（server 或 agent，按 ServerURL 判断），供 vdi-install 写盘
// VDI 无 elemental cloud-init 触发层（harvester 由 SUSE MicroOS elemental-init 提供），
// initRKE2Stage 的 initramfs stage 首启不会执行，需 vdi-install 安装时直接写 config.yaml
func RenderRKE2Config(config *VDIConfig) (string, error) {
	isAgent := config.Install.Role == RoleWorker || config.Install.Role == RoleWitness
	if config.Install.Role == "" && config.ServerURL != "" {
		isAgent = true
	}

	if !isAgent {
		rke2Config, err := render("rke2-server.yaml", config)
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(rke2Config), nil
	}

	rke2Config, err := render("rke2-agent.yaml", config)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(rke2Config), nil
}

// RenderRKE2Manifests 渲染首节点 HelmChart manifests（kube-ovn/longhorn/kubevirt/kagent），
// 供 vdi-install 写到 /var/lib/rancher/rke2/server/manifests/
// VDI 无 elemental cloud-init 触发层，initRKE2Stage 的 manifests 首启不会写，需 vdi-install 直接写
func RenderRKE2Manifests(config *VDIConfig) (map[string]string, error) {
	return genBootstrapResources(config)
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


