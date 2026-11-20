// Package bot owns the Discord gateway session and dispatches events to modules.
package bot

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"runtime/debug"
	"sort"
	"strings"
	"sync"
	"time"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/config"
	"github.com/nebuff/n-bot/internal/guild"
	"github.com/nebuff/n-bot/internal/interact"
	"github.com/nebuff/n-bot/internal/module"
	"github.com/nebuff/n-bot/internal/store"
)

const (
	interactionTimeout = 20 * time.Second
	messageTimeout     = 30 * time.Second
	memberJoinTimeout  = 20 * time.Second
	memberLeaveTimeout = 20 * time.Second
	voiceStateTimeout  = 20 * time.Second
	readyTimeout       = 30 * time.Second
)

// Bot wires a discordgo session to registered modules.
type Bot struct {
	cfg    config.Config
	log    *slog.Logger
	store  *store.Store
	guilds *guild.Cache

	session *dg.Session

	commands     map[string]module.Command
	commandOrder []string
	components   []module.Route
	modals       []module.Route
	modules      []module.Module

	readyCh   chan struct{}
	readyOnce sync.Once
}

// New creates the Discord session and registers the event dispatchers.
// Call Register for each module, then Run.
func New(cfg config.Config, log *slog.Logger, st *store.Store) (*Bot, error) {
	if log == nil {
		log = slog.Default()
	}
	if st == nil {
		return nil, errors.New("bot: store is required")
	}

	session, err := dg.New("Bot " + cfg.DiscordToken)
	if err != nil {
		return nil, fmt.Errorf("create Discord session: %w", err)
	}
	session.Identify.Intents = dg.IntentsGuilds |
		dg.IntentsGuildMessages |
		dg.IntentsDirectMessages |
		dg.IntentsGuildMembers |
		dg.IntentsGuildVoiceStates |
		dg.IntentsMessageContent

	b := &Bot{
		cfg:        cfg,
		log:        log,
		store:      st,
		guilds:     guild.NewCache(st),
		session:    session,
		commands:   make(map[string]module.Command),
		components: nil,
		modals:     nil,
		readyCh:    make(chan struct{}),
	}

	session.AddHandler(b.onReady)
	session.AddHandler(b.onInteractionCreate)
	session.AddHandler(b.onMessageCreate)
	session.AddHandler(b.onGuildMemberAdd)
	session.AddHandler(b.onGuildMemberRemove)
	session.AddHandler(b.onVoiceStateUpdate)

	return b, nil
}

// Register adds a module. It must be called before Run.
func (b *Bot) Register(m module.Module) error {
	if m == nil {
		return errors.New("bot: cannot register a nil module")
	}
	name := strings.TrimSpace(m.Name())
	if name == "" {
		return errors.New("bot: module name is empty")
	}
	for _, existing := range b.modules {
		if existing.Name() == name {
			return fmt.Errorf("bot: module %q is already registered", name)
		}
	}

	commands := m.Commands()
	seenCommands := make(map[string]struct{}, len(commands))
	for _, command := range commands {
		if command.Definition == nil || strings.TrimSpace(command.Definition.Name) == "" {
			return fmt.Errorf("bot: module %q has a command with no definition or name", name)
		}
		if command.Handler == nil {
			return fmt.Errorf("bot: module %q command %q has a nil handler", name, command.Definition.Name)
		}
		if _, exists := b.commands[command.Definition.Name]; exists {
			return fmt.Errorf("bot: duplicate command %q", command.Definition.Name)
		}
		if _, duplicate := seenCommands[command.Definition.Name]; duplicate {
			return fmt.Errorf("bot: module %q defines command %q twice", name, command.Definition.Name)
		}
		seenCommands[command.Definition.Name] = struct{}{}
	}

	var components, modals []module.Route
	if provider, ok := m.(module.ComponentProvider); ok {
		components = provider.Components()
		if err := validateRoutes(name, components, b.components); err != nil {
			return err
		}
	}
	if provider, ok := m.(module.ModalProvider); ok {
		modals = provider.Modals()
		if err := validateRoutes(name, modals, b.modals); err != nil {
			return err
		}
	}

	// Validation passed; commit the module atomically.
	b.modules = append(b.modules, m)
	for _, command := range commands {
		b.commands[command.Definition.Name] = command
		b.commandOrder = append(b.commandOrder, command.Definition.Name)
	}
	b.components = append(b.components, components...)
	b.modals = append(b.modals, modals...)
	sortRoutes(b.components)
	sortRoutes(b.modals)

	b.log.Info("module registered",
		"module", name,
		"commands", len(commands),
		"component_routes", len(components),
		"modal_routes", len(modals),
	)
	return nil
}

// Guilds returns the per-guild configuration cache used by feature modules.
func (b *Bot) Guilds() *guild.Cache {
	return b.guilds
}

