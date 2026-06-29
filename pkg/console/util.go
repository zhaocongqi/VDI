package console

import (
	"bufio"
	"bytes"
	"context"
	"crypto/tls"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/jroimartin/gocui"
	"github.com/pkg/errors"
	"github.com/sirupsen/logrus"
	"golang.org/x/crypto/ssh"
	"golang.org/x/net/http/httpproxy"
	"gopkg.in/ini.v1"
	"gopkg.in/yaml.v3"
	"k8s.io/apimachinery/pkg/util/rand"

	"vdi-installer/pkg/config"
	"vdi-installer/pkg/util"
	"vdi-installer/pkg/widgets"
)

const (
	rancherManagementPort = "443"
	defaultHTTPTimeout    = 15 * time.Second
	automaticCmdline      = "vdi.automatic"
	installFailureMessage = `
** Installation Failed **
You can see the full installation log by:
  - Press CTRL + ALT + F2 to switch to a different TTY console.
  - Login with user "rancher" (password is "rancher").
  - Run the command: sudo less %s.
`
	https = "https://"

	ElementalConfigDir  = "/tmp/elemental"
	ElementalConfigFile = "config.yaml"
	multipathOff        = "multipath=off"
	PartitionType       = "part"
	MpathType           = "mpath"
	CosDiskLabelPrefix  = "COS_OEM"
)

func newProxyClient() http.Client {
	return http.Client{
		Timeout: defaultHTTPTimeout,
		Transport: &http.Transport{
			Proxy: proxyFromEnvironment,
		},
	}
}

func proxyFromEnvironment(req *http.Request) (*url.URL, error) {
	return httpproxy.FromEnvironment().ProxyFunc()(req.URL)
}

func getURL(client http.Client, url string) ([]byte, error) {
	resp, err := client.Get(url)
	if err != nil {
		return nil, err
	}

	defer resp.Body.Close() //nolint:errcheck
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 400 {
		return nil, fmt.Errorf("got %d status code from %s, body: %s", resp.StatusCode, url, string(body))
	}

	return body, nil
}

func validatePingServerURL(url string) error {
	client := http.Client{
		Timeout: defaultHTTPTimeout,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				InsecureSkipVerify: true,
			},
		},
	}
	// After configure the network, network need a few seconds to be available.
	return retryOnError(3, 2, func() error {
		_, err := getURL(client, url)
		return err
	})
}

func validateNTPServers(ntpServerList []string) error {
	for _, ntpServer := range ntpServerList {
		var err error
		host, port, err := net.SplitHostPort(ntpServer)
		if err != nil {
			if addrErr, ok := err.(*net.AddrError); ok && addrErr.Err == "missing port in address" {
				host = ntpServer
				// default ntp server port
				// RFC: https://datatracker.ietf.org/doc/html/rfc4330#section-4
				port = "123"
			} else {
				return err
			}
		}

		ips, err := net.LookupIP(host)
		if err != nil {
			return err
		}

		isSuccess := false
		ipStrings := make([]string, 0, len(ips))
		for _, ip := range ips {
			ipString := ip.String()
			ipStrings = append(ipStrings, ipString)
			logrus.Infof("try to validate NTP server %s", ipString)
			// ntp servers use udp protocol
			// RFC: https://datatracker.ietf.org/doc/html/rfc4330
			var conn net.Conn
			address := net.JoinHostPort(ipString, port)
			conn, err = net.Dial("udp", address)
			if err != nil {
				logrus.Errorf("fail to dial %s, err: %v", address, err)
				continue
			}
			defer conn.Close() //nolint:errcheck
			if err = conn.SetDeadline(time.Now().Add(5 * time.Second)); err != nil {
				logrus.Errorf("fail to set deadline for connection")
			}

			// RFC: https://datatracker.ietf.org/doc/html/rfc4330#section-4
			// NTP Packet is 48 bytes and we set the first byte for request.
			// 00 100 011 (or 0x23)
			// |  |   +-- client mode (3)
			// |  + ----- version (4)
			// + -------- leap year indicator, 0 no warning
			req := make([]byte, 48)
			req[0] = 0x23

			// send time request
			if err = binary.Write(conn, binary.BigEndian, req); err != nil {
				logrus.Errorf("fail to send NTP request")
				continue
			}

			// block to receive server response
			rsp := make([]byte, 48)
			if err = binary.Read(conn, binary.BigEndian, &rsp); err != nil {
				logrus.Errorf("fail to receive NTP response")
				continue
			}
			isSuccess = true
			break
		}

		if !isSuccess {
			logrus.Errorf("fail to validate NTP servers %v", ipStrings)
			return fmt.Errorf("fail to validate NTP servers: %v, err: %w", ipStrings, err)
		}
	}

	return nil
}

