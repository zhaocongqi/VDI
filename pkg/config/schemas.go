package config

import (
	"fmt"

	"github.com/rancher/mapper"
	"github.com/rancher/mapper/convert"
	"gopkg.in/yaml.v3"
)

// FuzzyNames is a mapper that allows fuzzy matching of field names.
type FuzzyNames struct{}

func (f *FuzzyNames) FromInternal(data map[string]interface{})                {}
func (f *FuzzyNames) ToInternal(data map[string]interface{}) error            { return nil }
func (f *FuzzyNames) ModifySchema(s *mapper.Schema, schemas *mapper.Schemas) error { return nil }

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
