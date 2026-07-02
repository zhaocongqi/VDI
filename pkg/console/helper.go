package console

import (
	"github.com/jroimartin/gocui"

	"vdi-installer/pkg/widgets"
)

type passwordWrapper struct {
	c                *Console
	passwordV        *widgets.Input
	passwordConfirmV *widgets.Input
}

func (p *passwordWrapper) passwordVConfirmKeyBinding(_ *gocui.Gui, _ *gocui.View) error {
	password1V, err := p.c.GetElement(passwordPanel)
	if err != nil {
		return err
	}
	userInputData.Password, err = password1V.GetData()
	if err != nil {
		return err
	}
	if userInputData.Password == "" {
		return p.c.setContentByName(validatorPanel, "Password is required")
	}
	return showNext(p.c, passwordConfirmPanel)
}

func (p *passwordWrapper) passwordVEscapeKeyBinding(_ *gocui.Gui, _ *gocui.View) error {
	var err error
	if err = p.passwordV.Close(); err != nil {
		return err
	}
	if err = p.passwordConfirmV.Close(); err != nil {
		return err
	}
	if err := p.c.setContentByName(notePanel, ""); err != nil {
		return err
	}
	// VDI 角色已在 askCreatePanel 选定，ESC 统一回退到安装模式选择
	return showNext(p.c, askCreatePanel)
}

func (p *passwordWrapper) passwordConfirmVArrowUpKeyBinding(_ *gocui.Gui, _ *gocui.View) error {
	var err error
	userInputData.PasswordConfirm, err = p.passwordConfirmV.GetData()
	if err != nil {
		return err
	}
	return showNext(p.c, passwordPanel)
}

func (p *passwordWrapper) passwordConfirmVKeyEnter(_ *gocui.Gui, _ *gocui.View) error {
	var err error
	userInputData.PasswordConfirm, err = p.passwordConfirmV.GetData()
	if err != nil {
		return err
	}
	if userInputData.Password != userInputData.PasswordConfirm {
		return p.c.setContentByName(validatorPanel, "Password mismatching")
	}
	if err = p.passwordV.Close(); err != nil {
		return err
	}
	if err = p.passwordConfirmV.Close(); err != nil {
		return err
	}
	// 统一存明文：cfg.OS.Password 在自动模式（auto_install.go）、cloud-init 合并、
	// kickstart 渲染间保持明文约定，加密只在 KickstartRender 内做一次（openssl passwd -6
	// 写 shadow + rootpw --iscrypted）。历史此处调 GetEncryptedPasswd 把明文加密成 $6$ hash
	// 存入 config，kickstart.go 又对该 hash 跑 openssl passwd -6 二次加密，致 shadow 里的
	// hash 与明文不匹配，SSH 永远 Permission denied。
	p.c.config.OS.Password = userInputData.Password
	return showDiskPage(p.c)
}

func (p *passwordWrapper) passwordConfirmVKeyEscape(_ *gocui.Gui, _ *gocui.View) error {
	var err error
	if err = p.passwordV.Close(); err != nil {
		return err
	}
	if err = p.passwordConfirmV.Close(); err != nil {
		return err
	}
	if err := p.c.setContentByName(notePanel, ""); err != nil {
		return err
	}
	// VDI 角色已在 askCreatePanel 选定，ESC 统一回退到安装模式选择
	return showNext(p.c, askCreatePanel)
}
