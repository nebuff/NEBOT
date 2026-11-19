package guild

import (
	"encoding/json"
	"reflect"
	"testing"
)

func id(value int64) *int64 { return &value }

func sampleConfig() Config {
	cfg := Default(42)
	cfg.Prefix = "?"
	cfg.Cmd = "nebot-x"
	cfg.ChannelID = id(1001)
	cfg.AdminRoleID = id(1002)
	cfg.SharedChannelID = id(1003)
	cfg.PrivateSessionsEnabled = true
	cfg.SharedEnabled = false
	cfg.NEOSEnabled = true
	cfg.NebuffModuleEnabled = true
	cfg.BattleEnabled = true
	cfg.BattleDefaultHP = 777
	cfg.BattleDamageRange = "5-50"
	cfg.BattleTimeout = 99
	cfg.MinesweeperEnabled = true
	cfg.MinesweeperDefaultMines = 6
	cfg.WarningTrackerEnabled = true
	cfg.WarningPlatforms = []string{"Discord", "Twitch"}
	cfg.WarningSeverityPoints = map[string]int64{"Low": 5}
	cfg.WarningEscalationMode = "rolling"
	cfg.WarningRollingWindowDays = 30
	cfg.WarningLadder = map[string]string{"4": "1-hour timeout"}
	cfg.WarningLogChannelID = id(1004)
	cfg.WarningDMEnabled = true
	cfg.VerificationEnabled = true
	cfg.VerificationUnverifiedRoleID = id(1005)
	cfg.VerificationVerifiedRoleID = id(1006)
	cfg.VerificationVerifiedRoleIDs = []int64{1006, 1007}
	cfg.VerificationChannelID = id(1008)
	cfg.VerificationLandingChannelID = id(1009)
	cfg.GlobalLogChannelID = id(1010)
	cfg.VerificationLogChannelID = id(1011)
	cfg.VerificationTimeout = 600
	cfg.ModRoleID = id(1012)
	cfg.AutoRollerEnabled = true
	cfg.AutoRollerRoleID = id(1013)
	cfg.AutoRollerRoleIDs = []int64{1013, 1014}
	cfg.AutoModEnabled = true
	cfg.AutoModFilters = json.RawMessage(`[{"id":"f1"}]`)
	cfg.AutoModIgnoredChannels = []int64{1015}
	cfg.AutoModIgnoredRoles = []int64{1016}
	cfg.MusicEnabled = true
	cfg.MusicRoleRestrictionEnabled = true
	cfg.MusicAllowedRoles = []int64{1017}
	cfg.MusicAllowedUsers = []int64{1018}
	cfg.MusicComponentRestrictionEnabled = true
	cfg.AnalyticsEnabled = true
	cfg.AnalyticsExcludedChannels = []int64{1019}
	cfg.VCWREnabled = true
	cfg.JoinFilterEnabled = true
	cfg.JoinFilterMinAgeValue = 7
	cfg.JoinFilterMinAgeUnit = "hours"
	cfg.JoinFilterUsernamePatterns = []string{`r:bot_\d+`}
	cfg.JoinFilterUsernameEmojis = true
	cfg.JoinFilterUsernameHomoglyphs = true
	cfg.JoinFilterEnforcement = "kick"
	cfg.JoinFilters = json.RawMessage(`[{"id":"jf1"}]`)
	cfg.AutoChannelNamerEnabled = true
	cfg.AutoChannelNamerLeft = "L"
	cfg.AutoChannelNamerRight = "R"
	cfg.AutoChannelNamerFont = "bold"
	cfg.AutoChannelNamerExcludeIDs = []int64{1020}
	cfg.PluralityEnabled = true
	cfg.SelfRolesEnabled = true
	cfg.SelfRolesGroups = json.RawMessage(`[{"name":"colors"}]`)
	return cfg
}

func TestDefaultsMatchPython(t *testing.T) {
	cfg := Default(7)

	if cfg.GuildID != 7 || cfg.Prefix != "!" || cfg.Cmd != "nebot" {
		t.Fatalf("unexpected basic defaults: %+v", cfg)
	}
	if cfg.BattleDefaultHP != 500 || cfg.BattleDamageRange != "0-100" || cfg.BattleTimeout != 180 {
		t.Errorf("battle defaults = %d, %q, %d", cfg.BattleDefaultHP, cfg.BattleDamageRange, cfg.BattleTimeout)
	}
	if cfg.MinesweeperDefaultMines != 4 {
		t.Errorf("minesweeper default = %d, want 4", cfg.MinesweeperDefaultMines)
	}
	if !reflect.DeepEqual(cfg.WarningPlatforms, []string{"Discord"}) {
		t.Errorf("warning platforms = %#v", cfg.WarningPlatforms)
	}
	if !reflect.DeepEqual(cfg.WarningSeverityPoints, map[string]int64{"Low": 1, "Medium": 2, "High": 3}) {
		t.Errorf("severity points = %#v", cfg.WarningSeverityPoints)
	}
	if cfg.WarningEscalationMode != "static" || cfg.WarningRollingWindowDays != 90 {
		t.Errorf("warning mode/window = %q/%d", cfg.WarningEscalationMode, cfg.WarningRollingWindowDays)
	}
	if cfg.WarningLadder["7"] != "Permanent ban" {
		t.Errorf("warning ladder = %#v", cfg.WarningLadder)
	}
	if cfg.VerificationTimeout != 0 || cfg.JoinFilterMinAgeUnit != "days" || cfg.JoinFilterEnforcement != "quarantine" {
		t.Errorf("verification/join defaults = %d/%q/%q", cfg.VerificationTimeout, cfg.JoinFilterMinAgeUnit, cfg.JoinFilterEnforcement)
	}
	if cfg.AutoChannelNamerLeft != "| -↳-" || cfg.AutoChannelNamerFont != "normal" {
		t.Errorf("namer defaults = %q/%q", cfg.AutoChannelNamerLeft, cfg.AutoChannelNamerFont)
	}
	if cfg.ChannelID != nil || len(cfg.VerificationVerifiedRoleIDs) != 0 {
		t.Errorf("nil/empty defaults not preserved")
	}

	// Defaults must not share mutable state between guilds.
	first := Default(1)
	second := Default(2)
	first.WarningPlatforms[0] = "changed"
	if second.WarningPlatforms[0] != "Discord" {
		t.Error("Default shares its warning platform slice")
	}
}

