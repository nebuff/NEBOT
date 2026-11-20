package admin

import (
	"testing"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
	analyticsui "github.com/nebuff/n-bot/internal/modules/analytics"
	"github.com/nebuff/n-bot/internal/modules/autoroller"
	selfrolesui "github.com/nebuff/n-bot/internal/modules/selfroles"
)

func TestBuildModulesShowsStatusesAndAutoRollerButton(t *testing.T) {
	cfg := guild.Default(1)
	cfg.AutoRollerEnabled = true
	cfg.AnalyticsEnabled = true
	cfg.SelfRolesEnabled = true
	cfg.AutoModEnabled = true

	embed, components := buildModules(cfg)
	if embed.Title != "Nebot Module Manager" {
		t.Errorf("title = %q", embed.Title)
	}
	if len(embed.Fields) != 14 {
		t.Fatalf("fields = %d, want 14", len(embed.Fields))
	}

	statuses := make(map[string]string, len(embed.Fields))
	for _, field := range embed.Fields {
		statuses[field.Name] = field.Value
	}
	if statuses["Auto-Roller Module"] != "[ENABLED]" {
		t.Errorf("auto-roller status = %q", statuses["Auto-Roller Module"])
	}
	if statuses["AutoMod Module"] != "[ENABLED]" {
		t.Errorf("automod status = %q", statuses["AutoMod Module"])
	}
	if statuses["Music Module"] != "[DISABLED]" {
		t.Errorf("music status = %q", statuses["Music Module"])
	}

	if len(components) != 1 {
		t.Fatalf("components = %d, want 1 row", len(components))
	}
	row, ok := components[0].(dg.ActionsRow)
	if !ok || len(row.Components) != 3 {
		t.Fatalf("row = %#v", components[0])
	}
	button, ok := row.Components[0].(dg.Button)
	if !ok {
		t.Fatalf("button type = %T", row.Components[0])
	}
	if button.CustomID != autoroller.OpenCustomID {
		t.Errorf("custom id = %q", button.CustomID)
	}
	if button.Style != dg.SuccessButton {
		t.Errorf("enabled style = %v, want success", button.Style)
	}
	analyticsButton, ok := row.Components[1].(dg.Button)
	if !ok {
		t.Fatalf("analytics button type = %T", row.Components[1])
	}
	if analyticsButton.CustomID != analyticsui.OpenCustomID {
		t.Errorf("analytics custom id = %q", analyticsButton.CustomID)
	}
	if analyticsButton.Style != dg.SuccessButton {
		t.Errorf("analytics enabled style = %v, want success", analyticsButton.Style)
	}
	selfRolesButton, ok := row.Components[2].(dg.Button)
	if !ok {
		t.Fatalf("self roles button type = %T", row.Components[2])
	}
	if selfRolesButton.CustomID != selfrolesui.OpenCustomID {
		t.Errorf("self roles custom id = %q", selfRolesButton.CustomID)
	}
	if selfRolesButton.Style != dg.SuccessButton {
		t.Errorf("self roles enabled style = %v, want success", selfRolesButton.Style)
	}

	cfg.AutoRollerEnabled = false
	cfg.AnalyticsEnabled = false
	cfg.SelfRolesEnabled = false
	_, components = buildModules(cfg)
	row = components[0].(dg.ActionsRow)
	button = row.Components[0].(dg.Button)
	if button.Style != dg.DangerButton {
		t.Errorf("disabled style = %v, want danger", button.Style)
	}
	analyticsButton = row.Components[1].(dg.Button)
	if analyticsButton.Style != dg.DangerButton {
		t.Errorf("analytics disabled style = %v, want danger", analyticsButton.Style)
	}
	selfRolesButton = row.Components[2].(dg.Button)
	if selfRolesButton.Style != dg.DangerButton {
		t.Errorf("self roles disabled style = %v, want danger", selfRolesButton.Style)
	}
}
