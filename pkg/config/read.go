package config

import (
	"fmt"
	"os"
	"strings"

	"github.com/rancher/mapper/convert"

	"vdi-installer/pkg/util"
)

const (
	kernelParamPrefix   = "vdi"
	defaultUserDataFile = "/oem/userdata.yaml"
)

// ReadConfig constructs a config by reading various sources
func ReadConfig() (VDIConfig, error) {
	data, err := util.ReadCmdline(kernelParamPrefix)
	if err != nil {
		config := NewVDIConfig()
		return *config, err
	}
	return readConfigFromMap(data)
}

func ToEnv(prefix string, obj interface{}) ([]string, error) {
	data, err := convert.EncodeToMap(obj)
	if err != nil {
		return nil, err
	}

	return mapToEnv(prefix, data), nil
}

func mapToEnv(prefix string, data map[string]interface{}) []string {
	var result []string
	for k, v := range data {
		keyName := strings.ToUpper(prefix + convert.ToYAMLKey(k))
		if data, ok := v.(map[string]interface{}); ok {
			subResult := mapToEnv(keyName+"_", data)
			result = append(result, subResult...)
		} else {
			result = append(result, fmt.Sprintf("%s=%v", keyName, v))
		}
	}
	return result
}

// ReadUserDataConfig constructs a config from userdata
func ReadUserDataConfig() (VDIConfig, error) {
	return readUserData(defaultUserDataFile)
}

func readUserData(fileName string) (VDIConfig, error) {
	result := NewVDIConfig()
	_, err := os.Stat(fileName)

	if os.IsNotExist(err) {
		return *result, nil
	} else if err != nil {
		return *result, err
	}

	contents, err := os.ReadFile(fileName) //nolint:gosec
	if err != nil {
		return *result, err
	}

	tidyContents, err := cleanupFile(contents)
	if err != nil {
		return *result, err
	}
	result, err = LoadVDIConfig(tidyContents)
	return *result, err
}

func cleanupFile(content []byte) ([]byte, error) {
	lines := strings.Split(string(content), "\n")
	var config []string
	for _, v := range lines {
		if v != "#cloud-config" && v != "#!cloud-config" {
			config = append(config, v)
		}
	}

	return []byte(strings.Join(config, "\n")), nil
}

func snakeToCamel(s string) string {
	if s == "vlan_id" {
		return "vlanId"
	}
	parts := strings.Split(s, "_")
	for i := 1; i < len(parts); i++ {
		if len(parts[i]) > 0 {
			parts[i] = strings.ToUpper(parts[i][:1]) + parts[i][1:]
		}
	}
	return strings.Join(parts, "")
}

func normalizeMapKeys(m map[string]any) map[string]any {
	result := make(map[string]any)
	for k, v := range m {
		newKey := snakeToCamel(k)
		if newKey == "sysctl" {
			newKey = "sysctls"
		}
		// Specific dictionary maps must preserve their original keys (e.g. http_proxy, kernel.printk)
		if k == "sysctl" || k == "sysctls" || k == "environment" || k == "labels" || k == "bond_options" || k == "headers" {
			if subMap, ok := v.(map[string]any); ok {
				result[newKey] = subMap
			} else if subMapInterface, ok := v.(map[interface{}]interface{}); ok {
				tempMap := make(map[string]any)
				for sk, sv := range subMapInterface {
					tempMap[fmt.Sprintf("%v", sk)] = sv
				}
				result[newKey] = tempMap
			} else {
				result[newKey] = v
			}
			continue
		}

		if subMap, ok := v.(map[string]any); ok {
			result[newKey] = normalizeMapKeys(subMap)
		} else if subMapInterface, ok := v.(map[interface{}]interface{}); ok {
			tempMap := make(map[string]any)
			for sk, sv := range subMapInterface {
				tempMap[fmt.Sprintf("%v", sk)] = sv
			}
			result[newKey] = normalizeMapKeys(tempMap)
		} else {
			result[newKey] = v
		}
	}
	return result
}

func readConfigFromMap(data map[string]any) (VDIConfig, error) {
	data = normalizeMapKeys(data)
	config := NewVDIConfig()
	err := schema.Mapper.ToInternal(data)
	if err != nil {
		return *config, err
	}
	err = convert.ToObj(data, config)
	return *config, err
}
