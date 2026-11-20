// Package analytics tracks server activity and exposes the analytics report
// and configuration dashboard.
package analytics

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"slices"
	"strconv"
	"time"

	dg "github.com/bwmarrin/discordgo"

	analyticsdata "github.com/nebuff/n-bot/internal/analytics"
	"github.com/nebuff/n-bot/internal/audit"
	"github.com/nebuff/n-bot/internal/auth"
	"github.com/nebuff/n-bot/internal/guild"
	"github.com/nebuff/n-bot/internal/interact"
	"github.com/nebuff/n-bot/internal/module"
)

const (
	// OpenCustomID is rendered by the admin dashboard and handled here.
	OpenCustomID     = "analytics:open"
	ToggleCustomID   = "analytics:toggle"
	ExcludeCustomID  = "analytics:exclude"
	ChannelsCustomID = "analytics:channels"
	ClearCustomID    = "analytics:clear"

	// BackCustomID is handled by the admin dashboard.
	BackCustomID = "admin:modules"

	dashboardColor = 0x3498DB
)

// Module tracks analytics and implements the analytics dashboard and report.
type Module struct {
	module.Base

	guilds     *guild.Cache
	aggregator *analyticsdata.Aggregator
	ownerID    int64
	log        *slog.Logger
	now        func() time.Time
}

// New creates the analytics module.
func New(guilds *guild.Cache, aggregator *analyticsdata.Aggregator, ownerID int64, log *slog.Logger) *Module {
	if guilds == nil {
		panic("analytics: nil guild cache")
	}
	if aggregator == nil {
		panic("analytics: nil aggregator")
	}
	if log == nil {
		log = slog.Default()
	}
	return &Module{
		guilds:     guilds,
		aggregator: aggregator,
		ownerID:    ownerID,
		log:        log,
		now:        time.Now,
	}
}

// Name implements module.Module.
func (m *Module) Name() string { return "analytics" }

// Commands implements module.Module.
func (m *Module) Commands() []module.Command {
	return []module.Command{
		{
			Definition: &dg.ApplicationCommand{
				Name:        "analytics",
				Description: "View server activity analytics report",
				Options: []*dg.ApplicationCommandOption{
					{
						Type:        dg.ApplicationCommandOptionString,
						Name:        "window",
						Description: "The time window for the analytics report",
						Required:    false,
						Choices: []*dg.ApplicationCommandOptionChoice{
							{Name: "Last 24 Hours", Value: "24h"},
							{Name: "Last 7 Days", Value: "7d"},
						},
					},
				},
			},
			Handler: m.report,
		},
	}
}

// Components implements module.ComponentProvider.
func (m *Module) Components() []module.Route {
	return []module.Route{
		{Prefix: OpenCustomID, Name: "open", Handler: m.open},
		{Prefix: ToggleCustomID, Name: "toggle", Handler: m.toggle},
		{Prefix: ExcludeCustomID, Name: "exclude", Handler: m.exclude},
		{Prefix: ChannelsCustomID, Name: "channels", Handler: m.selectChannels},
		{Prefix: ClearCustomID, Name: "clear", Handler: m.clear},
	}
}

// HandleMessage implements module.Module.
func (m *Module) HandleMessage(ctx context.Context, _ *dg.Session, event *dg.MessageCreate) (bool, error) {
	if event == nil || event.Message == nil || event.Author == nil || event.Author.Bot || event.GuildID == "" {
		return false, nil
	}

	guildID, err := parseID(event.GuildID, "guild")
	if err != nil {
		return false, err
	}
	channelID, err := parseID(event.ChannelID, "channel")
	if err != nil {
		return false, err
	}
	cfg, err := m.guilds.Get(ctx, guildID)
	if err != nil {
		return false, err
	}
	if !cfg.AnalyticsEnabled || slices.Contains(cfg.AnalyticsExcludedChannels, channelID) {
		return false, nil
	}
	if err := m.aggregator.RecordMessage(ctx, guildID, event.ChannelID, m.now()); err != nil {
		return false, err
	}
	return false, nil
}