// Run connects to Discord, syncs commands, and blocks until ctx is canceled.
func (b *Bot) Run(ctx context.Context) error {
	b.log.Info("connecting to Discord")
	if err := b.session.Open(); err != nil {
		return fmt.Errorf("open Discord gateway: %w", err)
	}
	defer func() {
		if err := b.session.Close(); err != nil {
			b.log.Warn("closing Discord session", "err", err)
		}
	}()

	select {
	case <-b.readyCh:
	case <-time.After(readyTimeout):
		return errors.New("timed out waiting for Discord ready")
	case <-ctx.Done():
		return ctx.Err()
	}

	if err := b.syncCommands(); err != nil {
		return err
	}

	b.log.Info("NEBOT is running", "commands", len(b.commands))
	<-ctx.Done()
	b.log.Info("shutdown signal received")
	return nil
}

func (b *Bot) syncCommands() error {
	if b.session.State == nil || b.session.State.User == nil {
		return errors.New("Discord application ID is not available yet")
	}

	definitions := make([]*dg.ApplicationCommand, 0, len(b.commandOrder))
	for _, name := range b.commandOrder {
		definitions = append(definitions, b.commands[name].Definition)
	}

	created, err := b.session.ApplicationCommandBulkOverwrite(
		b.session.State.User.ID,
		b.cfg.DevGuildID,
		definitions,
	)
	if err != nil {
		return fmt.Errorf("sync application commands: %w", err)
	}

	scope := "global"
	if b.cfg.DevGuildID != "" {
		scope = "guild:" + b.cfg.DevGuildID
	}
	b.log.Info("application commands synced", "scope", scope, "count", len(created))
	return nil
}

func (b *Bot) onReady(session *dg.Session, ready *dg.Ready) {
	if ready.User != nil {
		b.log.Info("connected to Discord",
			"username", ready.User.Username,
			"user_id", ready.User.ID,
			"guilds", len(ready.Guilds),
		)
	}
	if err := session.UpdateGameStatus(0, b.cfg.BotStatus); err != nil {
		b.log.Warn("setting bot status", "err", err)
	}
	b.readyOnce.Do(func() { close(b.readyCh) })
}

func (b *Bot) onInteractionCreate(session *dg.Session, interaction *dg.InteractionCreate) {
	defer b.recoverPanic("interaction")

	ctx, cancel := context.WithTimeout(context.Background(), interactionTimeout)
	defer cancel()
	ic := interact.New(ctx, session, interaction)

	switch interaction.Type {
	case dg.InteractionApplicationCommand:
		b.handleCommand(ic)
	case dg.InteractionMessageComponent:
		b.handleComponent(ic)
	case dg.InteractionModalSubmit:
		b.handleModal(ic)
	case dg.InteractionApplicationCommandAutocomplete:
		b.handleAutocomplete(ic)
	default:
		b.log.Debug("ignoring interaction type", "type", interaction.Type)
	}
}

func (b *Bot) handleCommand(c *interact.Context) {
	data := c.Interaction.ApplicationCommandData()
	command, ok := b.commands[data.Name]
	if !ok {
		b.fail(c, fmt.Errorf("unknown command %q", data.Name), "command:"+data.Name)
		return
	}

	b.log.Debug("handling command",
		"command", data.Name,
		"guild_id", c.Interaction.GuildID,
		"user_id", interactionUserID(c.Interaction),
	)
	if err := command.Handler(c); err != nil {
		b.fail(c, err, "command:"+data.Name)
	}
}

func (b *Bot) handleComponent(c *interact.Context) {
	customID := c.Interaction.MessageComponentData().CustomID
	route, ok := matchRoute(b.components, customID)
	if !ok {
		b.log.Warn("unrouted component",
			"custom_id", customID,
			"guild_id", c.Interaction.GuildID,
			"user_id", interactionUserID(c.Interaction),
		)
		if err := c.ReplyEphemeral("This control is no longer available. Please run the command again."); err != nil {
			b.log.Error("rejecting stale component", "custom_id", customID, "err", err)
		}
		return
	}
	if err := route.Handler(c); err != nil {
		b.fail(c, err, "component:"+route.Prefix)
	}
}

func (b *Bot) handleModal(c *interact.Context) {
	customID := c.Interaction.ModalSubmitData().CustomID
	route, ok := matchRoute(b.modals, customID)
	if !ok {
		b.log.Warn("unrouted modal",
			"custom_id", customID,
			"guild_id", c.Interaction.GuildID,
			"user_id", interactionUserID(c.Interaction),
		)
		if err := c.ReplyEphemeral("This form is no longer available. Please run the command again."); err != nil {
			b.log.Error("rejecting stale modal", "custom_id", customID, "err", err)
		}
		return
	}
	if err := route.Handler(c); err != nil {
		b.fail(c, err, "modal:"+route.Prefix)
	}
}

