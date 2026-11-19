// Package guild models per-guild configuration and provides a cached,
// PostgreSQL-backed accessor.
package guild

import (
	"encoding/json"
	"maps"
	"slices"
	"strconv"
)

// Config mirrors one row of guild_configs. Discord IDs are stored as int64;
// nil pointers represent SQL NULL (Python None).
type Config struct {
	GuildID int64
	Prefix  string
	Cmd     string

	ChannelID       *int64
	AdminRoleID     *int64
	SharedChannelID *int64

	PrivateSessionsEnabled bool
	SharedEnabled          bool
	NEOSEnabled            bool
	NebuffModuleEnabled    bool

	BattleEnabled     bool
	BattleDefaultHP   int64
	BattleDamageRange string
	BattleTimeout     int64

	MinesweeperEnabled      bool
	MinesweeperDefaultMines int64

	WarningTrackerEnabled    bool
	WarningPlatforms         []string
	WarningSeverityPoints    map[string]int64
	WarningEscalationMode    string
	WarningRollingWindowDays int64
	WarningLadder            map[string]string
	WarningLogChannelID      *int64
	WarningDMEnabled         bool

	VerificationEnabled          bool
	VerificationUnverifiedRoleID *int64
	VerificationVerifiedRoleID   *int64
	VerificationVerifiedRoleIDs  []int64
	VerificationChannelID        *int64
	VerificationLandingChannelID *int64
	GlobalLogChannelID           *int64
	VerificationLogChannelID     *int64
	VerificationTimeout          int64

	ModRoleID *int64

	AutoRollerEnabled bool
	AutoRollerRoleID  *int64
	AutoRollerRoleIDs []int64

	AutoModEnabled         bool
	AutoModFilters         json.RawMessage
	AutoModIgnoredChannels []int64
	AutoModIgnoredRoles    []int64

	MusicEnabled                     bool
	MusicRoleRestrictionEnabled      bool
	MusicAllowedRoles                []int64
	MusicAllowedUsers                []int64
	MusicComponentRestrictionEnabled bool

	AnalyticsEnabled          bool
	AnalyticsExcludedChannels []int64

	VCWREnabled bool

	JoinFilterEnabled            bool
	JoinFilterMinAgeValue        int64
	JoinFilterMinAgeUnit         string
	JoinFilterUsernamePatterns   []string
	JoinFilterUsernameEmojis     bool
	JoinFilterUsernameHomoglyphs bool
	JoinFilterEnforcement        string
	JoinFilters                  json.RawMessage

	AutoChannelNamerEnabled    bool
	AutoChannelNamerLeft       string
	AutoChannelNamerRight      string
	AutoChannelNamerFont       string
	AutoChannelNamerExcludeIDs []int64

	PluralityEnabled bool

	SelfRolesEnabled bool
	SelfRolesGroups  json.RawMessage
}

// columnNames mirrors the PostgreSQL column order. Values() must stay in sync.
var columnNames = []string{
	"guild_id", "prefix", "cmd", "channel_id", "admin_role_id", "shared_channel_id",
	"private_sessions_enabled", "shared_enabled", "ne_os_enabled", "nebuff_module_enabled",
	"battle_enabled", "battle_default_hp", "battle_damage_range", "battle_timeout",
	"minesweeper_enabled", "minesweeper_default_mines",
	"warning_tracker_enabled", "warning_platforms", "warning_severity_points",
	"warning_escalation_mode", "warning_rolling_window_days", "warning_ladder",
	"warning_log_channel_id", "warning_dm_enabled",
	"verification_enabled", "verification_unverified_role_id", "verification_verified_role_id",
	"verification_verified_role_ids", "verification_channel_id", "verification_landing_channel_id",
	"global_log_channel_id", "verification_log_channel_id", "verification_timeout",
	"mod_role_id",
	"auto_roller_enabled", "auto_roller_role_id", "auto_roller_role_ids",
	"automod_enabled", "automod_filters", "automod_ignored_channels", "automod_ignored_roles",
	"music_enabled", "music_role_restriction_enabled", "music_allowed_roles", "music_allowed_users",
	"music_component_restriction_enabled",
	"analytics_enabled", "analytics_excluded_channels",
	"vc_wr_enabled",
	"join_filter_enabled", "join_filter_min_age_value", "join_filter_min_age_unit",
	"join_filter_username_patterns", "join_filter_username_emojis",
	"join_filter_username_homoglyphs", "join_filter_enforcement", "join_filters",
	"auto_channel_namer_enabled", "auto_channel_namer_left", "auto_channel_namer_right",
	"auto_channel_namer_font", "auto_channel_namer_exclude_ids",
	"plurality_enabled",
	"self_roles_enabled", "self_roles_groups",
}

