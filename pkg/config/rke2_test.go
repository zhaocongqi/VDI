package config

import (
	"log"
	"os"
	"testing"

	"github.com/stretchr/testify/assert"

	"vdi-installer/pkg/util"
)

func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "rke2-test-")
	if err != nil {
		log.Fatalf("error: %v", err)
	}
	defer os.RemoveAll(dir)

	// So UpdateManagementInterfaceConfig will work
	NMConnectionPath = dir

	m.Run()
}



func TestGenBootstrapResources(t *testing.T) {
	conf, err := LoadVDIConfig(util.LoadFixture(t, "vdi-config.yaml"))
	assert.NoError(t, err)
	bootstrapResources, err := genBootstrapResources(conf)
	assert.NoError(t, err)
	assert.True(t, len(bootstrapResources) > 0)
}

