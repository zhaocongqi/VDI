package config

import (
	"testing"
)

func TestEscapeMustaches(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "single mustache pattern",
			input:    "{{ foo }}",
			expected: "{{ `{{ foo }}` }}",
		},
		{
			name:     "multiple mustache patterns",
			input:    "{{ foo }} and {{ bar }}",
			expected: "{{ `{{ foo }}` }} and {{ `{{ bar }}` }}",
		},
		{
			name:     "no mustache pattern",
			input:    "plain text",
			expected: "plain text",
		},
		{
			name:     "mustache pattern with variable",
			input:    "Value: {{ .Name }}",
			expected: "Value: {{ `{{ .Name }}` }}",
		},
		{
			name:     "nested braces",
			input:    "{{ range .Items }}{{ .Value }}{{ end }}",
			expected: "{{ `{{ range .Items }}` }}{{ `{{ .Value }}` }}{{ `{{ end }}` }}",
		},
		{
			name:     "empty string",
			input:    "",
			expected: "",
		},
		{
			name:     "mustache at start",
			input:    "{{ start }} continues",
			expected: "{{ `{{ start }}` }} continues",
		},
		{
			name:     "mustache at end",
			input:    "starts {{ end }}",
			expected: "starts {{ `{{ end }}` }}",
		},
		{
			name:     "spaces inside mustache",
			input:    "{{   spaces   }}",
			expected: "{{ `{{   spaces   }}` }}",
		},
		{
			name:     "complex template",
			input:    "Config: {{ .Config }}, Status: {{ .Status }}",
			expected: "Config: {{ `{{ .Config }}` }}, Status: {{ `{{ .Status }}` }}",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := escapeMustaches(tt.input)
			if result != tt.expected {
				t.Errorf("EscapeMustaches(%q) = %q, want %q", tt.input, result, tt.expected)
			}
		})
	}
}