// Columns returns the database column order used by Values.
func Columns() []string {
	return slices.Clone(columnNames)
}

// Default returns the same defaults as configuration_module.get_guild_config.
// Slices and maps are freshly allocated for every call.
func Default(guildID int64) Config {
	return Config{
		GuildID: guildID,
		Prefix:  "!",
		Cmd:     "nebot",

		BattleDefaultHP:   500,
		BattleDamageRange: "0-100",
		BattleTimeout:     180,

		MinesweeperDefaultMines: 4,

		WarningPlatforms:         []string{"Discord"},
		WarningSeverityPoints:    map[string]int64{"Low": 1, "Medium": 2, "High": 3},
		WarningEscalationMode:    "static",
		WarningRollingWindowDays: 90,
		WarningLadder: map[string]string{
			"2": "10-minute timeout",
			"3": "1-hour timeout",
			"5": "1-day timeout",
			"7": "Permanent ban",
		},

		VerificationVerifiedRoleIDs: []int64{},

		AutoRollerRoleIDs: []int64{},

		AutoModFilters:         json.RawMessage("[]"),
		AutoModIgnoredChannels: []int64{},
		AutoModIgnoredRoles:    []int64{},

		MusicAllowedRoles: []int64{},
		MusicAllowedUsers: []int64{},

		AnalyticsExcludedChannels: []int64{},

		JoinFilterMinAgeUnit:       "days",
		JoinFilterUsernamePatterns: []string{},
		JoinFilterEnforcement:      "quarantine",
		JoinFilters:                json.RawMessage("[]"),

		AutoChannelNamerLeft:       "| -↳-",
		AutoChannelNamerRight:      "",
		AutoChannelNamerFont:       "normal",
		AutoChannelNamerExcludeIDs: []int64{},

		SelfRolesGroups: json.RawMessage("[]"),
	}
}

