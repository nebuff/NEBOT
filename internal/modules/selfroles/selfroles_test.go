package selfroles

import (
	"encoding/json"
	"strings"
	"testing"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
)

func TestParseGroupsAppliesPythonDefaultsAndRoundTrips(t *testing.T) {
	raw := json.RawMessage(`[{"name":"Pronouns","roles":[{"role_id":101,"name":"He/Him"}]}]`)
	groups, err := ParseGroups(raw)
	if err != nil {
		t.Fatal(err)
	}
	if len(groups) != 1 {
		t.Fatalf("groups = %d, want 1", len(groups))
	}
	group := groups[0]
	if group.Mode != ModeNone || !group.AutoTakeAway || group.RequireOne {
		t.Errorf("group defaults = %+v", group)
	}
	if group.Color != ColorBlue {
		t.Errorf("color = %q", group.Color)
	}
	if len(group.Roles) != 1 || !group.Roles[0].AllowTakeOff || group.Roles[0].Style != StyleBlurple {
		t.Errorf("role defaults = %+v", group.Roles)
	}

	encoded, err := MarshalGroups(groups)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := ParseGroups(encoded)
	if err != nil {
		t.Fatal(err)
	}
	if len(decoded) != 1 || decoded[0].Name != "Pronouns" || decoded[0].Roles[0].RoleID != 101 {
		t.Fatalf("decoded = %+v", decoded)
	}
}

func TestNewGroupValidation(t *testing.T) {
	group, err := NewGroup("Pronouns", "single")
	if err != nil {
		t.Fatal(err)
	}
	if group.Mode != ModeSingle || !group.AutoTakeAway || group.Roles == nil {
		t.Errorf("group = %+v", group)
	}
	if _, err := NewGroup("x", "none"); err == nil {
		t.Error("expected short-name error")
	}
	if _, err := NewGroup("Valid", "invalid"); err == nil {
		t.Error("expected invalid-mode error")
	}
}

func TestPlanToggleRequirementsAndSingleMode(t *testing.T) {
	roles := map[int64]RoleInfo{
		100: {Name: "He/Him", Exists: true},
		101: {Name: "RoleA", Exists: true},
		102: {Name: "RoleB", Exists: true},
		200: {Name: "MemberRole", Exists: true},
	}
	group := Group{
		Name:         "Pronouns",
		Mode:         ModeSingle,
		AutoTakeAway: true,
		RequireOne:   true,
		RequireRoles: []int64{200},
		Roles: []Role{
			{RoleID: 101, Name: "RoleA", AllowTakeOff: true},
			{RoleID: 102, Name: "RoleB", AllowTakeOff: true},
		},
	}

	decision, allowed := PlanToggle(true, group, group.Roles[0], nil, roles, true)
	if allowed || !strings.Contains(decision.Message, "MemberRole") {
		t.Fatalf("requirement decision = %+v allowed=%v", decision, allowed)
	}

	decision, allowed = PlanToggle(true, group, group.Roles[1], []string{"200", "101"}, roles, true)
	if !allowed || !decision.Add || len(decision.RemoveIDs) != 1 || decision.RemoveIDs[0] != 101 {
		t.Fatalf("replacement decision = %+v allowed=%v", decision, allowed)
	}
	if decision.Message != "Granted role: **RoleB** (and removed RoleA)" {
		t.Errorf("message = %q", decision.Message)
	}

	decision, allowed = PlanToggle(true, group, group.Roles[0], []string{"200", "101"}, roles, true)
	if allowed || decision.Message != "You must keep at least one role from this group." {
		t.Fatalf("require-one decision = %+v allowed=%v", decision, allowed)
	}

	group.RequireRoles = nil
	decision, allowed = PlanToggle(true, group, group.Roles[0], []string{"200", "101", "102"}, roles, true)
	if !allowed || decision.Add || len(decision.RemoveIDs) != 1 || decision.RemoveIDs[0] != 101 {
		t.Fatalf("removal decision = %+v allowed=%v", decision, allowed)
	}
	if decision.Message != "Removed role: **RoleA**" {
		t.Errorf("message = %q", decision.Message)
	}
}

