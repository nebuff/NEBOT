package fun

import "testing"

func TestConvertNebuffText(t *testing.T) {
	tests := []struct {
		name string
		text string
		want string
		ok   bool
	}{
		{name: "one nebuff", text: "i am 1 nebuff", want: "That would be 1.37 meters", ok: true},
		{name: "plural nebuff", text: "1.5 nebuffs", want: "That would be 2.06 meters", ok: true},
		{name: "apostrophe nebuff", text: "1 nebuff's", want: "That would be 1.37 meters", ok: true},
		{name: "feet and inches", text: `i am 5'11"`, want: "That would be 1.31 nebuff's", ok: true},
		{name: "centimeters", text: "180 cm", want: "That would be 1.31 nebuff's", ok: true},
		{name: "feet", text: "6 feet", want: "That would be 1.33 nebuff's", ok: true},
		{name: "inches", text: "70 inches", want: "That would be 1.3 nebuff's", ok: true},
		{name: "no measurement", text: "hello there", ok: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, ok := convertNebuffText(tt.text)
			if ok != tt.ok || got != tt.want {
				t.Errorf("convertNebuffText(%q) = %q, %v; want %q, %v", tt.text, got, ok, tt.want, tt.ok)
			}
		})
	}
}

func TestFormatPythonFloat(t *testing.T) {
	tests := []struct {
		value float64
		want  string
	}{
		{value: 0, want: "0.0"},
		{value: 2, want: "2.0"},
		{value: 1.37, want: "1.37"},
		{value: 1.3, want: "1.3"},
	}
	for _, tt := range tests {
		if got := formatPythonFloat(tt.value); got != tt.want {
			t.Errorf("formatPythonFloat(%v) = %q, want %q", tt.value, got, tt.want)
		}
	}
}