// HandleMemberJoin implements module.MemberJoinProvider.
func (m *Module) HandleMemberJoin(ctx context.Context, _ *dg.Session, event *dg.GuildMemberAdd) (bool, error) {
	if event == nil || event.Member == nil || event.User == nil || event.GuildID == "" {
		return false, nil
	}

	guildID, err := parseID(event.GuildID, "guild")
	if err != nil {
		return false, err
	}
	cfg, err := m.guilds.Get(ctx, guildID)
	if err != nil {
		return false, err
	}
	if !cfg.AnalyticsEnabled {
		return false, nil
	}
	userID, err := parseID(event.User.ID, "user")
	if err != nil {
		return false, err
	}
	return false, m.aggregator.RecordJoin(ctx, guildID, userID, m.now())
}

// HandleMemberLeave implements module.MemberLeaveProvider.
func (m *Module) HandleMemberLeave(ctx context.Context, _ *dg.Session, event *dg.GuildMemberRemove) (bool, error) {
	if event == nil || event.Member == nil || event.User == nil || event.GuildID == "" {
		return false, nil
	}

	guildID, err := parseID(event.GuildID, "guild")
	if err != nil {
		return false, err
	}
	cfg, err := m.guilds.Get(ctx, guildID)
	if err != nil {
		return false, err
	}
	if !cfg.AnalyticsEnabled {
		return false, nil
	}
	userID, err := parseID(event.User.ID, "user")
	if err != nil {
		return false, err
	}
	return false, m.aggregator.RecordLeave(ctx, guildID, userID, m.now())
}

// HandleVoiceStateUpdate implements module.VoiceStateProvider.
func (m *Module) HandleVoiceStateUpdate(ctx context.Context, session *dg.Session, event *dg.VoiceStateUpdate) (bool, error) {
	if event == nil || event.VoiceState == nil || event.GuildID == "" {
		return false, nil
	}

	member := event.Member
	if member == nil && session != nil && session.State != nil {
		member, _ = session.State.Member(event.GuildID, event.UserID)
	}
	if member == nil || member.User == nil || member.User.Bot {
		return false, nil
	}

	beforeChannel := ""
	if event.BeforeUpdate != nil {
		beforeChannel = event.BeforeUpdate.ChannelID
	}
	if beforeChannel == event.ChannelID {
		return false, nil
	}

	guildID, err := parseID(event.GuildID, "guild")
	if err != nil {
		return false, err
	}
	cfg, err := m.guilds.Get(ctx, guildID)
	if err != nil {
		return false, err
	}
	if !cfg.AnalyticsEnabled {
		return false, nil
	}

	count, err := voiceConcurrency(session, event.GuildID)
	if err != nil {
		return false, err
	}
	return false, m.aggregator.RecordVoice(ctx, guildID, count, m.now())
}

func (m *Module) report(c *interact.Context) error {
	if c.Interaction.GuildID == "" {
		return c.ReplyEphemeral("Server only command")
	}

	guildID, err := parseID(c.Interaction.GuildID, "guild")
	if err != nil {
		return err
	}
	cfg, err := m.guilds.Get(c.Context(), guildID)
	if err != nil {
		return err
	}
	if !auth.IsMod(c.Session, c.Interaction.GuildID, c.Interaction.Member, c.Interaction.User, cfg, m.ownerID) {
		return c.ReplyEphemeral("Permission denied.")
	}

	record, err := m.aggregator.Snapshot(c.Context(), guildID)
	if err != nil {
		return err
	}
	report := record.BuildReport(reportWindow(c), m.now())
	return c.ReplyEmbedEphemeral(reportEmbed(guildName(c.Session, c.Context(), c.Interaction.GuildID), report))
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

	cfg.AnalyticsEnabled = !cfg.AnalyticsEnabled
	if err := m.guilds.Save(c.Context(), cfg); err != nil {
		return err
	}
	audit.SettingChange(
		c.Session, cfg, c.Interaction,
		fmt.Sprintf("Toggled Server Analytics module to %s", enabledWord(cfg.AnalyticsEnabled)),
		m.log,
	)
	return m.update(c, cfg)
}

func (m *Module) exclude(c *interact.Context) error {
	_, ok, err := m.loadAdminConfig(c)
	if err != nil || !ok {
		return err
	}
	return c.Update("", nil, excludeComponents())
}