func enableNTPServers(ntpServerList []string) error {
	if len(ntpServerList) == 0 {
		return nil
	}

	// LooseLoad allows us to handle the case where the file doesn't exist yet
	cfg, err := ini.LooseLoad("/etc/systemd/timesyncd.conf")
	if err != nil {
		return err
	}

	cfg.Section("Time").Key("NTP").SetValue(strings.Join(ntpServerList, " "))
	if err = cfg.SaveTo("/etc/systemd/timesyncd.conf"); err != nil {
		return err
	}

	// When users want to reset NTP servers, we should stop timesyncd first,
	// so it can reload timesyncd.conf after restart.
	output, err := exec.Command("timedatectl", "set-ntp", "false").CombinedOutput()
	if err != nil {
		logrus.Error(err, string(output))
		return err
	}

	output, err = exec.Command("timedatectl", "set-ntp", "true").CombinedOutput()
	if err != nil {
		logrus.Error(err, string(output))
		return err
	}

	return nil
}

func updateDNSServersAndReloadNetConfig(dnsServerList []string, vlanId int) error {
	connection := "bridge-mgmt"
	device := config.MgmtInterfaceName
	if vlanId > 1 {
		connection = "vlan-mgmt"
		device = fmt.Sprintf("%s.%d", device, vlanId)
	}
	dnsServers := strings.Join(dnsServerList, ",")
	output, err := exec.Command("nmcli", "con", "modify", connection, "ipv4.dns", dnsServers).CombinedOutput()
	if err != nil {
		logrus.Error(err, string(output))
		return err
	}

	output, err = exec.Command("nmcli", "device", "reapply", device).CombinedOutput()
	if err != nil {
		logrus.Error(err, string(output))
		return err
	}

	return nil
}

func diskExceedsMBRLimit(blockDevPath string) (bool, error) {
	// Test if the storage is larger than MBR limit (2TiB).
	// MBR partition table uses 32-bit values to describe the starting offset and length of a
	// partition. Due to this size limit, MBR allows a maximum disk size of
	// (2^32 - 1) = 4,294,967,295 sectors, which is 2,199,023,255,040 bytes (512 bytes per sector)
	output, err := exec.Command("/bin/sh", "-c", fmt.Sprintf(`lsblk %s -n -b -d -r -o SIZE`, blockDevPath)).CombinedOutput()
	if err != nil {
		return false, err
	}
	sizeStr := strings.TrimSpace(string(output))
	sizeByte, err := strconv.ParseInt(sizeStr, 10, 64)
	if err != nil {
		return false, err
	}

	if sizeByte > 2199023255040 {
		return true, nil
	}
	return false, nil
}

func retryOnError(retryNum, retryInterval int64, process func() error) error {
	for {
		if err := process(); err != nil {
			if retryNum == 0 {
				return err
			}
			retryNum--
			if retryInterval > 0 {
				time.Sleep(time.Duration(retryInterval) * time.Second)
			}
			continue
		}
		return nil
	}
}

