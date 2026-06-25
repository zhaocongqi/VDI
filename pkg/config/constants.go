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
	RancherdConfigFile = "/etc/rancher/rancherd/config.yaml"
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
	DefaultCosStateSizeMiB      = 15360
	DefaultCosRecoverySizeMiB   = 8192
	DefaultSystemImageSizeMiB   = 6144 // active.img 的 ext2 文件系统大小，需容纳 rootfs(~2.7G) + RKE2 离线镜像(~2.3G)；recovery.img 复制 active.img，COS_RECOVERY 分区(8G)需大于此值
	PersistentSizeMinGiB        = 150
)

// Default persistent partition percentage
const DefaultPersistentPercentageNum = 0.3
