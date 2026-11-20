// Package admin provides the guild administration dashboard.
package admin

import (
	"errors"
	"fmt"
	"log/slog"
	"strconv"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/auth"
	"github.com/nebuff/n-bot/internal/guild"
	"github.com/nebuff/n-bot/internal/interact"
	"github.com/nebuff/n-bot/internal/module"
	analyticsui "github.com/nebuff/n-bot/internal/modules/analytics"
	"github.com/nebuff/n-bot/internal/modules/autoroller"
	selfrolesui "github.com/nebuff/n-bot/internal/modules/selfroles"
)

const (
	modulesCustomID = "admin:modules"
	modulesColor    = 0x3498DB
)

// Module implements the /admin module manager.
type Module struct {
	module.Base

	guilds  *guild.Cache
	ownerID int64
	log     *slog.Logger
}

// New creates the administration dashboard module.
func New(guilds *guild.Cache, ownerID int64, log *slog.Logger) *Module {
	if guilds == nil {
		panic("admin: nil guild cache")
	}
	if log == nil {
		log = slog.Default()
	}
	return &Module{guilds: guilds, ownerID: ownerID, log: log}
}

// Name implements module.Module.
func (m *Module) Name() string { return "admin" }

// Commands implements module.Module.
func (m *Module) Commands() []module.Command {
	return []module.Command{
		{
			Definition: &dg.ApplicationCommand{
				Name:        "admin",
				Description: "Nebot Administration Dashboard",
			},
			Handler: m.adminPanel,
		},
	}
}

// Components implements module.ComponentProvider.
func (m *Module) Components() []module.Route {
	return []module.Route{
		{Prefix: modulesCustomID, Name: "modules", Handler: m.modulesPanel},
	}
}

func (m *Module) adminPanel(c *interact.Context) error {
	if c.Interaction.GuildID == "" {
		return c.ReplyEphemeral("Server only command")
	}

	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	embed, components := buildModules(cfg)
	return c.ReplyEmbedWithComponents(embed, components, true)
}

func (m *Module) modulesPanel(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	embed, components := buildModules(cfg)
	return c.Update("", embed, components)
}

func (m *Module) requireAdmin(c *interact.Context) (guild.Config, bool, error) {
	if c == nil || c.Interaction == nil {
		return guild.Config{}, false, errors.New("admin: nil interaction")
	}
	if c.Interaction.GuildID == "" {
		return guild.Config{}, false, c.ReplyEphemeral("Server only command")
	}

	guildID, err := strconv.ParseInt(c.Interaction.GuildID, 10, 64)
	if err != nil || guildID <= 0 {
		return guild.Config{}, false, fmt.Errorf("admin: invalid guild id %q", c.Interaction.GuildID)
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

func buildModules(cfg guild.Config) (*dg.MessageEmbed, []dg.MessageComponent) {
	embed := &dg.MessageEmbed{
		Title:       "Nebot Module Manager",
		Description: "Status overview of all server modules. Enabled modules are highlighted in green, disabled in red.",
		Color:       modulesColor,
		Fields: []*dg.MessageEmbedField{
			{Name: "Ne-OS Shell Module", Value: status(cfg.NEOSEnabled), Inline: true},
			{Name: "Battle Game Module", Value: status(cfg.BattleEnabled), Inline: true},
			{Name: "Minesweeper Module", Value: status(cfg.MinesweeperEnabled), Inline: true},
			{Name: "Warning Tracker Module", Value: status(cfg.WarningTrackerEnabled), Inline: true},
			{Name: "Verification Module", Value: status(cfg.VerificationEnabled), Inline: true},
			{Name: "Auto-Roller Module", Value: status(cfg.AutoRollerEnabled), Inline: true},
			{Name: "AutoMod Module", Value: status(cfg.AutoModEnabled), Inline: true},
			{Name: "Music Module", Value: status(cfg.MusicEnabled), Inline: true},
			{Name: "VC WR Module", Value: status(cfg.VCWREnabled), Inline: true},
			{Name: "Server Analytics Module", Value: status(cfg.AnalyticsEnabled), Inline: true},
			{Name: "Join Filtering Module", Value: status(cfg.JoinFilterEnabled), Inline: true},
			{Name: "Nebuff Funny Module", Value: status(cfg.NebuffModuleEnabled), Inline: true},
			{Name: "Plurality Module", Value: status(cfg.PluralityEnabled), Inline: true},
			{Name: "Self Roles Module", Value: status(cfg.SelfRolesEnabled), Inline: true},
		},
	}

	autoRollerStyle := dg.DangerButton
	if cfg.AutoRollerEnabled {
		autoRollerStyle = dg.SuccessButton
	}
	analyticsStyle := dg.DangerButton
	if cfg.AnalyticsEnabled {
		analyticsStyle = dg.SuccessButton
	}
	selfRolesStyle := dg.DangerButton
	if cfg.SelfRolesEnabled {
		selfRolesStyle = dg.SuccessButton
	}
	components := []dg.MessageComponent{
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{
				Label:    "Auto-Roller Module",
				Style:    autoRollerStyle,
				CustomID: autoroller.OpenCustomID,
			},
			dg.Button{
				Label:    "Server Analytics Module",
				Style:    analyticsStyle,
				CustomID: analyticsui.OpenCustomID,
			},
			dg.Button{
				Label:    "Self Roles Module",
				Style:    selfRolesStyle,
				CustomID: selfrolesui.OpenCustomID,
			},
		}},
	}
	return embed, components
}

func status(enabled bool) string {
	if enabled {
		return "[ENABLED]"
	}
	return "[DISABLED]"
}
