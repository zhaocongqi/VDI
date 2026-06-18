package config

import (
	"fmt"

	"github.com/rancher/mapper"
	"github.com/rancher/mapper/convert"
	"gopkg.in/yaml.v3"
)

var (
	schemas = mapper.NewSchemas().Init(func(s *mapper.Schemas) *mapper.Schemas {
		s.DefaultMappers = func() []mapper.Mapper {
			return []mapper.Mapper{
				NewToMap(),
				NewToSlice(),
				NewToBool(),
				NewToInt(),
				NewToFloat(),
				&FuzzyNames{},
			}
		}
		return s
	}).MustImport(VDIConfig{})
	schema = schemas.Schema("vdiConfig")
)

func LoadVDIConfig(yamlBytes []byte) (*VDIConfig, error) {
	result := NewVDIConfig()
	data := map[string]interface{}{}
	if err := yaml.Unmarshal(yamlBytes, &data); err != nil {
		return result, fmt.Errorf("failed to unmarshal yaml: %v", err)
	}
	if err := schema.Mapper.ToInternal(data); err != nil {
		return result, err
	}
	if err := convert.ToObj(data, result); err != nil {
		return result, fmt.Errorf("failed to convert to VDIConfig: %v", err)
	}

	return result, nil
}

// LoadHarvesterConfig is a deprecated alias for LoadVDIConfig, kept for transitional compatibility.
// Deprecated: Use LoadVDIConfig instead.
func LoadHarvesterConfig(yamlBytes []byte) (*VDIConfig, error) {
	return LoadVDIConfig(yamlBytes)
}
