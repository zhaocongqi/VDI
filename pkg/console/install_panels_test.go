package console

import (
	"testing"

	"github.com/jroimartin/gocui"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"vdi-installer/pkg/config"
	"vdi-installer/pkg/widgets"
)

// TestPasswordPanel_KeyEsc 验证密码框与确认框绑定 KeyEsc。
// 设计：保留 ESC 让用户从密码页统一回退到安装模式选择（askCreatePanel）。
// 权衡：部分终端的特殊字符可能被误识别为 Escape 序列而触发回退（见 commit 5ad2dd4c），
// 当前以"ESC 回退"功能优先。
func TestPasswordPanel_KeyEsc(t *testing.T) {
	g := &gocui.Gui{}
	c := &Console{
		Gui:      g,
		elements: make(map[string]widgets.Element),
		config:   config.NewVDIConfig(),
	}
	err := addPasswordPanels(c)
	require.NoError(t, err)

	passwordV, err := c.GetElement(passwordPanel)
	require.NoError(t, err)
	inputV, ok := passwordV.(*widgets.Input)
	require.True(t, ok)

	_, hasEsc := inputV.KeyBindings[gocui.KeyEsc]
	assert.True(t, hasEsc, "passwordV should bind to KeyEsc to allow ESC back to create mode")

	passwordConfirmV, err := c.GetElement(passwordConfirmPanel)
	require.NoError(t, err)
	inputConfirmV, ok := passwordConfirmV.(*widgets.Input)
	require.True(t, ok)

	_, hasConfirmEsc := inputConfirmV.KeyBindings[gocui.KeyEsc]
	assert.True(t, hasConfirmEsc, "passwordConfirmV should bind to KeyEsc to allow ESC back to create mode")
}
