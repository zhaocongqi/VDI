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
	DefaultCosOemSizeMiB        = 512
	DefaultCosStateSizeMiB      = 49152 // 容纳 active.img(20G) + passive.img(20G) = 40G + 余量
	DefaultCosRecoverySizeMiB   = 24576 // > active.img(20G)，recovery.img 复制 active.img 需更大
	DefaultSystemImageSizeMiB   = 20480 // active.img 的 ext2 大小，容纳 rootfs+RKE2二进制+containerd全量镜像blob+余量
	PersistentSizeMinGiB        = 50
)

// Default persistent partition percentage
const DefaultPersistentPercentageNum = 0.3
