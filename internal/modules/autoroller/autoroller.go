// Package autoroller grants configured roles to members when they join and
// serves the Auto-Roller configuration dashboard.
package autoroller

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"slices"
	"strconv"
	"strings"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/audit"
	"github.com/nebuff/n-bot/internal/auth"
	"github.com/nebuff/n-bot/internal/guild"
	"github.com/nebuff/n-bot/internal/interact"
	"github.com/nebuff/n-bot/internal/module"
)

const (
	// OpenCustomID is rendered by the admin dashboard and handled here.
	OpenCustomID   = "autoroller:open"
	ToggleCustomID = "autoroller:toggle"
	ClearCustomID  = "autoroller:clear"
	RolesCustomID  = "autoroller:roles"

	// BackCustomID is handled by the admin dashboard.
	BackCustomID = "admin:modules"

	dashboardColor = 0x1ABC9C
)

// Module implements member-join role assignment and the Auto-Roller panel.
type Module struct {
	module.Base

	guilds  *guild.Cache
	ownerID int64
	log     *slog.Logger
}

// New creates the auto-roller module.
func New(guilds *guild.Cache, ownerID int64, log *slog.Logger) *Module {
	if guilds == nil {
		panic("autoroller: nil guild cache")
	}
	if log == nil {
		log = slog.Default()
	}
	return &Module{guilds: guilds, ownerID: ownerID, log: log}
}

// Name implements module.Module.
func (m *Module) Name() string { return "auto-roller" }

// Components implements module.ComponentProvider.
func (m *Module) Components() []module.Route {
	return []module.Route{
		{Prefix: OpenCustomID, Name: "open", Handler: m.open},
		{Prefix: ToggleCustomID, Name: "toggle", Handler: m.toggle},
		{Prefix: ClearCustomID, Name: "clear", Handler: m.clear},
		{Prefix: RolesCustomID, Name: "roles", Handler: m.selectRoles},
	}
}

// HandleMemberJoin implements module.MemberJoinProvider. It never consumes the
// join event, so later join-aware modules can still process it.
func (m *Module) HandleMemberJoin(ctx context.Context, session *dg.Session, event *dg.GuildMemberAdd) (bool, error) {
	if event == nil || event.Member == nil || event.User == nil {
		return false, nil
	}

	guildID, err := strconv.ParseInt(event.GuildID, 10, 64)
	if err != nil || guildID <= 0 {
		return false, fmt.Errorf("auto-roller: invalid guild id %q", event.GuildID)
	}

	cfg, err := m.guilds.Get(ctx, guildID)
	if err != nil {
		return false, err
	}
	configured := configuredRoleIDs(cfg)
	if !cfg.AutoRollerEnabled || len(configured) == 0 {
		return false, nil
	}

	if session == nil || session.State == nil {
		return false, errors.New("auto-roller: Discord session state is unavailable")
	}
	botID := ""
	if session.State.User != nil {
		botID = session.State.User.ID
	}
	if botID == "" {
		return false, errors.New("auto-roller: bot user is unavailable")
	}

	guildState, _ := session.State.Guild(event.GuildID)
	if guildState == nil {
		guildState, err = session.Guild(event.GuildID, dg.WithContext(ctx))
		if err != nil {
			return false, fmt.Errorf("auto-roller: load guild %s: %w", event.GuildID, err)
		}
	}

	roles := guildState.Roles
	if len(roles) == 0 {
		roles, err = session.GuildRoles(event.GuildID, dg.WithContext(ctx))
		if err != nil {
			return false, fmt.Errorf("auto-roller: load roles for guild %s: %w", event.GuildID, err)
		}
	}

	botMember, _ := session.State.Member(event.GuildID, botID)
	if botMember == nil {
		botMember, err = session.GuildMember(event.GuildID, botID, dg.WithContext(ctx))
		if err != nil {
			return false, fmt.Errorf("auto-roller: load bot member in guild %s: %w", event.GuildID, err)
		}
	}

	allowed, skipped := assignableRoleIDs(
		configured,
		event.Member.Roles,
		roles,
		botTopRolePosition(botMember, roles),
	)
	for _, roleID := range skipped {
		m.log.Warn("skipping auto-roller role above bot's top role",
			"guild_id", event.GuildID,
			"role_id", roleID,
		)
	}

	for _, roleID := range allowed {
		if err := session.GuildMemberRoleAdd(event.GuildID, event.User.ID, roleID, dg.WithContext(ctx)); err != nil {
			m.log.Error("adding auto-roller role",
				"guild_id", event.GuildID,
				"user_id", event.User.ID,
				"role_id", roleID,
				"err", err,
			)
		}
	}

	return false, nil
}