func getRemoteSSHKeys(url string) ([]string, error) {
	client := newProxyClient()
	b, err := getURL(client, url)
	if err != nil {
		return nil, err
	}

	lines := strings.Split(string(b), "\n")
	keys := make([]string, 0, len(lines))
	for i, line := range lines {
		if line == "" {
			continue
		}
		_, _, _, _, err := ssh.ParseAuthorizedKey([]byte(line))
		if err != nil {
			return nil, errors.Errorf("fail to parse on line %d: %s", i+1, line)
		}
		keys = append(keys, line)
	}
	if len(keys) == 0 {
		return nil, errors.Errorf(("no key found"))
	}
	return keys, nil
}

func getFormattedServerURL(addr string) (string, error) {
	if addr == "" {
		return "", errors.New("management address cannot be empty")
	}
	addr = strings.TrimSpace(addr)

	realAddr := addr
	if !strings.HasPrefix(addr, https) {
		realAddr = https + addr
	}
	parsedURL, err := url.ParseRequestURI(realAddr)
	if err != nil {
		return "", fmt.Errorf("%s is invalid", addr)
	}

	host := parsedURL.Hostname()
	if checkIP(host) != nil && checkDomain(host) != nil {
		return "", fmt.Errorf("%s is not a valid ip/domain", addr)
	}

	if parsedURL.Path != "" {
		return "", fmt.Errorf("path is not allowed in management address: %s", parsedURL.Path)
	}

	port := parsedURL.Port()
	if port == "" {
		parsedURL.Host += ":443"
	} else if port != "443" {
		return "", fmt.Errorf("currently non-443 port are not allowed")
	}

	return parsedURL.String(), nil
}

func getServerURLFromRancherdConfig(data []byte) (string, error) {
	rancherdConf := make(map[string]interface{})
	err := yaml.Unmarshal(data, rancherdConf)
	if err != nil {
		return "", err
	}

	if server, ok := rancherdConf["server"]; ok {
		serverURL, typeOK := server.(string)
		if typeOK {
			return serverURL, nil
		}
	}
	return "", nil
}

func showNext(c *Console, names ...string) error {
	for _, name := range names {
		v, err := c.GetElement(name)
		if err != nil {
			return err
		}
		if err := v.Show(); err != nil {
			return err
		}
	}

	validatorV, err := c.GetElement(validatorPanel)
	if err != nil {
		return err
	}
	if err := validatorV.Close(); err != nil {
		return err
	}
	return nil
}

func generateHostName() string {
	return "vdi-" + rand.String(5)
}

func execute(ctx context.Context, g *gocui.Gui, env []string, cmdName string) error {
	cmd := exec.CommandContext(ctx, cmdName)
	cmd.Env = env
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}
	defer stderr.Close() //nolint:errcheck

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	defer stdout.Close() //nolint:errcheck

	var wg sync.WaitGroup
	var writeLock sync.Mutex

	wg.Add(2)
	go func() {
		defer wg.Done()
		printToPanelAndLog(g, installPanel, "[stderr]", stderr, &writeLock)
	}()

	go func() {
		defer wg.Done()
		printToPanelAndLog(g, installPanel, "[stdout]", stdout, &writeLock)
	}()

	if err := cmd.Start(); err != nil {
		return err
	}

	wg.Wait()
	return cmd.Wait()
}

func dropCR(data []byte) []byte {
	if len(data) > 0 && data[len(data)-1] == '\r' {
		return data[0 : len(data)-1]
	}
	return data
}

func ScanLines(data []byte, atEOF bool) (advance int, token []byte, err error) {
	if atEOF && len(data) == 0 {
		return 0, nil, nil
	}

	if i := bytes.IndexByte(data, '\r'); i >= 0 {
		// We have a full CR-terminated line.
		return i + 1, dropCR(data[0:i]), nil
	}

	if i := bytes.IndexByte(data, '\n'); i >= 0 {
		// We have a full newline-terminated line.
		return i + 1, dropCR(data[0:i]), nil
	}

	// If we're at EOF, we have a final, non-terminated line. Return it.
	if atEOF {
		return len(data), dropCR(data), nil
	}
	// Request more data.
	return 0, nil, nil
}

