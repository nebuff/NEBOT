// Package module defines the contract implemented by every NEBOT feature.
package module

import (
	"context"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/interact"
)

// Handler handles one slash command, component, or modal interaction.
type Handler func(*interact.Context) error

// Command is a slash command definition plus its handler.
type Command struct {
	Definition *dg.ApplicationCommand
	Handler    Handler
}

// Route dispatches interactions whose custom_id starts with Prefix. Routes are
// matched longest-prefix-first.
type Route struct {
	Prefix  string
	Name    string
	Handler Handler
}

// Module is a self-contained feature package.
//
// Modules are registered before the bot starts; implementations must be safe
// for concurrent event handlers.
type Module interface {
	Name() string
	Commands() []Command
	HandleMessage(ctx context.Context, session *dg.Session, message *dg.MessageCreate) (handled bool, err error)
}

// ComponentProvider is implemented by modules that handle buttons and selects.
type ComponentProvider interface {
	Components() []Route
}

// ModalProvider is implemented by modules that handle modal submissions.
type ModalProvider interface {
	Modals() []Route
}

// Base provides no-op implementations for modules that do not use every hook.
// Embed it by value.
type Base struct{}

func (Base) Commands() []Command { return nil }

func (Base) HandleMessage(context.Context, *dg.Session, *dg.MessageCreate) (bool, error) {
	return false, nil
}
