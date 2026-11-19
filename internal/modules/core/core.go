// Package core contains platform-level commands that do not belong to a
// feature module.
package core

import (
	"fmt"
	"log/slog"
	"time"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/interact"
	"github.com/nebuff/n-bot/internal/module"
)

// Module exposes the bot's health command.
type Module struct {
	module.Base
	started time.Time
	log     *slog.Logger
}

// New creates the core module.
func New(log *slog.Logger) *Module {
	return &Module{started: time.Now(), log: log}
}

// Name implements module.Module.
func (m *Module) Name() string { return "core" }

// Commands implements module.Module.
func (m *Module) Commands() []module.Command {
	return []module.Command{
		{
			Definition: &dg.ApplicationCommand{
				Name:        "ping",
				Description: "Check that NEBOT is online",
			},
			Handler: m.ping,
		},
	}
}

func (m *Module) ping(c *interact.Context) error {
	return c.ReplyEphemeral(fmt.Sprintf("Pong! Uptime: %s", time.Since(m.started).Round(time.Second)))
}
