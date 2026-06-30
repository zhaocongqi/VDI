package console

import (
	"context"
	"fmt"
	"os"
	"syscall"

	"github.com/jroimartin/gocui"
	"github.com/sirupsen/logrus"

	"vdi-installer/pkg/config"
	"vdi-installer/pkg/preflight"
	"vdi-installer/pkg/widgets"
)

var (
	debug bool
)

const (
	defaultLogFilePath = "/var/log/console.log"
)

func initLogs() error {
	if os.Getenv("DEBUG") == "true" {
		debug = true
		logrus.SetLevel(logrus.DebugLevel)
	}

	var logFilePath string
	if path := os.Getenv("LOGFILE"); path != "" {
		logFilePath = path
	} else {
		logFilePath = defaultLogFilePath
	}

	f, err := os.OpenFile(logFilePath, os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0600) //nolint:gosec
	if err != nil {
		return err
	}
	logrus.SetOutput(f)
	return nil
}

// Console is the structure of the VDI console
type Console struct {
	context context.Context
	*gocui.Gui
	elements map[string]widgets.Element
	config   *config.VDIConfig
}

// dbgSerial 把诊断写到串口 /dev/ttyS0（失败静默，且不污染 TUI 所在 tty），
// 供 anaconda %pre / 真机串口诊断 TUI 启动与 grabTTY 结果。
func dbgSerial(format string, args ...interface{}) {
	f, err := os.OpenFile("/dev/ttyS0", os.O_WRONLY|os.O_APPEND, 0)
	if err != nil {
		return
	}
	defer f.Close()
	fmt.Fprintf(f, ">>> [vdi] "+format+"\n", args...)
}

// grabTTY 新建会话并把 tty 强制设为控制终端，使当前进程成为该 tty 的前台会话 leader。
// anaconda %pre 环境下，tty2 上的 anaconda 调试 shell 会抢占键盘输入，导致 vdi-installer
// 的 TUI 虽渲染但收不到按键（TUI 与 shell 叠加、按键进 shell）。此处抢夺控制终端独占键盘。
// ramdisk 无 setsid 命令，故用 syscall 实现（root 的 CAP_SYS_ADMIN 允许 TIOCSCTTY 强制抢占）。
func grabTTY(tty string) error {
	if _, _, errno := syscall.RawSyscall(syscall.SYS_SETSID, 0, 0, 0); errno != 0 {
		return fmt.Errorf("setsid: %v", errno)
	}
	f, err := os.OpenFile(tty, os.O_RDWR, 0)
	if err != nil {
		return err
	}
	defer f.Close()
	const tiocsctty = 0x540E // Linux TIOCSCTTY
	if _, _, errno := syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), tiocsctty, 1); errno != 0 {
		return fmt.Errorf("TIOCSCTTY: %v", errno)
	}
	return nil
}

// RunConsole starts the console
func RunConsole() error {
	// 抢 TTY 前台独占键盘（非 tmux 环境下，anaconda 调试 shell 会抢 tty 输入）。
	// 在 anaconda tmux window 内运行时跳过：tmux pane 的 pty 已是单 reader，
	// setsid+TIOCSCTTY 反而会干扰 tmux 的 pty 归属。失败仅告警不中断。
	if tty := os.Getenv("TTY"); tty != "" && os.Getenv("TMUX") == "" {
		if err := grabTTY(tty); err != nil {
			dbgSerial("grabTTY(%s) 失败: %v（键盘可能仍被 shell 抢）", tty, err)
		} else {
			dbgSerial("grabTTY OK: 已抢 %s 前台独占键盘", tty)
		}
	}
	c, err := NewConsole()
	if err != nil {
		return err
	}
	if err := initLogs(); err != nil {
		return err
	}

	// 终端尺寸前置校验：gocui 面板坐标依赖 g.Size()，尺寸不足会导致 TUI 全黑屏。
	// 在此明确报错便于诊断（start-installer.sh 通过 stty 设置足够大的 winsize）。
	if w, h := c.Gui.Size(); w < 80 || h < 24 {
		return fmt.Errorf("terminal size %dx%d too small for TUI (need >= 80x24); ensure start-installer.sh sets winsize via stty", w, h)
	}

	err = c.doRun()
	if err != nil {
		// This ensures difficult to debug failures
		// (e.g. invalid dimensions) are actually logged
		logrus.Errorf("console.doRun() failed: %v", err)
	}
	return err
}