func (m *Module) selectChannels(c *interact.Context) error {
	cfg, ok, err := m.loadAdminConfig(c)
	if err != nil || !ok {
		return err
	}

	values := c.Interaction.MessageComponentData().Values
	channelIDs := make([]int64, 0, len(values))
	for _, raw := range values {
		channelID, err := parseID(raw, "channel")
		if err != nil {
			return err
		}
		channelIDs = append(channelIDs, channelID)
	}
	cfg.AnalyticsExcludedChannels = channelIDs
	if err := m.guilds.Save(c.Context(), cfg); err != nil {
		return err
	}
	audit.SettingChange(
		c.Session, cfg, c.Interaction,
		"Updated Server Analytics excluded channels",
		m.log,
	)
	return m.update(c, cfg)
}

func (m *Module) clear(c *interact.Context) error {
	cfg, ok, err := m.loadAdminConfig(c)
	if err != nil || !ok {
		return err
	}
	if err := m.aggregator.Clear(c.Context(), cfg.GuildID); err != nil {
		return err
	}
	audit.SettingChange(
		c.Session, cfg, c.Interaction,
		"Cleared all historical analytics logs",
		m.log,
	)
	return m.update(c, cfg)
}

func (m *Module) update(c *interact.Context, cfg guild.Config) error {
	embed, components := Dashboard(cfg)
	return c.Update("", embed, components)
}

func (m *Module) loadAdminConfig(c *interact.Context) (guild.Config, bool, error) {
	if c == nil || c.Interaction == nil {
		return guild.Config{}, false, errors.New("analytics: nil interaction")
	}
	if c.Interaction.GuildID == "" {
		return guild.Config{}, false, c.ReplyEphemeral("This control can only be used in a server.")
	}

	guildID, err := parseID(c.Interaction.GuildID, "guild")
	if err != nil {
		return guild.Config{}, false, err
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

func voiceConcurrency(session *dg.Session, guildID string) (int64, error) {
	if session == nil || session.State == nil {
		return 0, errors.New("analytics: Discord session state is unavailable")
	}
	guildState, err := session.State.Guild(guildID)
	if err != nil || guildState == nil {
		return 0, fmt.Errorf("analytics: guild %s is unavailable: %w", guildID, err)
	}
	return countVoiceMembers(guildState, func(userID string) *dg.Member {
		member, err := session.State.Member(guildID, userID)
		if err != nil {
			return nil
		}
		return member
	}), nil
}

func countVoiceMembers(guildState *dg.Guild, lookup func(string) *dg.Member) int64 {
	if guildState == nil {
		return 0
	}
	voiceChannels := make(map[string]struct{})
	for _, channel := range guildState.Channels {
		if channel != nil && channel.Type == dg.ChannelTypeGuildVoice {
			voiceChannels[channel.ID] = struct{}{}
		}
	}

	var count int64
	for _, state := range guildState.VoiceStates {
		if state == nil || state.ChannelID == "" {
			continue
		}
		if _, ok := voiceChannels[state.ChannelID]; !ok {
			continue
		}
		member := state.Member
		if member == nil && lookup != nil {
			member = lookup(state.UserID)
		}
		if member == nil || member.User == nil || member.User.Bot {
			continue
		}
		count++
	}
	return count
}

func parseID(raw, kind string) (int64, error) {
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		return 0, fmt.Errorf("analytics: invalid %s id %q", kind, raw)
	}
	return id, nil
}

func reportWindow(c *interact.Context) time.Duration {
	if c != nil && c.Interaction != nil {
		for _, option := range c.Interaction.ApplicationCommandData().Options {
			if option == nil || option.Name != "window" {
				continue
			}
			if value, ok := option.Value.(string); ok && value == "7d" {
				return 7 * 24 * time.Hour
			}
		}
	}
	return 24 * time.Hour
}

func guildName(session *dg.Session, ctx context.Context, guildID string) string {
	if session != nil && session.State != nil {
		if guildState, err := session.State.Guild(guildID); err == nil && guildState != nil && guildState.Name != "" {
			return guildState.Name
		}
	}
	if session != nil {
		if guildState, err := session.Guild(guildID, dg.WithContext(ctx)); err == nil && guildState != nil && guildState.Name != "" {
			return guildState.Name
		}
	}
	return "this server"
}

func enabledWord(enabled bool) string {
	if enabled {
		return "enabled"
	}
	return "disabled"
}