// Dashboard builds the auto-roller panel and its components.
func Dashboard(cfg guild.Config) (*dg.MessageEmbed, []dg.MessageComponent) {
	roleIDs := configuredRoleIDs(cfg)
	mentions := make([]string, 0, len(roleIDs))
	for _, roleID := range roleIDs {
		mentions = append(mentions, formatRoleMention(roleID))
	}

	embed := &dg.MessageEmbed{
		Title: "Nebot Module: Auto-Roller Configuration",
		Description: "Configure roles that are automatically granted to users when they join the server.\n\n" +
			"**Owner Setup Instructions:**\n" +
			"• Select the target role(s) to grant automatically from the dropdown below.\n" +
			"• The bot must have the `Manage Roles` permission, and its top role must be positioned above the configured auto-roller roles.",
		Color: dashboardColor,
		Fields: []*dg.MessageEmbedField{
			{Name: "Status", Value: statusText(cfg.AutoRollerEnabled), Inline: true},
			{Name: "Auto-Roller Roles", Value: safeJoinItems(mentions, 1000), Inline: true},
		},
	}

	components := []dg.MessageComponent{
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{Label: "Toggle Auto-Roller", Style: dg.PrimaryButton, CustomID: ToggleCustomID},
			dg.Button{Label: "Clear Auto-Roller Roles", Style: dg.SecondaryButton, CustomID: ClearCustomID},
		}},
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.SelectMenu{
				MenuType:    dg.RoleSelectMenu,
				CustomID:    RolesCustomID,
				Placeholder: "Select Auto-Roller Roles...",
				MinValues:   intPointer(1),
				MaxValues:   10,
			},
		}},
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{Label: "Back to Modules", Style: dg.DangerButton, CustomID: BackCustomID},
		}},
	}

	return embed, components
}

func (m *Module) open(c *interact.Context) error {
	cfg, ok, err := m.loadAdminConfig(c)
	if err != nil || !ok {
		return err
	}
	return m.update(c, cfg)
}

func (m *Module) toggle(c *interact.Context) error {
	cfg, ok, err := m.loadAdminConfig(c)
	if err != nil || !ok {
		return err
	}

	cfg.AutoRollerEnabled = !cfg.AutoRollerEnabled
	if err := m.guilds.Save(c.Context(), cfg); err != nil {
		return err
	}

	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Toggled Auto-Roller module state to `%s`",
		enabledWord(cfg.AutoRollerEnabled),
	), m.log)
	return m.update(c, cfg)
}

func (m *Module) clear(c *interact.Context) error {
	cfg, ok, err := m.loadAdminConfig(c)
	if err != nil || !ok {
		return err
	}

	cfg.AutoRollerRoleIDs = []int64{}
	cfg.AutoRollerRoleID = nil
	if err := m.guilds.Save(c.Context(), cfg); err != nil {
		return err
	}

	audit.SettingChange(c.Session, cfg, c.Interaction, "Cleared Auto-Roller roles", m.log)
	return m.update(c, cfg)
}

func (m *Module) selectRoles(c *interact.Context) error {
	cfg, ok, err := m.loadAdminConfig(c)
	if err != nil || !ok {
		return err
	}

	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Select at least one role.")
	}
	if len(values) > 10 {
		return c.ReplyEphemeral("Select at most 10 roles.")
	}

	roleIDs := make([]int64, 0, len(values))
	for _, raw := range values {
		roleID, err := strconv.ParseInt(raw, 10, 64)
		if err != nil || roleID <= 0 {
			return fmt.Errorf("auto-roller: invalid role id %q", raw)
		}
		roleIDs = append(roleIDs, roleID)
	}

	cfg.AutoRollerRoleIDs = roleIDs
	first := roleIDs[0]
	cfg.AutoRollerRoleID = &first
	if err := m.guilds.Save(c.Context(), cfg); err != nil {
		return err
	}

	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Updated Auto-Roller roles to: %s",
		strings.Join(roleNames(c.Session, c.Interaction.GuildID, roleIDs), ", "),
	), m.log)
	return m.update(c, cfg)
}

func (m *Module) update(c *interact.Context, cfg guild.Config) error {
	embed, components := Dashboard(cfg)
	return c.Update("", embed, components)
}