// FromRow builds a Config from a guild_configs row, applying defaults for NULL
// scalar values. JSON values are parsed into typed fields; malformed JSON falls
// back to the default rather than failing the whole guild.
func FromRow(guildID int64, row map[string]any) Config {
	cfg := Default(guildID)

	cfg.Prefix = stringValue(row, "prefix", cfg.Prefix)
	cfg.Cmd = stringValue(row, "cmd", cfg.Cmd)

	cfg.ChannelID = idValue(row, "channel_id", cfg.ChannelID)
	cfg.AdminRoleID = idValue(row, "admin_role_id", cfg.AdminRoleID)
	cfg.SharedChannelID = idValue(row, "shared_channel_id", cfg.SharedChannelID)

	cfg.PrivateSessionsEnabled = boolValue(row, "private_sessions_enabled", cfg.PrivateSessionsEnabled)
	cfg.SharedEnabled = boolValue(row, "shared_enabled", cfg.SharedEnabled)
	cfg.NEOSEnabled = boolValue(row, "ne_os_enabled", cfg.NEOSEnabled)
	cfg.NebuffModuleEnabled = boolValue(row, "nebuff_module_enabled", cfg.NebuffModuleEnabled)

	cfg.BattleEnabled = boolValue(row, "battle_enabled", cfg.BattleEnabled)
	cfg.BattleDefaultHP = intValue(row, "battle_default_hp", cfg.BattleDefaultHP)
	cfg.BattleDamageRange = stringValue(row, "battle_damage_range", cfg.BattleDamageRange)
	cfg.BattleTimeout = intValue(row, "battle_timeout", cfg.BattleTimeout)

	cfg.MinesweeperEnabled = boolValue(row, "minesweeper_enabled", cfg.MinesweeperEnabled)
	cfg.MinesweeperDefaultMines = intValue(row, "minesweeper_default_mines", cfg.MinesweeperDefaultMines)

	cfg.WarningTrackerEnabled = boolValue(row, "warning_tracker_enabled", cfg.WarningTrackerEnabled)
	cfg.WarningPlatforms = stringSliceValue(row, "warning_platforms", cfg.WarningPlatforms)
	cfg.WarningSeverityPoints = stringInt64MapValue(row, "warning_severity_points", cfg.WarningSeverityPoints)
	cfg.WarningEscalationMode = stringValue(row, "warning_escalation_mode", cfg.WarningEscalationMode)
	cfg.WarningRollingWindowDays = intValue(row, "warning_rolling_window_days", cfg.WarningRollingWindowDays)
	cfg.WarningLadder = stringStringMapValue(row, "warning_ladder", cfg.WarningLadder)
	cfg.WarningLogChannelID = idValue(row, "warning_log_channel_id", cfg.WarningLogChannelID)
	cfg.WarningDMEnabled = boolValue(row, "warning_dm_enabled", cfg.WarningDMEnabled)

	cfg.VerificationEnabled = boolValue(row, "verification_enabled", cfg.VerificationEnabled)
	cfg.VerificationUnverifiedRoleID = idValue(row, "verification_unverified_role_id", cfg.VerificationUnverifiedRoleID)
	cfg.VerificationVerifiedRoleID = idValue(row, "verification_verified_role_id", cfg.VerificationVerifiedRoleID)
	cfg.VerificationVerifiedRoleIDs = int64SliceValue(row, "verification_verified_role_ids", cfg.VerificationVerifiedRoleIDs)
	cfg.VerificationChannelID = idValue(row, "verification_channel_id", cfg.VerificationChannelID)
	cfg.VerificationLandingChannelID = idValue(row, "verification_landing_channel_id", cfg.VerificationLandingChannelID)
	cfg.GlobalLogChannelID = idValue(row, "global_log_channel_id", cfg.GlobalLogChannelID)
	cfg.VerificationLogChannelID = idValue(row, "verification_log_channel_id", cfg.VerificationLogChannelID)
	cfg.VerificationTimeout = intValue(row, "verification_timeout", cfg.VerificationTimeout)

	cfg.ModRoleID = idValue(row, "mod_role_id", cfg.ModRoleID)

	cfg.AutoRollerEnabled = boolValue(row, "auto_roller_enabled", cfg.AutoRollerEnabled)
	cfg.AutoRollerRoleID = idValue(row, "auto_roller_role_id", cfg.AutoRollerRoleID)
	cfg.AutoRollerRoleIDs = int64SliceValue(row, "auto_roller_role_ids", cfg.AutoRollerRoleIDs)

	cfg.AutoModEnabled = boolValue(row, "automod_enabled", cfg.AutoModEnabled)
	cfg.AutoModFilters = rawValue(row, "automod_filters", "[]")
	cfg.AutoModIgnoredChannels = int64SliceValue(row, "automod_ignored_channels", cfg.AutoModIgnoredChannels)
	cfg.AutoModIgnoredRoles = int64SliceValue(row, "automod_ignored_roles", cfg.AutoModIgnoredRoles)

	cfg.MusicEnabled = boolValue(row, "music_enabled", cfg.MusicEnabled)
	cfg.MusicRoleRestrictionEnabled = boolValue(row, "music_role_restriction_enabled", cfg.MusicRoleRestrictionEnabled)
	cfg.MusicAllowedRoles = int64SliceValue(row, "music_allowed_roles", cfg.MusicAllowedRoles)
	cfg.MusicAllowedUsers = int64SliceValue(row, "music_allowed_users", cfg.MusicAllowedUsers)
	cfg.MusicComponentRestrictionEnabled = boolValue(row, "music_component_restriction_enabled", cfg.MusicComponentRestrictionEnabled)

	cfg.AnalyticsEnabled = boolValue(row, "analytics_enabled", cfg.AnalyticsEnabled)
	cfg.AnalyticsExcludedChannels = int64SliceValue(row, "analytics_excluded_channels", cfg.AnalyticsExcludedChannels)

	cfg.VCWREnabled = boolValue(row, "vc_wr_enabled", cfg.VCWREnabled)

	cfg.JoinFilterEnabled = boolValue(row, "join_filter_enabled", cfg.JoinFilterEnabled)
	cfg.JoinFilterMinAgeValue = intValue(row, "join_filter_min_age_value", cfg.JoinFilterMinAgeValue)
	cfg.JoinFilterMinAgeUnit = stringValue(row, "join_filter_min_age_unit", cfg.JoinFilterMinAgeUnit)
	cfg.JoinFilterUsernamePatterns = stringSliceValue(row, "join_filter_username_patterns", cfg.JoinFilterUsernamePatterns)
	cfg.JoinFilterUsernameEmojis = boolValue(row, "join_filter_username_emojis", cfg.JoinFilterUsernameEmojis)
	cfg.JoinFilterUsernameHomoglyphs = boolValue(row, "join_filter_username_homoglyphs", cfg.JoinFilterUsernameHomoglyphs)
	cfg.JoinFilterEnforcement = stringValue(row, "join_filter_enforcement", cfg.JoinFilterEnforcement)
	cfg.JoinFilters = rawValue(row, "join_filters", "[]")

	cfg.AutoChannelNamerEnabled = boolValue(row, "auto_channel_namer_enabled", cfg.AutoChannelNamerEnabled)
	cfg.AutoChannelNamerLeft = stringValue(row, "auto_channel_namer_left", cfg.AutoChannelNamerLeft)
	cfg.AutoChannelNamerRight = stringValue(row, "auto_channel_namer_right", cfg.AutoChannelNamerRight)
	cfg.AutoChannelNamerFont = stringValue(row, "auto_channel_namer_font", cfg.AutoChannelNamerFont)
	cfg.AutoChannelNamerExcludeIDs = int64SliceValue(row, "auto_channel_namer_exclude_ids", cfg.AutoChannelNamerExcludeIDs)

	cfg.PluralityEnabled = boolValue(row, "plurality_enabled", cfg.PluralityEnabled)

	cfg.SelfRolesEnabled = boolValue(row, "self_roles_enabled", cfg.SelfRolesEnabled)
	cfg.SelfRolesGroups = rawValue(row, "self_roles_groups", "[]")

	return cfg
}