func printToPanelAndLog(g *gocui.Gui, panel string, logPrefix string, reader io.Reader, lock *sync.Mutex) {
	scanner := bufio.NewScanner(reader)
	scanner.Split(ScanLines)

	for scanner.Scan() {
		logrus.Infof("%s: %s", logPrefix, scanner.Text())
		lock.Lock()
		printToPanel(g, scanner.Text(), panel)
		lock.Unlock()
	}
}

func saveElementalConfig(obj interface{}) (string, string, error) {
	err := os.MkdirAll(ElementalConfigDir, os.ModePerm) //nolint:gosec
	if err != nil {
		return "", "", err
	}

	bytes, err := yaml.Marshal(obj)
	if err != nil {
		return "", "", err
	}

	elementalConfigFile := filepath.Join(ElementalConfigDir, ElementalConfigFile)
	err = os.WriteFile(elementalConfigFile, bytes, 0600)
	if err != nil {
		return "", "", err
	}

	return ElementalConfigDir, elementalConfigFile, nil
}

func saveTemp(obj interface{}, prefix string) (string, error) {
	tempFile, err := os.CreateTemp("/tmp", fmt.Sprintf("%s.", prefix))
	if err != nil {
		return "", err
	}

	bytes, err := yaml.Marshal(obj)
	if err != nil {
		return "", err
	}
	if _, err := tempFile.Write(bytes); err != nil {
		return "", err
	}
	if err := tempFile.Close(); err != nil {
		return "", err
	}

	logrus.Infof("Content of %s: %s", tempFile.Name(), string(bytes))

	return tempFile.Name(), nil
}

func roleSetup(c *config.VDIConfig) error {
	if c.Install.Role == "" {
		return nil
	}
	if c.OS.Labels == nil {
		c.OS.Labels = make(map[string]string)
	}
	switch c.Install.Role {
	case config.RoleMaster:
		c.OS.Labels[util.HarvesterMgmtNodeLabelKey] = "true"
	case config.RoleWorker:
		c.OS.Labels[util.HarvesterWorkerNodeLabelKey] = "true"
	case config.RoleFirst:
		// do not set any label
	default:
		return fmt.Errorf("unknown role %s, please correct it", c.Install.Role)
	}
	return nil
}

func doInstall(g *gocui.Gui, hvstConfig *config.VDIConfig, webhooks RendererWebhooks) error {
	logrus.Info("doInstall: started (Kickstart mode)")
	webhooks.Handle(EventInstallStarted)

	// specific the node label for the specific node role
	if err := roleSetup(hvstConfig); err != nil {
		return err
	}

	// 渲染完整的 Kickstart 配置
	ks, err := config.KickstartRender(hvstConfig)
	if err != nil {
		logrus.Errorf("doInstall: KickstartRender failed: %v", err)
		printToPanel(g, fmt.Sprintf("渲染 Kickstart 失败: %v", err), installPanel)
		webhooks.Handle(EventInstallFailed)
		return err
	}

	// 将其写入 /tmp/ks-include.cfg
	ksPath := "/tmp/ks-include.cfg"
	if err := os.WriteFile(ksPath, []byte(ks), 0644); err != nil {
		logrus.Errorf("doInstall: write ks to %s failed: %v", ksPath, err)
		printToPanel(g, fmt.Sprintf("写入 %s 失败: %v", ksPath, err), installPanel)
		webhooks.Handle(EventInstallFailed)
		return err
	}
	logrus.Infof("doInstall: Kickstart rendered to %s", ksPath)

	printToPanel(g, fmt.Sprintf("配置已成功保存到 %s", ksPath), installPanel)
	printToPanel(g, "即将退出配置程序，系统安装将由 Anaconda 接管...", installPanel)

	webhooks.Handle(EventInstallSuceeded)

	// 延时 2 秒，然后平滑关闭 gocui 主循环以退出 vdi-installer
	go func() {
		time.Sleep(2 * time.Second)
		g.Update(func(g *gocui.Gui) error {
			return gocui.ErrQuit
		})
	}()

	return nil
}

