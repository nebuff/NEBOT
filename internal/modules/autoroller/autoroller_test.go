package autoroller

import (
	"testing"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
)

func TestConfiguredRoleIDsMergesLegacySingleRole(t *testing.T) {
	single := int64(300)
	cfg := guild.Default(1)
	cfg.AutoRollerRoleIDs = []int64{100, 200}
	cfg.AutoRollerRoleID = &single

	got := configuredRoleIDs(cfg)
	want := []int64{300, 100, 200}
	if len(got) != len(want) {
		t.Fatalf("configuredRoleIDs = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("configuredRoleIDs = %v, want %v", got, want)
		}
	}

	existing := int64(200)
	cfg.AutoRollerRoleID = &existing
	got = configuredRoleIDs(cfg)
	want = []int64{100, 200}
	if len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("configuredRoleIDs with existing single = %v, want %v", got, want)
	}
}

func TestAssignableRoleIDsFiltersHierarchyAndExistingRoles(t *testing.T) {
	roles := []*dg.Role{
		{ID: "10", Position: 10},
		{ID: "20", Position: 20},
		{ID: "30", Position: 5},
	}
	allowed, skipped := assignableRoleIDs(
		[]int64{10, 20, 30, 404},
		[]string{"30"},
		roles,
		15,
	)

	if len(allowed) != 1 || allowed[0] != "10" {
		t.Fatalf("allowed = %v, want [10]", allowed)
	}
	if len(skipped) != 1 || skipped[0] != "20" {
		t.Fatalf("skipped = %v, want [20]", skipped)
	}
}

func TestDashboardBuildsRoleSelectAndButtons(t *testing.T) {
	cfg := guild.Default(1)
	cfg.AutoRollerEnabled = true
	cfg.AutoRollerRoleIDs = []int64{111, 222}

	embed, components := Dashboard(cfg)
	if embed.Title != "Nebot Module: Auto-Roller Configuration" {
		t.Errorf("title = %q", embed.Title)
	}
	if embed.Color != dashboardColor {
		t.Errorf("color = %#x, want %#x", embed.Color, dashboardColor)
	}
	if len(embed.Fields) != 2 {
		t.Fatalf("fields = %d, want 2", len(embed.Fields))
	}
	if embed.Fields[0].Name != "Status" || embed.Fields[0].Value != "[ENABLED]" {
		t.Errorf("status field = %+v", embed.Fields[0])
	}
	if embed.Fields[1].Value != "<@&111>, <@&222>" {
		t.Errorf("roles field = %q", embed.Fields[1].Value)
	}

	if len(components) != 3 {
		t.Fatalf("components = %d, want 3 rows", len(components))
	}

	buttons, ok := components[0].(dg.ActionsRow)
	if !ok || len(buttons.Components) != 2 {
		t.Fatalf("button row = %#v", components[0])
	}
	toggle, ok := buttons.Components[0].(dg.Button)
	if !ok || toggle.CustomID != ToggleCustomID || toggle.Style != dg.PrimaryButton {
		t.Errorf("toggle button = %#v", buttons.Components[0])
	}
	clear, ok := buttons.Components[1].(dg.Button)
	if !ok || clear.CustomID != ClearCustomID || clear.Style != dg.SecondaryButton {
		t.Errorf("clear button = %#v", buttons.Components[1])
	}

	selectRow, ok := components[1].(dg.ActionsRow)
	if !ok || len(selectRow.Components) != 1 {
		t.Fatalf("select row = %#v", components[1])
	}
	selectMenu, ok := selectRow.Components[0].(dg.SelectMenu)
	if !ok {
		t.Fatalf("select menu type = %T", selectRow.Components[0])
	}
	if selectMenu.MenuType != dg.RoleSelectMenu || selectMenu.CustomID != RolesCustomID {
		t.Errorf("select menu = %+v", selectMenu)
	}
	if selectMenu.MinValues == nil || *selectMenu.MinValues != 1 || selectMenu.MaxValues != 10 {
		t.Errorf("select bounds = min %v max %d", selectMenu.MinValues, selectMenu.MaxValues)
	}

	backRow, ok := components[2].(dg.ActionsRow)
	if !ok || len(backRow.Components) != 1 {
		t.Fatalf("back row = %#v", components[2])
	}
	back, ok := backRow.Components[0].(dg.Button)
	if !ok || back.CustomID != BackCustomID || back.Style != dg.DangerButton {
		t.Errorf("back button = %#v", backRow.Components[0])
	}
}

func TestSafeJoinItems(t *testing.T) {
	if got := safeJoinItems(nil, 1000); got != "None" {
		t.Errorf("empty = %q, want None", got)
	}
	if got := safeJoinItems([]string{"a", "b"}, 1000); got != "a, b" {
		t.Errorf("join = %q, want a, b", got)
	}
	got := safeJoinItems([]string{"0123456789", "abcdefghij", "ABCDEFGHIJ", "klmnopqrst"}, 35)
	if got != "0123456789 ... (and 3 more)" {
		t.Errorf("truncated = %q", got)
	}
}