// Values returns the row values in Columns order for the store layer.
func (c Config) Values() []any {
	return []any{
		c.GuildID,
		c.Prefix,
		c.Cmd,
		nullableID(c.ChannelID),
		nullableID(c.AdminRoleID),
		nullableID(c.SharedChannelID),
		c.PrivateSessionsEnabled,
		c.SharedEnabled,
		c.NEOSEnabled,
		c.NebuffModuleEnabled,
		c.BattleEnabled,
		c.BattleDefaultHP,
		c.BattleDamageRange,
		c.BattleTimeout,
		c.MinesweeperEnabled,
		c.MinesweeperDefaultMines,
		c.WarningTrackerEnabled,
		marshalJSON(c.WarningPlatforms, "[]"),
		marshalJSON(c.WarningSeverityPoints, "{}"),
		c.WarningEscalationMode,
		c.WarningRollingWindowDays,
		marshalJSON(c.WarningLadder, "{}"),
		nullableID(c.WarningLogChannelID),
		c.WarningDMEnabled,
		c.VerificationEnabled,
		nullableID(c.VerificationUnverifiedRoleID),
		nullableID(c.VerificationVerifiedRoleID),
		marshalJSON(c.VerificationVerifiedRoleIDs, "[]"),
		nullableID(c.VerificationChannelID),
		nullableID(c.VerificationLandingChannelID),
		nullableID(c.GlobalLogChannelID),
		nullableID(c.VerificationLogChannelID),
		c.VerificationTimeout,
		nullableID(c.ModRoleID),
		c.AutoRollerEnabled,
		nullableID(c.AutoRollerRoleID),
		marshalJSON(c.AutoRollerRoleIDs, "[]"),
		c.AutoModEnabled,
		marshalJSON(c.AutoModFilters, "[]"),
		marshalJSON(c.AutoModIgnoredChannels, "[]"),
		marshalJSON(c.AutoModIgnoredRoles, "[]"),
		c.MusicEnabled,
		c.MusicRoleRestrictionEnabled,
		marshalJSON(c.MusicAllowedRoles, "[]"),
		marshalJSON(c.MusicAllowedUsers, "[]"),
		c.MusicComponentRestrictionEnabled,
		c.AnalyticsEnabled,
		marshalJSON(c.AnalyticsExcludedChannels, "[]"),
		c.VCWREnabled,
		c.JoinFilterEnabled,
		c.JoinFilterMinAgeValue,
		c.JoinFilterMinAgeUnit,
		marshalJSON(c.JoinFilterUsernamePatterns, "[]"),
		c.JoinFilterUsernameEmojis,
		c.JoinFilterUsernameHomoglyphs,
		c.JoinFilterEnforcement,
		marshalJSON(c.JoinFilters, "[]"),
		c.AutoChannelNamerEnabled,
		c.AutoChannelNamerLeft,
		c.AutoChannelNamerRight,
		c.AutoChannelNamerFont,
		marshalJSON(c.AutoChannelNamerExcludeIDs, "[]"),
		c.PluralityEnabled,
		c.SelfRolesEnabled,
		marshalJSON(c.SelfRolesGroups, "[]"),
	}
}