func doUpgrade(g *gocui.Gui) error {
	// TODO(kiefer): to cOS upgrade method
	cmd := exec.Command("/k3os/system/k3os/current/harvester-upgrade.sh")
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	if err := cmd.Start(); err != nil {
		return err
	}

	scanner := bufio.NewScanner(stdout)
	for scanner.Scan() {
		printToPanel(g, scanner.Text(), upgradePanel)
	}
	scanner = bufio.NewScanner(stderr)
	for scanner.Scan() {
		printToPanel(g, scanner.Text(), upgradePanel)
	}
	return nil
}

func printToPanel(g *gocui.Gui, message string, panelName string) {
	// block printToPanel call in the same goroutine.
	// This ensures messages are printed out in the calling order.
	ch := make(chan struct{})

	g.Update(func(g *gocui.Gui) error {

		defer func() {
			ch <- struct{}{}
		}()

		v, err := g.View(panelName)
		if err != nil {
			return err
		}
		_, err = fmt.Fprintln(v, message)
		return err
	})

	<-ch
}

func getRemoteConfig(configURL string) (*config.VDIConfig, error) {
	client := newProxyClient()
	b, err := getURL(client, configURL)
	if err != nil {
		return nil, err
	}
	cfg, err := config.LoadVDIConfig(b)
	if err != nil {
		return nil, err
	}
	return cfg, nil
}

func retryRemoteConfig(configURL string, g *gocui.Gui) (*config.VDIConfig, error) {
	var confData []byte
	client := newProxyClient()

	retries := 30
	interval := 10
	err := retryOnError(int64(retries), int64(interval), func() error {
		var e error
		confData, e = getURL(client, configURL)
		if e != nil {
			logrus.Error(e)
			printToPanel(g, e.Error(), installPanel)
			printToPanel(g, fmt.Sprintf("Retry after %d seconds (Remaining: %d)...", interval, retries), installPanel)
			retries--
		}
		return e
	})

	if err != nil {
		return nil, fmt.Errorf("fail to fetch config: %w", err)
	}

	cfg, err := config.LoadVDIConfig(confData)
	if err != nil {
		return nil, fmt.Errorf("fail to load config: %w", err)
	}
	return cfg, nil
}

func validateDiskSize(devPath string, single bool) error {
	diskSizeBytes, err := util.GetDiskSizeBytes(devPath)
	if err != nil {
		return err
	}

	limit := config.SingleDiskMinSizeGiB
	if !single {
		limit = config.MultipleDiskMinSizeGiB
	}
	if util.ByteToGi(diskSizeBytes) < limit {
		return fmt.Errorf("installation disk size is too small. Minimum %dGi is required", limit)
	}

	return nil
}

func validateDataDiskSize(devPath string) error {
	diskSizeBytes, err := util.GetDiskSizeBytes(devPath)
	if err != nil {
		return err
	}
	if util.ByteToGi(diskSizeBytes) < config.HardMinDataDiskSizeGiB {
		return fmt.Errorf("data disk size is too small. Minimum %dGi is required", config.HardMinDataDiskSizeGiB)
	}

	return nil
}

func createVerticalLocator(c *Console) func(elem widgets.Element, height int) {
	maxX, maxY := c.Gui.Size()
	lastY := maxY / 8
	return func(elem widgets.Element, height int) {
		if height <= 0 {
			panic("element height must be > 0")
		}

		var (
			x0 = maxX / 8
			y0 = lastY
			x1 = maxX / 8 * 7
			y1 = lastY + height
		)
		lastY += height
		elem.SetLocation(x0, y0, x1, y1)
	}
}

