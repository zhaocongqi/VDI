package console

import (
	"testing"

	"github.com/jroimartin/gocui"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

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
	err := addPasswordPanels(c)
	require.NoError(t, err)

	passwordV, err := c.GetElement(passwordPanel)
	require.NoError(t, err)
	inputV, ok := passwordV.(*widgets.Input)
	require.True(t, ok)

	_, hasEsc := inputV.KeyBindings[gocui.KeyEsc]
	assert.False(t, hasEsc, "passwordV should not bind to KeyEsc to prevent escape sequences issues")

	passwordConfirmV, err := c.GetElement(passwordConfirmPanel)
	require.NoError(t, err)
	inputConfirmV, ok := passwordConfirmV.(*widgets.Input)
	require.True(t, ok)

	_, hasConfirmEsc := inputConfirmV.KeyBindings[gocui.KeyEsc]
	assert.False(t, hasConfirmEsc, "passwordConfirmV should not bind to KeyEsc to prevent escape sequences issues")
}
