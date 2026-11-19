package fun

import (
	"testing"
)

func TestExtractGrokQuery(t *testing.T) {
	tests := []struct {
		name    string
		content string
		query   string
		ok      bool
	}{
		{name: "bare trigger", content: "@grok", query: "", ok: true},
		{name: "prefix query", content: "@grok is this true?", query: "is this true?", ok: true},
		{name: "suffix trigger", content: "is this true? @grok", query: "is this true?", ok: true},
		{name: "case insensitive", content: "@GROK 67", query: "67", ok: true},
		{name: "word boundary", content: "@grokking is this true?", ok: false},
		{name: "no trigger", content: "hello there", ok: false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			query, ok := extractQuery(tt.content)
			if ok != tt.ok || query != tt.query {
				t.Errorf("extractQuery(%q) = %q, %v; want %q, %v", tt.content, query, ok, tt.query, tt.ok)
			}
		})
	}
}

func TestGrokReplyCategories(t *testing.T) {
	module := NewGrok(nil)
	module.pick = func(int) int { return 0 }

	tests := []struct {
		name  string
		query string
		want  string
	}{
		{name: "empty", query: "", want: repliesGeneral[0]},
		{name: "is this true", query: "is this true?", want: repliesIsThisTrue[0]},
		{name: "repeated true", query: "IS THIS TRUE IS THIS TRUE??????", want: repliesIsThisTrue[0]},
		{name: "67", query: "67", want: replies67[0]},
		{name: "number", query: "42", want: repliesNumbers[0]},
		{name: "question", query: "why is the sky blue?", want: repliesQuestions[0]},
		{name: "general", query: "hello", want: repliesGeneral[0]},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := module.replyFor(tt.query); got != tt.want {
				t.Errorf("replyFor(%q) = %q, want %q", tt.query, got, tt.want)
			}
		})
	}
}

func TestGrokRepliesContainNoEmoji(t *testing.T) {
	lists := map[string][]string{
		"is this true": repliesIsThisTrue,
		"67":           replies67,
		"numbers":      repliesNumbers,
		"questions":    repliesQuestions,
		"general":      repliesGeneral,
	}
	for name, replies := range lists {
		for _, reply := range replies {
			if containsEmoji(reply) {
				t.Errorf("%s reply contains an emoji: %q", name, reply)
			}
		}
	}
}

func TestContainsEmoji(t *testing.T) {
	tests := []struct {
		text string
		want bool
	}{
		{text: "", want: false},
		{text: "Hello, World!", want: false},
		{text: "Is this true?", want: false},
		{text: "<:custom_emoji:1234567890>", want: true},
		{text: "<a:animated_emoji:0987654321>", want: true},
		{text: "Hello \U0001F600", want: true},
	}
	for _, tt := range tests {
		if got := containsEmoji(tt.text); got != tt.want {
			t.Errorf("containsEmoji(%q) = %v, want %v", tt.text, got, tt.want)
		}
	}
}