func TestPlanToggleMultiLimitsAndTakeOff(t *testing.T) {
	roles := map[int64]RoleInfo{
		101: {Name: "RoleA", Exists: true},
		102: {Name: "RoleB", Exists: true},
		103: {Name: "RoleC", Exists: true},
	}
	group := Group{
		Name:      "Roles",
		Mode:      ModeMulti,
		MinAmount: 1,
		MaxAmount: 2,
		Roles: []Role{
			{RoleID: 101, Name: "RoleA", AllowTakeOff: true},
			{RoleID: 102, Name: "RoleB", AllowTakeOff: true},
			{RoleID: 103, Name: "RoleC", AllowTakeOff: true},
		},
	}

	decision, allowed := PlanToggle(true, group, group.Roles[2], []string{"101", "102"}, roles, true)
	if !allowed || !decision.Add || len(decision.RemoveIDs) != 1 || decision.RemoveIDs[0] != 101 {
		t.Fatalf("max decision = %+v allowed=%v", decision, allowed)
	}
	if decision.Message != "Granted role: **RoleC** (and removed RoleA)" {
		t.Errorf("message = %q", decision.Message)
	}

	decision, allowed = PlanToggle(true, group, group.Roles[1], []string{"102"}, roles, true)
	if allowed || decision.Message != "You must keep at least 1 roles from this group." {
		t.Fatalf("min decision = %+v allowed=%v", decision, allowed)
	}

	locked := group
	locked.Mode = ModeNone
	locked.Roles = []Role{{RoleID: 101, Name: "RoleA", AllowTakeOff: false}}
	decision, allowed = PlanToggle(true, locked, locked.Roles[0], []string{"101"}, roles, true)
	if allowed || decision.Message != "This role cannot be removed once assigned." {
		t.Fatalf("take-off decision = %+v allowed=%v", decision, allowed)
	}
}

func TestGroupKeyAndLegacyCustomID(t *testing.T) {
	if GroupKey("Pronouns") == "" || GroupKey("Pronouns") != GroupKey("Pronouns") {
		t.Error("group key is not stable")
	}
	if GroupKey("Pronouns") == GroupKey("pronouns") {
		t.Error("group key should be case-sensitive like the Python name lookup")
	}

	guildID, name, roleID, err := parseLegacyCustomID("self_role:123:My Group:456")
	if err != nil {
		t.Fatal(err)
	}
	if guildID != "123" || name != "My Group" || roleID != 456 {
		t.Errorf("legacy = %q %q %d", guildID, name, roleID)
	}

	key, parsedRole, err := roleFromCustomID("selfroles:role:"+GroupKey("Pronouns")+":456", RoleTogglePrefix)
	if err != nil {
		t.Fatal(err)
	}
	if key != GroupKey("Pronouns") || parsedRole != 456 {
		t.Errorf("new role id = %q %d", key, parsedRole)
	}
}

func TestDashboardsAndRoleMenu(t *testing.T) {
	cfg := guild.Default(1)
	cfg.SelfRolesEnabled = true
	groups := []Group{
		{Name: "Pronouns", Mode: ModeSingle, Color: ColorGreen, Roles: []Role{{RoleID: 101, Name: "He/Him", Style: StyleGreen}}},
		{Name: "Colors", Mode: ModeMulti},
	}

	embed, components := moduleDashboard(cfg, groups)
	if embed.Title != "Nebot Module: Self-Assignable Roles" {
		t.Errorf("title = %q", embed.Title)
	}
	if len(embed.Fields) != 3 || embed.Fields[0].Value != "[ENABLED]" {
		t.Errorf("fields = %+v", embed.Fields)
	}
	if len(components) != 3 {
		t.Fatalf("module components = %d, want 3 rows", len(components))
	}
	groupSelectRow, ok := components[1].(dg.ActionsRow)
	if !ok {
		t.Fatalf("group select row = %T", components[1])
	}
	groupSelect, ok := groupSelectRow.Components[0].(dg.SelectMenu)
	if !ok || groupSelect.CustomID != GroupSelectCustomID || len(groupSelect.Options) != 2 {
		t.Errorf("group select = %+v", groupSelectRow.Components[0])
	}

	_, groupComponents := groupDashboard(groups[0], GroupKey(groups[0].Name))
	if len(groupComponents) != 5 {
		t.Fatalf("group components = %d, want 5 rows", len(groupComponents))
	}

	menuEmbed, menuComponents := roleMenu(groups[0], GroupKey(groups[0].Name))
	if menuEmbed.Title != "Self-Assignable Roles: Pronouns" || menuEmbed.Color != 0x2ECC71 {
		t.Errorf("menu embed = %+v", menuEmbed)
	}
	if len(menuComponents) != 1 {
		t.Fatalf("menu components = %d, want 1 row", len(menuComponents))
	}
	menuRow := menuComponents[0].(dg.ActionsRow)
	button, ok := menuRow.Components[0].(dg.Button)
	if !ok || button.CustomID != roleToggleID(GroupKey("Pronouns"), 101) || button.Style != dg.SuccessButton {
		t.Errorf("menu button = %+v", menuRow.Components[0])
	}

	_, styleComponents := styleDashboard(groups[0], GroupKey(groups[0].Name), 101)
	if len(styleComponents) != 3 {
		t.Fatalf("style components = %d, want 3 rows", len(styleComponents))
	}
	colorRow := styleComponents[1].(dg.ActionsRow)
	colorMenu := colorRow.Components[0].(dg.SelectMenu)
	if colorMenu.CustomID != styleColorID(GroupKey("Pronouns"), 101) {
		t.Errorf("color custom id = %q", colorMenu.CustomID)
	}
}