func createVerticalLocatorWithName(c *Console) func(elemName string, height int) error {
	maxX, maxY := c.Gui.Size()
	lastY := maxY / 8
	return func(elemName string, height int) error {
		if height <= 0 {
			panic(fmt.Sprintf("height of element %q must be > 0", elemName))
		}

		elem, err := c.GetElement(elemName)
		if err != nil {
			return err
		}

		var (
			x0 = maxX / 8
			y0 = lastY
			x1 = maxX / 8 * 7
			y1 = lastY + height
		)
		lastY += height
		elem.SetLocation(x0, y0, x1, y1)
		return nil
	}
}

func needToGetVIPFromDHCP(mode, vip, hwAddr string) bool {
	return strings.ToLower(mode) == config.NetworkMethodDHCP && (vip == "" || hwAddr == "")
}

func executeSupportconfig(ctx context.Context, fileName string) error {
	cmd := exec.CommandContext(ctx, "/sbin/supportconfig", "-Q", "-B", fileName)

	err := cmd.Start()
	if err != nil {
		return err
	}

	return cmd.Wait()
}

func configureInstalledNode(g *gocui.Gui, hvstConfig *config.VDIConfig, webhooks RendererWebhooks) error {
	logrus.Info("configureInstalledNode: ignored under Kickstart mode")
	webhooks.Handle(EventInstallStarted)
	printToPanel(g, "系统配置在 Kickstart 自动化装机中由 Anaconda 接管，正在平滑退出...", installPanel)
	webhooks.Handle(EventInstallSuceeded)

	go func() {
		time.Sleep(2 * time.Second)
		g.Update(func(g *gocui.Gui) error {
			return gocui.ErrQuit
		})
	}()
	return nil
}

// internal objects to parse lsblk output
type BlockDevices struct {
	Disks []Device `json:"blockdevices"`
}

type Device struct {
	Name     string   `json:"name"`
	Size     string   `json:"size"`
	DiskType string   `json:"type"`
	WWN      string   `json:"wwn,omitempty"`
	Serial   string   `json:"serial,omitempty"`
	Label    string   `json:"label,omitempty"`
	Children []Device `json:"children,omitempty"`
}

func generateDiskEntry(d Device) string {
	return fmt.Sprintf("%s %s", d.Name, d.Size)
}

const (
	diskType = "disk"
)

var (
	// So that we can fake this stuff up for unit tests
	run = runCommand
)

type DiskOptionsCache struct {
	diskOptions              []widgets.Option
	hvstInstalledDiskOptions []widgets.Option
}

func NewDiskOptionsCache() *DiskOptionsCache {
	return &DiskOptionsCache{}
}

func (d *DiskOptionsCache) refresh() error {
	output, err := run(exec.Command("/bin/sh", "-c", `lsblk -J -o NAME,SIZE,TYPE,WWN,SERIAL,LABEL`))

	if err != nil {
		return err
	}

	resultMap, err := filterUniqueDisks(output)
	if err != nil {
		return err
	}

	disks := make([]string, 0, len(resultMap))
	hvstInstalledDisks := make([]string, 0)
	for _, device := range resultMap {
		disks = append(disks, generateDiskEntry(device))
		if deviceContainsCOSPartition(device) {
			hvstInstalledDisks = append(hvstInstalledDisks, generateDiskEntry(device))
		}
	}

	// ordered result makes the stable item list on the downstream DropDown widget
	sort.Strings(disks)
	sort.Strings(hvstInstalledDisks)

	d.diskOptions = generateDiskWidgetOptions(disks)
	d.hvstInstalledDiskOptions = generateDiskWidgetOptions(hvstInstalledDisks)

	return nil
}

func (d *DiskOptionsCache) getAllValidDiskOptions() []widgets.Option {
	return d.diskOptions
}