// NewConsole initialize the console
func NewConsole() (*Console, error) {
	g, err := gocui.NewGui(gocui.OutputNormal)
	if err != nil {
		return nil, err
	}
	return &Console{
		context:  context.Background(),
		Gui:      g,
		elements: make(map[string]widgets.Element),
		config:   config.NewVDIConfig(),
	}, nil
}

// GetElement gets an element by name
func (c *Console) GetElement(name string) (widgets.Element, error) {
	e, ok := c.elements[name]
	if ok {
		return e, nil
	}
	return nil, fmt.Errorf("element %q is not found", name)
}

// AddElement adds an element with name
func (c *Console) AddElement(name string, element widgets.Element) {
	c.elements[name] = element
}

// ShowElement shows the element by name
func (c *Console) ShowElement(name string) error {
	elem, err := c.GetElement(name)
	if err != nil {
		return err
	}
	return elem.Show()
}

func (c *Console) setContentByName(name string, content string) error {
	v, err := c.GetElement(name)
	if err != nil {
		return err
	}
	if content == "" {
		return v.Close()
	}
	if err := v.Show(); err != nil {
		return err
	}
	v.SetContent(content)
	_, err = c.Gui.SetViewOnTop(name)
	return err
}

func (c *Console) CloseElement(name string) {
	v, err := c.GetElement(name)
	if err != nil {
		return
	}
	if err = v.Close(); err != nil && err != gocui.ErrUnknownView {
		logrus.Error(err)
	}
}

func (c *Console) CloseElements(names ...string) {
	for _, name := range names {
		c.CloseElement(name)
	}
}

func (c *Console) doRun() error {
	defer c.Close()

	dashboard := c.layoutInstall
	preflightCheck := true

	if hd, _ := os.LookupEnv("HARVESTER_DASHBOARD"); hd == "true" {
		if err := c.getHarvesterConfig(); err != nil {
			return err
		}
		if c.config.Install.Mode == config.ModeCreate {
			dashboard = c.layoutDashboard
			// no need to do preflight check after the node is installed, it runs layoutDashboard directly
			// preflightWarnings are used in layoutInstall
			preflightCheck = false
		}
	}

	// installModeBoot is used to control options in layoutInstall
	if c.config.Install.Mode == config.ModeInstall {
		logrus.Info("VDI already installed")
		alreadyInstalled = true
		c.config.Install.Mode = ""
		preflightCheck = false
	}

	if preflightCheck {
		checks := []preflight.Check{
			preflight.BIOSCheck{},
			preflight.CPUCheck{},
			preflight.MemoryCheck{},
			preflight.VirtCheck{},
			preflight.KVMHostCheck{},
		}
		for _, c := range checks {
			msg, err := c.Run()
			if err != nil {
				// Preflight checks that fail to run at all are
				// logged, rather than killing the installer
				logrus.Error(err)
				continue
			}
			if len(msg) > 0 {
				preflightWarnings = append(preflightWarnings, msg)
			}
		}
	}

	c.SetManagerFunc(dashboard)

	if err := setGlobalKeyBindings(c.Gui); err != nil {
		return err
	}

	dbgSerial("doRun: 进 MainLoop（TUI 应渲染）")
	if err := c.MainLoop(); err != nil && err != gocui.ErrQuit {
		dbgSerial("MainLoop err: %v", err)
		return err
	}
	dbgSerial("doRun: MainLoop 退出（用户完成配置）")
	return nil
}

func setGlobalKeyBindings(g *gocui.Gui) error {
	g.InputEsc = true
	if debug {
		if err := g.SetKeybinding("", gocui.KeyCtrlC, gocui.ModNone, quit); err != nil {
			return err
		}
	}
	return nil
}

func quit(_ *gocui.Gui, _ *gocui.View) error {
	return gocui.ErrQuit
}