// Clone returns a deep copy. Cache reads and writes use it so callers cannot
// mutate shared slices, maps, or ID pointers.
func (c Config) Clone() Config {
	out := c

	out.ChannelID = cloneID(c.ChannelID)
	out.AdminRoleID = cloneID(c.AdminRoleID)
	out.SharedChannelID = cloneID(c.SharedChannelID)

	out.WarningPlatforms = slices.Clone(c.WarningPlatforms)
	out.WarningSeverityPoints = maps.Clone(c.WarningSeverityPoints)
	out.WarningLadder = maps.Clone(c.WarningLadder)
	out.WarningLogChannelID = cloneID(c.WarningLogChannelID)

	out.VerificationUnverifiedRoleID = cloneID(c.VerificationUnverifiedRoleID)
	out.VerificationVerifiedRoleID = cloneID(c.VerificationVerifiedRoleID)
	out.VerificationVerifiedRoleIDs = slices.Clone(c.VerificationVerifiedRoleIDs)
	out.VerificationChannelID = cloneID(c.VerificationChannelID)
	out.VerificationLandingChannelID = cloneID(c.VerificationLandingChannelID)
	out.GlobalLogChannelID = cloneID(c.GlobalLogChannelID)
	out.VerificationLogChannelID = cloneID(c.VerificationLogChannelID)

	out.ModRoleID = cloneID(c.ModRoleID)

	out.AutoRollerRoleID = cloneID(c.AutoRollerRoleID)
	out.AutoRollerRoleIDs = slices.Clone(c.AutoRollerRoleIDs)

	out.AutoModFilters = cloneRaw(c.AutoModFilters)
	out.AutoModIgnoredChannels = slices.Clone(c.AutoModIgnoredChannels)
	out.AutoModIgnoredRoles = slices.Clone(c.AutoModIgnoredRoles)

	out.MusicAllowedRoles = slices.Clone(c.MusicAllowedRoles)
	out.MusicAllowedUsers = slices.Clone(c.MusicAllowedUsers)

	out.AnalyticsExcludedChannels = slices.Clone(c.AnalyticsExcludedChannels)

	out.JoinFilterUsernamePatterns = slices.Clone(c.JoinFilterUsernamePatterns)
	out.JoinFilters = cloneRaw(c.JoinFilters)

	out.AutoChannelNamerExcludeIDs = slices.Clone(c.AutoChannelNamerExcludeIDs)

	out.SelfRolesGroups = cloneRaw(c.SelfRolesGroups)

	return out
}

