# TUI 密码框输入中断与意外跳转修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 TUI 密码输入框和确认密码输入框上的 `gocui.KeyEsc` 按键事件绑定，防止输入特殊字符时转义序列冲突导致的输入吞噬及意外退回主菜单 Bug。

**Architecture:** 在 `pkg/console/install_panels.go` 中，删去 `passwordV.KeyBindings` 与 `passwordConfirmV.KeyBindings` 里对 `gocui.KeyEsc` 的监听。编写单元测试文件 `pkg/console/install_panels_test.go` 针对按键绑定进行断言。

**Tech Stack:** Go 1.26, gocui, stretchr/testify

---

### Task 1: 移除 `gocui.KeyEsc` 事件绑定

**Files:**
- Modify: `pkg/console/install_panels.go:1016-1037`

- [ ] **Step 1: 移除 `gocui.KeyEsc` 按键映射**
  修改 `pkg/console/install_panels.go` 中的 `addPasswordPanel` 函数。

修改前的代码片段：
```go
	pw.passwordV.KeyBindings = map[gocui.Key]func(*gocui.Gui, *gocui.View) error{
		gocui.KeyEnter:     pw.passwordVConfirmKeyBinding,
		gocui.KeyArrowDown: pw.passwordVConfirmKeyBinding,
		gocui.KeyEsc:       pw.passwordVEscapeKeyBinding,
	}

	pw.passwordV.SetLocation(maxX/8, maxY/8, maxX/8*7, maxY/8+2)
	c.AddElement(passwordPanel, pw.passwordV)

	pw.passwordConfirmV.PreShow = func() error {
		c.Gui.Cursor = true
		passwordConfirmV.Value = userInputData.PasswordConfirm
		if err := c.setContentByName(notePanel, ""); err != nil {
			return err
		}
		return c.setContentByName(titlePanel, "Password change: set the default login password")
	}
	pw.passwordConfirmV.KeyBindings = map[gocui.Key]func(*gocui.Gui, *gocui.View) error{
		gocui.KeyArrowUp: pw.passwordConfirmVArrowUpKeyBinding,
		gocui.KeyEnter:   pw.passwordConfirmVKeyEnter,
		gocui.KeyEsc:     pw.passwordConfirmVKeyEscape,
	}
```

修改后的代码片段：
```go
	pw.passwordV.KeyBindings = map[gocui.Key]func(*gocui.Gui, *gocui.View) error{
		gocui.KeyEnter:     pw.passwordVConfirmKeyBinding,
		gocui.KeyArrowDown: pw.passwordVConfirmKeyBinding,
	}

	pw.passwordV.SetLocation(maxX/8, maxY/8, maxX/8*7, maxY/8+2)
	c.AddElement(passwordPanel, pw.passwordV)

	pw.passwordConfirmV.PreShow = func() error {
		c.Gui.Cursor = true
		passwordConfirmV.Value = userInputData.PasswordConfirm
		if err := c.setContentByName(notePanel, ""); err != nil {
			return err
		}
		return c.setContentByName(titlePanel, "Password change: set the default login password")
	}
	pw.passwordConfirmV.KeyBindings = map[gocui.Key]func(*gocui.Gui, *gocui.View) error{
		gocui.KeyArrowUp: pw.passwordConfirmVArrowUpKeyBinding,
		gocui.KeyEnter:   pw.passwordConfirmVKeyEnter,
	}
```

- [ ] **Step 2: 自我代码审查**
  确认语法无误，未多删或漏删大括号，且导入的 `github.com/jroimartin/gocui` 依然在使用（`gocui.KeyEnter` 等仍在）。

---

### Task 2: 编写单元测试验证按键绑定

**Files:**
- Create: `pkg/console/install_panels_test.go`

- [ ] **Step 1: 创建单元测试文件**
  新建 `pkg/console/install_panels_test.go`，内容如下：

```go
package console

import (
	"testing"

	"github.com/jroimartin/gocui"
	"github.com/stretchr/testify/assert"

	"vdi-installer/pkg/config"
	"vdi-installer/pkg/widgets"
)

func TestPasswordPanel_NoKeyEsc(t *testing.T) {
	g := &gocui.Gui{}
	c := &Console{
		Gui:      g,
		elements: make(map[string]widgets.Element),
		config:   config.NewVDIConfig(),
	}
	err := addPasswordPanel(c)
	assert.Nil(t, err)

	passwordV, err := c.GetElement(passwordPanel)
	assert.Nil(t, err)
	inputV, ok := passwordV.(*widgets.Input)
	assert.True(t, ok)

	_, hasEsc := inputV.KeyBindings[gocui.KeyEsc]
	assert.False(t, hasEsc, "passwordV should not bind to KeyEsc to prevent escape sequences issues")

	passwordConfirmV, err := c.GetElement(passwordConfirmPanel)
	assert.Nil(t, err)
	inputConfirmV, ok := passwordConfirmV.(*widgets.Input)
	assert.True(t, ok)

	_, hasConfirmEsc := inputConfirmV.KeyBindings[gocui.KeyEsc]
	assert.False(t, hasConfirmEsc, "passwordConfirmV should not bind to KeyEsc to prevent escape sequences issues")
}
```

- [ ] **Step 2: 运行测试并确保通过**
  运行命令：
  `go test -v ./pkg/console -run TestPasswordPanel_NoKeyEsc`
  预期输出：
  `PASS: TestPasswordPanel_NoKeyEsc` 且最终结果为 `PASS`。

---

### Task 3: 提交修改到 Git

- [ ] **Step 1: 提交代码**
  运行命令：
  ```bash
  git add pkg/console/install_panels.go pkg/console/install_panels_test.go docs/superpowers/plans/2026-06-23-fix-tui-password-esc.md
  git commit -m "fix(console): 移除密码框的 KeyEsc 绑定防止输入跳转" -m "Why: 特殊字符可能在部分终端被误识别为 Escape 序列开头，导致密码输入中断且意外退回首目录" -m "What: 移除 install_panels.go 中密码框与确认框的 gocui.KeyEsc 绑定，并增加单元测试"
  ```
