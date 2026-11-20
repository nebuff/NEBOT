package analytics

import (
	"strings"
	"testing"
	"time"

	dg "github.com/bwmarrin/discordgo"

	analyticsdata "github.com/nebuff/n-bot/internal/analytics"
	"github.com/nebuff/n-bot/internal/guild"
)

func TestDashboardBuildsButtonsAndExcludedChannels(t *testing.T) {
	cfg := guild.Default(1)
	cfg.AnalyticsEnabled = true
	cfg.AnalyticsExcludedChannels = []int64{111, 222}

	embed, components := Dashboard(cfg)
	if embed.Title != "Nebot Module: Server Analytics" {
		t.Errorf("title = %q", embed.Title)
	}
	if len(embed.Fields) != 2 {
		t.Fatalf("fields = %d, want 2", len(embed.Fields))
	}
	if embed.Fields[0].Value != "[ENABLED]" {
		t.Errorf("status = %q", embed.Fields[0].Value)
	}
	if embed.Fields[1].Value != "<#111>, <#222>" {
		t.Errorf("excluded = %q", embed.Fields[1].Value)
	}

	if len(components) != 2 {
		t.Fatalf("components = %d, want 2 rows", len(components))
	}
	first, ok := components[0].(dg.ActionsRow)
	if !ok || len(first.Components) != 2 {
		t.Fatalf("first row = %#v", components[0])
	}
	toggle, ok := first.Components[0].(dg.Button)
	if !ok || toggle.CustomID != ToggleCustomID {
		t.Errorf("toggle = %#v", first.Components[0])
	}
	exclude, ok := first.Components[1].(dg.Button)
	if !ok || exclude.CustomID != ExcludeCustomID {
		t.Errorf("exclude = %#v", first.Components[1])
	}

	second, ok := components[1].(dg.ActionsRow)
	if !ok || len(second.Components) != 2 {
		t.Fatalf("second row = %#v", components[1])
	}
	clear, ok := second.Components[0].(dg.Button)
	if !ok || clear.CustomID != ClearCustomID || clear.Style != dg.DangerButton {
		t.Errorf("clear = %#v", second.Components[0])
	}
	back, ok := second.Components[1].(dg.Button)
	if !ok || back.CustomID != BackCustomID {
		t.Errorf("back = %#v", second.Components[1])
	}
}

func TestExcludeComponentsUseChannelSelect(t *testing.T) {
	components := excludeComponents()
	if len(components) != 2 {
		t.Fatalf("components = %d, want 2 rows", len(components))
	}
	row, ok := components[0].(dg.ActionsRow)
	if !ok || len(row.Components) != 1 {
		t.Fatalf("row = %#v", components[0])
	}
	menu, ok := row.Components[0].(dg.SelectMenu)
	if !ok {
		t.Fatalf("menu type = %T", row.Components[0])
	}
	if menu.MenuType != dg.ChannelSelectMenu || menu.CustomID != ChannelsCustomID {
		t.Errorf("menu = %+v", menu)
	}
	if menu.MinValues == nil || *menu.MinValues != 0 || menu.MaxValues != 25 {
		t.Errorf("bounds = min %v max %d", menu.MinValues, menu.MaxValues)
	}
	if len(menu.ChannelTypes) != 3 {
		t.Errorf("channel types = %v", menu.ChannelTypes)
	}
}

func TestReportEmbed(t *testing.T) {
	report := analyticsdata.Report{
		TotalMessages:       10,
		PeakHour:            time.Date(2026, 11, 19, 10, 0, 0, 0, time.UTC),
		PeakCount:           7,
		MostActiveChannelID: "123",
		MostActiveCount:     6,
		MostActivePercent:   60,
		Joins:               3,
		Leaves:              1,
		NetGrowth:           2,
		VoicePeak:           5,
		VoiceAverage:        2.5,
	}

	embed := reportEmbed("Test Guild", report)
	if embed.Title != "Server Analytics Report for Test Guild" {
		t.Errorf("title = %q", embed.Title)
	}
	if len(embed.Fields) != 3 {
		t.Fatalf("fields = %d, want 3", len(embed.Fields))
	}
	if !strings.Contains(embed.Fields[0].Value, "Total Messages Processed: 10") {
		t.Errorf("chat field = %q", embed.Fields[0].Value)
	}
	if !strings.Contains(embed.Fields[0].Value, "Peak Message Hour: 10:00 UTC with 7 messages") {
		t.Errorf("chat field = %q", embed.Fields[0].Value)
	}
	if !strings.Contains(embed.Fields[0].Value, "<#123> (60.0% of total volume)") {
		t.Errorf("chat field = %q", embed.Fields[0].Value)
	}
	if !strings.Contains(embed.Fields[1].Value, "Net Growth: 2") {
		t.Errorf("churn field = %q", embed.Fields[1].Value)
	}
	if !strings.Contains(embed.Fields[2].Value, "Average Voice Concurrency: 2.5 members") {
		t.Errorf("voice field = %q", embed.Fields[2].Value)
	}
}

func TestCountVoiceMembers(t *testing.T) {
	guildState := &dg.Guild{
		Channels: []*dg.Channel{
			{ID: "voice-1", Type: dg.ChannelTypeGuildVoice},
			{ID: "text-1", Type: dg.ChannelTypeGuildText},
		},
		VoiceStates: []*dg.VoiceState{
			{ChannelID: "voice-1", Member: &dg.Member{User: &dg.User{ID: "1"}}},
			{ChannelID: "voice-1", Member: &dg.Member{User: &dg.User{ID: "2", Bot: true}}},
			{ChannelID: "text-1", Member: &dg.Member{User: &dg.User{ID: "3"}}},
			{ChannelID: "voice-1", UserID: "4"},
		},
	}
	lookup := func(userID string) *dg.Member {
		if userID == "4" {
			return &dg.Member{User: &dg.User{ID: "4"}}
		}
		return nil
	}

	if got := countVoiceMembers(guildState, lookup); got != 2 {
		t.Errorf("count = %d, want 2", got)
	}
}