func stringValue(row map[string]any, key, fallback string) string {
	value, ok := row[key]
	if !ok || value == nil {
		return fallback
	}
	switch value := value.(type) {
	case string:
		return value
	case []byte:
		return string(value)
	default:
		return fallback
	}
}

func intValue(row map[string]any, key string, fallback int64) int64 {
	value, ok := row[key]
	if !ok || value == nil {
		return fallback
	}
	if parsed, ok := toInt64(value); ok {
		return parsed
	}
	return fallback
}

func boolValue(row map[string]any, key string, fallback bool) bool {
	value, ok := row[key]
	if !ok || value == nil {
		return fallback
	}
	switch value := value.(type) {
	case bool:
		return value
	case string:
		return value == "t" || value == "true" || value == "1"
	default:
		return fallback
	}
}

func idValue(row map[string]any, key string, fallback *int64) *int64 {
	value, ok := row[key]
	if !ok {
		return cloneID(fallback)
	}
	if value == nil {
		return nil
	}
	parsed, ok := toInt64(value)
	if !ok || parsed <= 0 {
		return nil
	}
	return &parsed
}

func stringSliceValue(row map[string]any, key string, fallback []string) []string {
	raw, ok := rowText(row, key)
	if !ok {
		return slices.Clone(fallback)
	}
	var out []string
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		return slices.Clone(fallback)
	}
	if out == nil {
		return []string{}
	}
	return out
}

func int64SliceValue(row map[string]any, key string, fallback []int64) []int64 {
	raw, ok := rowText(row, key)
	if !ok {
		return slices.Clone(fallback)
	}
	var out []int64
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		return slices.Clone(fallback)
	}
	if out == nil {
		return []int64{}
	}
	return out
}

func stringInt64MapValue(row map[string]any, key string, fallback map[string]int64) map[string]int64 {
	raw, ok := rowText(row, key)
	if !ok {
		return maps.Clone(fallback)
	}
	var out map[string]int64
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		return maps.Clone(fallback)
	}
	if out == nil {
		return map[string]int64{}
	}
	return out
}

func stringStringMapValue(row map[string]any, key string, fallback map[string]string) map[string]string {
	raw, ok := rowText(row, key)
	if !ok {
		return maps.Clone(fallback)
	}
	var out map[string]string
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		return maps.Clone(fallback)
	}
	if out == nil {
		return map[string]string{}
	}
	return out
}

func rawValue(row map[string]any, key, fallback string) json.RawMessage {
	raw, ok := rowText(row, key)
	if !ok || !json.Valid([]byte(raw)) {
		return cloneRaw(json.RawMessage(fallback))
	}
	return cloneRaw(json.RawMessage(raw))
}

func rowText(row map[string]any, key string) (string, bool) {
	value, ok := row[key]
	if !ok || value == nil {
		return "", false
	}
	switch value := value.(type) {
	case string:
		return value, true
	case []byte:
		return string(value), true
	default:
		return "", false
	}
}

func toInt64(value any) (int64, bool) {
	switch value := value.(type) {
	case int64:
		return value, true
	case int32:
		return int64(value), true
	case int:
		return int64(value), true
	case float64:
		return int64(value), true
	case string:
		parsed, err := strconv.ParseInt(value, 10, 64)
		return parsed, err == nil
	default:
		return 0, false
	}
}

func nullableID(id *int64) any {
	if id == nil {
		return nil
	}
	return *id
}

func marshalJSON(value any, fallback string) string {
	data, err := json.Marshal(value)
	if err != nil || string(data) == "null" {
		return fallback
	}
	return string(data)
}

func cloneID(id *int64) *int64 {
	if id == nil {
		return nil
	}
	value := *id
	return &value
}

func cloneRaw(value json.RawMessage) json.RawMessage {
	if value == nil {
		return nil
	}
	return append(json.RawMessage(nil), value...)
}