func (d *DiskOptionsCache) getDataDiskOptions(hvstConfig *config.VDIConfig) []widgets.Option {
	// Show the OS disk as "Use the installation disk (<Disk Name>)"

	const newTextTemplate = "Use the installation disk (%s)"
	deviceForOS := hvstConfig.Install.Device
	diskOpts := make([]widgets.Option, len(d.diskOptions))
	copy(diskOpts, d.diskOptions)
	if deviceForOS == "" {
		diskOpts[0].Text = fmt.Sprintf(newTextTemplate, diskOpts[0].Text)
		return diskOpts
	}

	for i, diskOpt := range diskOpts {
		if diskOpt.Value == deviceForOS {
			osDiskOpt := widgets.Option{
				Text:  fmt.Sprintf(newTextTemplate, diskOpt.Text),
				Value: diskOpt.Value,
			}
			diskOpts = append(diskOpts[:i], diskOpts[i+1:]...)
			diskOpts = append([]widgets.Option{osDiskOpt}, diskOpts...)
			return diskOpts
		}
	}
	logrus.Warnf("device '%s' not found in disk options", deviceForOS)
	return nil
}

func (d *DiskOptionsCache) getWipeDisksOptions(hvstConfig *config.VDIConfig) []widgets.Option {
	// filter disks to ignore disks which may be used as base install device
	// or an additional data disk, and rest can be used for generation of option
	var filterDisks []widgets.Option
	for _, v := range d.hvstInstalledDiskOptions {
		if v.Value != hvstConfig.Install.Device && v.Value != hvstConfig.Install.DataDisk {
			filterDisks = append(filterDisks, v)
		}
	}
	return filterDisks
}

// filterUniqueDisks will dedup results of disk output to generate a map[disName]Device of unique devices
func filterUniqueDisks(output []byte) (map[string]Device, error) {
	disks := &BlockDevices{}
	err := json.Unmarshal(output, disks)
	if err != nil {
		return nil, fmt.Errorf("error unmarshalling lsblk json output: %v", err)
	}
	// identify devices which may be unique
	dedupMap := make(map[string]Device)
	for _, disk := range disks.Disks {
		if disk.DiskType == diskType {
			// no serial or wwn info present
			// add to list of disks
			if disk.WWN == "" && disk.Serial == "" {
				dedupMap[disk.Name] = disk
				continue
			}

			if disk.Serial != "" {
				_, ok := dedupMap[disk.Serial]
				if !ok {
					dedupMap[disk.Serial] = disk
				}
			}

			// disks may have same serial number but different wwn when used with a raid array
			// as evident in test data from a host with a raid array
			// in this case if serial number is same, we still check for unique wwn
			if disk.WWN != "" {
				_, ok := dedupMap[disk.WWN]
				if !ok {
					dedupMap[disk.WWN] = disk
				}
				continue
			}
		}
	}
	// devices may appear twice in the map when both serial number and wwn info is present
	// we need to ensure only unique names are shown in the console
	resultMap := make(map[string]Device)
	for _, v := range dedupMap {
		resultMap[v.Name] = v
	}
	return resultMap, nil
}

func deviceContainsCOSPartition(disk Device) bool {
	for _, partition := range disk.Children {
		if partition.DiskType == MpathType {
			return deviceContainsCOSPartition(partition)
		}
		if partition.DiskType == PartitionType && partition.Label == CosDiskLabelPrefix {
			return true
		}
	}
	return false
}

func generateDiskWidgetOptions(lines []string) []widgets.Option {
	var options []widgets.Option
	for _, line := range lines {
		splits := strings.SplitN(line, " ", 2)
		if len(splits) == 2 {
			options = append(options, widgets.Option{
				Value: "/dev/" + splits[0],
				Text:  line,
			})
		}
	}
	return options
}

func executeWipeDisks(ctx context.Context, name string) error {
	cmd := exec.CommandContext(ctx, "/usr/sbin/sgdisk", "-Z", name)
	if _, err := runCommand(cmd); err != nil {
		return err
	}
	cmd = exec.CommandContext(ctx, "/usr/sbin/partprobe", "-s", name)
	if _, err := runCommand(cmd); err != nil {
		return err
	}
	return nil
}

func runCommand(cmd *exec.Cmd) ([]byte, error) {
	output, err := cmd.CombinedOutput()
	if err != nil {
		logrus.Error(string(output))
	}
	return output, err
}
