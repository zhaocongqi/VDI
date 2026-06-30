package config

// Role constants
const (
	RoleFirst   = "first"
	RoleMaster  = "master"
	RoleWorker  = "worker"
	RoleWitness = "witness"
	RoleDefault = ""
	RoleMgmt    = "management"
)

// Install mode constants
const (
	ModeCreate  = "create"
	ModeJoin    = "join"
	ModeInstall = "install"
	ModeUpgrade = "upgrade"
)

// Network interface constants
const (
	MgmtInterfaceName    = "mgmt-br"
	MgmtBondInterfaceName = "mgmt-bo"
)

// Config file paths
const (
	Rke2ConfigFile = "/etc/rancher/rke2/config.yaml"
)

// Network method constants
const (
	NetworkMethodDHCP   = "dhcp"
	NetworkMethodStatic = "static"
	NetworkMethodNone   = "none"
)

// Sysctl constants
const (
	SysctlDisableIPv6All     = "net.ipv6.conf.all.disable_ipv6"
	SysctlDisableIPv6Default = "net.ipv6.conf.default.disable_ipv6"
	SysctlDisableIPv6Lo      = "net.ipv6.conf.lo.disable_ipv6"
)

// 版本变量（通过 ldflags 注入）
var (
	RKE2Version     string
	KubevirtVersion string
	LonghornVersion string
	KubeovnVersion  string
	KagentVersion   string
)

// Partition size constants (in MiB)
const (
	PersistentSizeMinGiB = 50
)

// Default persistent partition percentage
const DefaultPersistentPercentageNum = 0.3