func (m *Module) loadAdminConfig(c *interact.Context) (guild.Config, bool, error) {
	if c == nil || c.Interaction == nil {
		return guild.Config{}, false, errors.New("auto-roller: nil interaction")
	}
	if c.Interaction.GuildID == "" {
		return guild.Config{}, false, c.ReplyEphemeral("This control can only be used in a server.")
	}

	guildID, err := strconv.ParseInt(c.Interaction.GuildID, 10, 64)
	if err != nil || guildID <= 0 {
		return guild.Config{}, false, fmt.Errorf("auto-roller: invalid guild id %q", c.Interaction.GuildID)
	}
	cfg, err := m.guilds.Get(c.Context(), guildID)
	if err != nil {
		return guild.Config{}, false, err
	}
	if !auth.IsAdmin(c.Session, c.Interaction.GuildID, c.Interaction.Member, c.Interaction.User, cfg, m.ownerID) {
		return cfg, false, c.ReplyEphemeral("Permission denied")
	}
	return cfg, true, nil
}

func configuredRoleIDs(cfg guild.Config) []int64 {
	out := make([]int64, 0, len(cfg.AutoRollerRoleIDs)+1)
	for _, roleID := range cfg.AutoRollerRoleIDs {
		if roleID > 0 && !slices.Contains(out, roleID) {
			out = append(out, roleID)
		}
	}
	if cfg.AutoRollerRoleID != nil &&
		*cfg.AutoRollerRoleID > 0 &&
		!slices.Contains(out, *cfg.AutoRollerRoleID) {
		out = append([]int64{*cfg.AutoRollerRoleID}, out...)
	}
	return out
}

func botTopRolePosition(bot *dg.Member, roles []*dg.Role) int {
	if bot == nil {
		return 0
	}
	positions := make(map[string]int, len(roles))
	for _, role := range roles {
		if role != nil {
			positions[role.ID] = role.Position
		}
	}

	top := 0
	for _, roleID := range bot.Roles {
		if position, ok := positions[roleID]; ok && position > top {
			top = position
		}
	}
	return top
}

func assignableRoleIDs(configured []int64, memberRoleIDs []string, roles []*dg.Role, botTopPosition int) (allowed, skipped []string) {
	if len(configured) == 0 || len(roles) == 0 {
		return nil, nil
	}

	byID := make(map[string]*dg.Role, len(roles))
	for _, role := range roles {
		if role != nil {
			byID[role.ID] = role
		}
	}
	hasRole := make(map[string]struct{}, len(memberRoleIDs))
	for _, roleID := range memberRoleIDs {
		hasRole[roleID] = struct{}{}
	}

	seen := make(map[string]struct{}, len(configured))
	for _, rawID := range configured {
		if rawID <= 0 {
			continue
		}
		roleID := strconv.FormatInt(rawID, 10)
		if _, duplicate := seen[roleID]; duplicate {
			continue
		}
		seen[roleID] = struct{}{}

		role := byID[roleID]
		if role == nil {
			continue
		}
		if role.Position >= botTopPosition {
			skipped = append(skipped, roleID)
			continue
		}
		if _, exists := hasRole[roleID]; exists {
			continue
		}
		allowed = append(allowed, roleID)
	}
	return allowed, skipped
}

func roleNames(session *dg.Session, guildID string, roleIDs []int64) []string {
	names := make([]string, 0, len(roleIDs))
	roleNameByID := make(map[string]string)
	if session != nil && session.State != nil {
		if guildState, err := session.State.Guild(guildID); err == nil && guildState != nil {
			for _, role := range guildState.Roles {
				if role != nil {
					roleNameByID[role.ID] = role.Name
				}
			}
		}
	}

	for _, roleID := range roleIDs {
		name := roleNameByID[strconv.FormatInt(roleID, 10)]
		if name == "" {
			name = formatRoleMention(roleID)
		}
		names = append(names, name)
	}
	return names
}

func safeJoinItems(items []string, maxLen int) string {
	if len(items) == 0 {
		return "None"
	}

	joined := strings.Join(items, ", ")
	if len(joined) <= maxLen {
		return joined
	}

	result := make([]string, 0, len(items))
	currentLen := 0
	for _, item := range items {
		addition := item
		if len(result) > 0 {
			addition = ", " + item
		}
		if currentLen+len(addition)+25 > maxLen {
			break
		}
		result = append(result, item)
		currentLen += len(addition)
	}

	remaining := len(items) - len(result)
	if remaining > 0 {
		return strings.Join(result, ", ") + fmt.Sprintf(" ... (and %d more)", remaining)
	}
	return strings.Join(result, ", ")
}

func statusText(enabled bool) string {
	if enabled {
		return "[ENABLED]"
	}
	return "[DISABLED]"
}

func enabledWord(enabled bool) string {
	if enabled {
		return "enabled"
	}
	return "disabled"
}

func formatRoleMention(roleID int64) string {
	return fmt.Sprintf("<@&%d>", roleID)
}

func intPointer(value int) *int { return &value }