func TestColumnsMatchValues(t *testing.T) {
	columns := Columns()
	if len(columns) != 65 {
		t.Fatalf("got %d columns, want 65", len(columns))
	}
	if columns[0] != "guild_id" || columns[len(columns)-1] != "self_roles_groups" {
		t.Errorf("unexpected column endpoints: %q ... %q", columns[0], columns[len(columns)-1])
	}
	if got := len(Default(1).Values()); got != len(columns) {
		t.Fatalf("Values has %d entries, want %d", got, len(columns))
	}
}

func TestValuesRoundTrip(t *testing.T) {
	cfg := sampleConfig()
	values := cfg.Values()
	columns := Columns()
	if len(values) != len(columns) {
		t.Fatalf("Values has %d entries, want %d", len(values), len(columns))
	}

	row := make(map[string]any, len(columns))
	for i, column := range columns {
		row[column] = values[i]
	}

	got := FromRow(cfg.GuildID, row)
	if !reflect.DeepEqual(cfg, got) {
		t.Fatalf("round trip mismatch:\nwant: %#v\ngot:  %#v", cfg, got)
	}
}

func TestFromRowUsesDefaultsForNulls(t *testing.T) {
	got := FromRow(9, map[string]any{
		"prefix":               nil,
		"cmd":                  nil,
		"channel_id":           nil,
		"battle_default_hp":    nil,
		"warning_platforms":    nil,
		"warning_ladder":       nil,
		"verification_timeout": nil,
	})

	if got.Prefix != "!" || got.Cmd != "nebot" {
		t.Errorf("string defaults = %q/%q", got.Prefix, got.Cmd)
	}
	if got.ChannelID != nil {
		t.Errorf("channel id = %v, want nil", got.ChannelID)
	}
	if got.BattleDefaultHP != 500 {
		t.Errorf("battle hp = %d, want 500", got.BattleDefaultHP)
	}
	if !reflect.DeepEqual(got.WarningPlatforms, []string{"Discord"}) {
		t.Errorf("platforms = %#v", got.WarningPlatforms)
	}
	if got.WarningLadder["2"] != "10-minute timeout" {
		t.Errorf("ladder = %#v", got.WarningLadder)
	}
	if got.VerificationTimeout != 0 {
		t.Errorf("verification timeout = %d, want 0", got.VerificationTimeout)
	}
}

func TestFromRowParsesStoredJSON(t *testing.T) {
	got := FromRow(3, map[string]any{
		"warning_platforms":       `["Discord","Twitch"]`,
		"warning_severity_points": `{"Low":4,"High":9}`,
		"warning_ladder":          `{"2":"kick"}`,
		"automod_filters":         `[{"id":"x"}]`,
		"invalid_json":            `not json`,
	})
	if !reflect.DeepEqual(got.WarningPlatforms, []string{"Discord", "Twitch"}) {
		t.Errorf("platforms = %#v", got.WarningPlatforms)
	}
	if got.WarningSeverityPoints["High"] != 9 {
		t.Errorf("severity = %#v", got.WarningSeverityPoints)
	}
	if got.WarningLadder["2"] != "kick" {
		t.Errorf("ladder = %#v", got.WarningLadder)
	}
	if string(got.AutoModFilters) != `[{"id":"x"}]` {
		t.Errorf("filters = %s", got.AutoModFilters)
	}
}

func TestCloneIsDeep(t *testing.T) {
	original := sampleConfig()
	cloned := original.Clone()

	*cloned.ChannelID = 9999
	cloned.WarningPlatforms[0] = "changed"
	cloned.WarningSeverityPoints["Low"] = 999
	cloned.WarningLadder["4"] = "changed"
	cloned.VerificationVerifiedRoleIDs[0] = 999
	cloned.AutoModFilters[1] = 'X'

	if *original.ChannelID != 1001 {
		t.Errorf("original channel id changed to %d", *original.ChannelID)
	}
	if original.WarningPlatforms[0] != "Discord" {
		t.Errorf("original platforms changed to %#v", original.WarningPlatforms)
	}
	if original.WarningSeverityPoints["Low"] != 5 {
		t.Errorf("original severity changed to %#v", original.WarningSeverityPoints)
	}
	if original.WarningLadder["4"] != "1-hour timeout" {
		t.Errorf("original ladder changed to %#v", original.WarningLadder)
	}
	if original.VerificationVerifiedRoleIDs[0] != 1006 {
		t.Errorf("original verified role ids changed to %#v", original.VerificationVerifiedRoleIDs)
	}
	if string(original.AutoModFilters) != `[{"id":"f1"}]` {
		t.Errorf("original filters changed to %s", original.AutoModFilters)
	}
}
