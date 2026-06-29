package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"gopkg.in/yaml.v3"
)

func TestHarvesterConfig_sanitized(t *testing.T) {
	c := NewVDIConfig()
	c.OS.Password = `#3tQ66t!`
	c.Token = `3mO3&nEJ`

	expected := NewVDIConfig()
	expected.OS.Password = SanitizeMask
	expected.Token = SanitizeMask

	s, err := c.sanitized()
	assert.Equal(t, nil, err)
	assert.Equal(t, expected, s)
}

func TestHarvesterConfig_GetKubeletLabelsArg(t *testing.T) {

	testCases := []struct {
		name      string
		input     map[string]string
		output    []string
		expectErr bool
	}{
		{
			name:   "Successfully creates node-labels argument",
			input:  map[string]string{"labelKey1": "value1"},
			output: []string{"max-pods=200", "node-labels=labelKey1=value1"},
		},
		{
			name:   "Returns maxPods even if no Labels are given",
			input:  map[string]string{},
			output: []string{"max-pods=200"},
		},
		{
			name:      "Error for invalid label name",
			input:     map[string]string{"???invalidName": "value"},
			output:    []string{},
			expectErr: true,
		},
		{
			name:      "Error for invalid label value",
			input:     map[string]string{"example.io/somelabel": "???value###NAH"},
			output:    []string{},
			expectErr: true,
		},
		{
			name:   "Successfully creates max-pods argument",
			input:  map[string]string{},
			output: []string{"max-pods=200"},
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			c := NewVDIConfig()
			c.OS.Labels = testCase.input

			result, err := c.GetKubeletArgs()

			if testCase.expectErr {
				assert.NotNil(t, err)
			} else {
				assert.Nil(t, err)
				assert.Equal(t,
					testCase.output,
					result,
				)
			}
		})
	}
}

func TestHarvesterRootfsRendering(t *testing.T) {
	type Rootfs struct {
		Environment map[string]string
	}

	testCases := []struct {
		name       string
		harvConfig VDIConfig
		assertion  func(t *testing.T, rootfs *Rootfs)
	}{
		{
			name:       "Test default config",
			harvConfig: VDIConfig{},
			assertion: func(t *testing.T, rootfs *Rootfs) {
				assert.Contains(t, rootfs.Environment["VOLUMES"], "LABEL=HARV_LH_DEFAULT:/var/lib/harvester/defaultdisk")
				assert.Contains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/var/lib/longhorn")
				assert.NotContains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/var/lib/harvester/defaultdisk")
			},
		},
		{
			name: "Test ForceMBR=true and no DataDisk -> No need to mount data partition",
			harvConfig: VDIConfig{
				Install: InstallConfig{
					ForceMBR: true,
					DataDisk: "",
				},
			},
			assertion: func(t *testing.T, rootfs *Rootfs) {
				assert.NotContains(t, rootfs.Environment["VOLUMES"], "LABEL=HARV_LH_DEFAULT:/var/lib/harvester/defaultdisk")
				assert.Contains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/var/lib/longhorn")
				assert.Contains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/var/lib/harvester/defaultdisk")
			},
		},
		{
			name: "Test ForceMBR=true but has DataDisk -> Still need to mount data partition",
			harvConfig: VDIConfig{
				Install: InstallConfig{
					ForceMBR: true,
					DataDisk: "/dev/sdb",
				},
			},
			assertion: func(t *testing.T, rootfs *Rootfs) {
				assert.Contains(t, rootfs.Environment["VOLUMES"], "LABEL=HARV_LH_DEFAULT:/var/lib/harvester/defaultdisk")
				assert.Contains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/var/lib/longhorn")
				assert.NotContains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/var/lib/harvester/defaultdisk")
			},
		},
		{
			name: "Test additional persistent state paths",
			harvConfig: VDIConfig{
				OS: OSConfig{
					PersistentStatePaths: []string{
						"/path1",
						"/path2",
					},
				},
			},
			assertion: func(t *testing.T, rootfs *Rootfs) {
				assert.Contains(t, rootfs.Environment["VOLUMES"], "LABEL=HARV_LH_DEFAULT:/var/lib/harvester/defaultdisk")
				assert.NotContains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/var/lib/harvester/defaultdisk")
				assert.Contains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/path1")
				assert.Contains(t, rootfs.Environment["PERSISTENT_STATE_PATHS"], "/path2")
			},
		},
	}

	for _, tc := range testCases {
		content, err := render("cos-rootfs.yaml", &tc.harvConfig)
		assert.NoError(t, err)
		t.Log("Rendered content:")
		t.Log(content)

		rootfs := Rootfs{}
		err = yaml.Unmarshal([]byte(content), &rootfs)
		assert.NoError(t, err)
		t.Log("Loaded Config:")
		t.Log(rootfs)

		tc.assertion(t, &rootfs)
	}
}