func (b *Bot) handleAutocomplete(c *interact.Context) {
	// Individual modules will register autocomplete providers in M1/M2.
	if err := c.Autocomplete(nil); err != nil {
		b.log.Error("responding to autocomplete", "err", err)
	}
}

func (b *Bot) onMessageCreate(session *dg.Session, message *dg.MessageCreate) {
	defer b.recoverPanic("message")

	if message == nil || message.Message == nil || message.Author == nil || message.Author.Bot {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), messageTimeout)
	defer cancel()

	for _, mod := range b.modules {
		handled, err := mod.HandleMessage(ctx, session, message)
		if err != nil {
			b.log.Error("message module failed", "module", mod.Name(), "err", err)
			continue
		}
		if handled {
			return
		}
	}
}

func (b *Bot) onGuildMemberAdd(session *dg.Session, event *dg.GuildMemberAdd) {
	defer b.recoverPanic("member join")

	if event == nil || event.Member == nil || event.User == nil {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), memberJoinTimeout)
	defer cancel()

	for _, mod := range b.modules {
		provider, ok := mod.(module.MemberJoinProvider)
		if !ok {
			continue
		}
		handled, err := provider.HandleMemberJoin(ctx, session, event)
		if err != nil {
			b.log.Error("member join module failed", "module", mod.Name(), "err", err)
			continue
		}
		if handled {
			return
		}
	}
}

func (b *Bot) onGuildMemberRemove(session *dg.Session, event *dg.GuildMemberRemove) {
	defer b.recoverPanic("member leave")

	if event == nil || event.Member == nil || event.User == nil {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), memberLeaveTimeout)
	defer cancel()

	for _, mod := range b.modules {
		provider, ok := mod.(module.MemberLeaveProvider)
		if !ok {
			continue
		}
		handled, err := provider.HandleMemberLeave(ctx, session, event)
		if err != nil {
			b.log.Error("member leave module failed", "module", mod.Name(), "err", err)
			continue
		}
		if handled {
			return
		}
	}
}

func (b *Bot) onVoiceStateUpdate(session *dg.Session, event *dg.VoiceStateUpdate) {
	defer b.recoverPanic("voice state")

	if event == nil || event.VoiceState == nil {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), voiceStateTimeout)
	defer cancel()

	for _, mod := range b.modules {
		provider, ok := mod.(module.VoiceStateProvider)
		if !ok {
			continue
		}
		handled, err := provider.HandleVoiceStateUpdate(ctx, session, event)
		if err != nil {
			b.log.Error("voice state module failed", "module", mod.Name(), "err", err)
			continue
		}
		if handled {
			return
		}
	}
}

func (b *Bot) fail(c *interact.Context, handlerErr error, label string) {
	b.log.Error("interaction handler failed", "handler", label, "err", handlerErr)

	const userMessage = "Something went wrong. The error has been logged."
	var sendErr error
	if c.Responded() {
		sendErr = c.Followup(userMessage)
	} else {
		sendErr = c.ReplyEphemeral(userMessage)
	}
	if sendErr != nil {
		b.log.Error("reporting handler error", "handler", label, "err", sendErr)
	}
}

func (b *Bot) recoverPanic(where string) {
	if recovered := recover(); recovered != nil {
		b.log.Error("panic in Discord handler",
			"where", where,
			"panic", recovered,
			"stack", string(debug.Stack()),
		)
	}
}

func interactionUserID(interaction *dg.InteractionCreate) string {
	if interaction.Member != nil && interaction.Member.User != nil {
		return interaction.Member.User.ID
	}
	if interaction.User != nil {
		return interaction.User.ID
	}
	return ""
}

func validateRoutes(owner string, routes, existing []module.Route) error {
	seen := make(map[string]struct{}, len(existing)+len(routes))
	for _, route := range existing {
		seen[route.Prefix] = struct{}{}
	}
	for _, route := range routes {
		if strings.TrimSpace(route.Prefix) == "" {
			return fmt.Errorf("bot: module %q has a route with an empty prefix", owner)
		}
		if route.Handler == nil {
			return fmt.Errorf("bot: module %q route %q has a nil handler", owner, route.Prefix)
		}
		if _, duplicate := seen[route.Prefix]; duplicate {
			return fmt.Errorf("bot: module %q has duplicate route prefix %q", owner, route.Prefix)
		}
		seen[route.Prefix] = struct{}{}
	}
	return nil
}

func sortRoutes(routes []module.Route) {
	sort.SliceStable(routes, func(i, j int) bool {
		return len(routes[i].Prefix) > len(routes[j].Prefix)
	})
}

func matchRoute(routes []module.Route, customID string) (module.Route, bool) {
	for _, route := range routes {
		if strings.HasPrefix(customID, route.Prefix) {
			return route, true
		}
	}
	return module.Route{}, false
}