func TestNetworkRendering_MTU(t *testing.T) {
	testCases := []struct {
		name         string
		templateName string
		network      interface{}
		assertion    func(t *testing.T, result string)
	}{
		{
			name:         "MTU = 0 will not set MTU for bond master",
			templateName: "nm-bond-master.nmconnection",
			network: map[string]interface{}{
				"Bond":     Network{MTU: 0},
				"BondName": MgmtBondInterfaceName,
			},
			assertion: func(t *testing.T, result string) {
				assert.NotContains(t, result, "mtu=")
			},
		},
		{
			name:         "MTU != 0  will set the MTU for bond master",
			templateName: "nm-bond-master.nmconnection",
			network: map[string]interface{}{
				"Bond":     Network{MTU: 1234},
				"BondName": MgmtBondInterfaceName,
			},
			assertion: func(t *testing.T, result string) {
				assert.Contains(t, result, "mtu=1234")
			},
		},
		{
			name:         "MTU = 0 will not set MTU for bridge",
			templateName: "nm-bridge.nmconnection",
			network: map[string]interface{}{
				"Bridge":     Network{MTU: 0},
				"BridgeName": MgmtInterfaceName,
			},
			assertion: func(t *testing.T, result string) {
				assert.NotContains(t, result, "mtu=")
			},
		},
		{
			name:         "MTU != 0  will set the MTU for bridge",
			templateName: "nm-bridge.nmconnection",
			network: map[string]interface{}{
				"Bridge":     Network{MTU: 2345},
				"BridgeName": MgmtInterfaceName,
			},
			assertion: func(t *testing.T, result string) {
				assert.Contains(t, result, "mtu=2345")
			},
		},
		{
			name:         "MTU = 0 will not set MTU for vlan",
			templateName: "nm-vlan.nmconnection",
			network: map[string]interface{}{
				"BridgeName": MgmtInterfaceName,
				"Vlan":       Network{MTU: 0},
			},
			assertion: func(t *testing.T, result string) {
				assert.NotContains(t, result, "mtu=")
			},
		},
		{
			name:         "MTU != 0  will set the MTU for vlan",
			templateName: "nm-vlan.nmconnection",
			network: map[string]interface{}{
				"BridgeName": MgmtInterfaceName,
				"Vlan":       Network{MTU: 3456},
			},
			assertion: func(t *testing.T, result string) {
				assert.Contains(t, result, "mtu=3456")
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result, err := render(tc.templateName, tc.network)
			t.Log(result)
			assert.NoError(t, err)

			tc.assertion(t, result)
		})
	}
}

func TestHarvesterConfigMerge_OtherField(t *testing.T) {
	conf := NewVDIConfig()
	conf.OS.Hostname = "hellofoo"
	conf.OS.Labels = map[string]string{"foo": "bar"}
	conf.OS.DNSNameservers = []string{"1.1.1.1"}

	otherConf := NewVDIConfig()
	otherConf.OS.Hostname = "NOOOOOOO"
	otherConf.Token = "TokenValue"
	otherConf.OS.Labels = map[string]string{"key": "val"}
	otherConf.OS.DNSNameservers = []string{"8.8.8.8"}

	err := conf.Merge(*otherConf)
	assert.NoError(t, err)

	assert.Equal(t, "hellofoo", conf.OS.Hostname, "Primitive field should not be override")
	assert.Equal(t, map[string]string{"foo": "bar", "key": "val"}, conf.OS.Labels, "Map field should be merged")
	assert.Equal(t, []string{"1.1.1.1", "8.8.8.8"}, conf.OS.DNSNameservers, "Slice shoule be appended")
	assert.Equal(t, "TokenValue", conf.Token, "New field should be added")
}

func TestHarvesterAfterInstallChrootRendering(t *testing.T) {
	type HarvesterAfterInstallChroot struct {
		Commands []string `yaml:"commands,omitempty"`
	}

	testCases := []struct {
		name       string
		harvConfig VDIConfig
		assertion  func(t *testing.T, afterInstallChroot *HarvesterAfterInstallChroot)
	}{

		{
			name: "Test after-install-chroot-command",
			harvConfig: VDIConfig{
				OS: OSConfig{
					AfterInstallChrootCommands: []string{
						`echo "hello"`,
						`echo "world"`,
					},
				},
			},
			assertion: func(t *testing.T, afterInstallChroot *HarvesterAfterInstallChroot) {
				assert.Contains(t, afterInstallChroot.Commands, `echo "hello"`)
				assert.Contains(t, afterInstallChroot.Commands, `echo "world"`)
			},
		},
	}

	for _, tc := range testCases {
		content, err := render("cos-after-install-chroot.yaml", tc.harvConfig)
		assert.NoError(t, err)
		t.Log("Rendered content:")
		t.Log(content)

		afterInstallChroot := HarvesterAfterInstallChroot{}
		err = yaml.Unmarshal([]byte(content), &afterInstallChroot)
		assert.NoError(t, err)
		t.Log("Loaded Config:")
		t.Log(afterInstallChroot)

		tc.assertion(t, &afterInstallChroot)
	}
}

func TestCalculateCPUReservedInMilliCPU(t *testing.T) {
	testCases := []struct {
		name               string
		coreNum            int
		maxPods            int
		reservedMilliCores int64
	}{
		{
			name:               "invalid core num",
			coreNum:            -1,
			maxPods:            MaxPods,
			reservedMilliCores: 0,
		},
		{
			name:               "invalid max pods",
			coreNum:            1,
			maxPods:            -1,
			reservedMilliCores: 0,
		},
		{
			name:               "core = 1 and max pods = 110",
			coreNum:            1,
			maxPods:            110,
			reservedMilliCores: 60,
		},
		{
			name:               "core = 1",
			coreNum:            1,
			maxPods:            MaxPods,
			reservedMilliCores: 60 + 400,
		},
		{
			name:               "core = 2",
			coreNum:            2,
			maxPods:            MaxPods,
			reservedMilliCores: 60 + 10 + 400,
		},
		{
			name:               "core = 4",
			coreNum:            4,
			maxPods:            MaxPods,
			reservedMilliCores: 60 + 10 + 5*2 + 400,
		},
		{
			name:               "core = 8",
			coreNum:            8,
			maxPods:            MaxPods,
			reservedMilliCores: 60 + 10 + 5*2 + 2.5*4 + 400,
		},
	}

	for _, tc := range testCases {
		assert.Equal(t, tc.reservedMilliCores, calculateCPUReservedInMilliCPU(tc.coreNum, tc.maxPods))
	}
}
