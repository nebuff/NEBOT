// Package interact wraps a Discord interaction with response helpers that
// enforce a single initial response.
package interact

import (
	"context"
	"errors"

	dg "github.com/bwmarrin/discordgo"
)

// ErrAlreadyResponded is returned when a handler tries to send a second initial
// interaction response. Use Followup for subsequent messages.
var ErrAlreadyResponded = errors.New("interaction already responded")

// Context is the per-handler view of an interaction.
type Context struct {
	ctx         context.Context
	Session     *dg.Session
	Interaction *dg.InteractionCreate
	responded   bool
}

// New creates a handler context.
func New(ctx context.Context, session *dg.Session, interaction *dg.InteractionCreate) *Context {
	if ctx == nil {
		ctx = context.Background()
	}
	return &Context{ctx: ctx, Session: session, Interaction: interaction}
}

// Context returns the handler deadline/cancellation context.
func (c *Context) Context() context.Context {
	return c.ctx
}

// Responded reports whether the initial interaction response was sent.
func (c *Context) Responded() bool {
	return c.responded
}

// Reply sends a public channel message.
func (c *Context) Reply(content string) error {
	return c.respond(dg.InteractionResponseChannelMessageWithSource, &dg.InteractionResponseData{
		Content: content,
	})
}

// ReplyEphemeral sends a message only the invoking user can see.
func (c *Context) ReplyEphemeral(content string) error {
	return c.respond(dg.InteractionResponseChannelMessageWithSource, &dg.InteractionResponseData{
		Content: content,
		Flags:   dg.MessageFlagsEphemeral,
	})
}

// ReplyEmbed sends a public embed.
func (c *Context) ReplyEmbed(embed *dg.MessageEmbed) error {
	if embed == nil {
		return errors.New("reply embed is nil")
	}
	return c.respond(dg.InteractionResponseChannelMessageWithSource, &dg.InteractionResponseData{
		Embeds: []*dg.MessageEmbed{embed},
	})
}

// ReplyEmbedEphemeral sends an ephemeral embed.
func (c *Context) ReplyEmbedEphemeral(embed *dg.MessageEmbed) error {
	if embed == nil {
		return errors.New("reply embed is nil")
	}
	return c.respond(dg.InteractionResponseChannelMessageWithSource, &dg.InteractionResponseData{
		Embeds: []*dg.MessageEmbed{embed},
		Flags:  dg.MessageFlagsEphemeral,
	})
}

// ReplyEmbedWithComponents sends an embed with interactive components, either
// publicly or ephemerally.
func (c *Context) ReplyEmbedWithComponents(embed *dg.MessageEmbed, components []dg.MessageComponent, ephemeral bool) error {
	if embed == nil {
		return errors.New("reply embed is nil")
	}
	data := &dg.InteractionResponseData{
		Embeds:     []*dg.MessageEmbed{embed},
		Components: components,
	}
	if ephemeral {
		data.Flags = dg.MessageFlagsEphemeral
	}
	return c.respond(dg.InteractionResponseChannelMessageWithSource, data)
}

// Update edits the message that owns a button/select/modal interaction.
func (c *Context) Update(content string, embed *dg.MessageEmbed, components []dg.MessageComponent) error {
	data := &dg.InteractionResponseData{
		Content:    content,
		Components: components,
	}
	if embed != nil {
		data.Embeds = []*dg.MessageEmbed{embed}
	}
	return c.respond(dg.InteractionResponseUpdateMessage, data)
}

// ShowModal opens a modal form for the user. The caller's next interaction is
// routed by the modal's custom ID.
func (c *Context) ShowModal(customID, title string, components []dg.MessageComponent) error {
	if customID == "" || title == "" {
		return errors.New("modal custom_id and title are required")
	}
	return c.respond(dg.InteractionResponseModal, &dg.InteractionResponseData{
		CustomID:   customID,
		Title:      title,
		Components: components,
	})
}

// Defer acknowledges an interaction while a slower operation completes.
func (c *Context) Defer(ephemeral bool) error {
	data := &dg.InteractionResponseData{}
	if ephemeral {
		data.Flags = dg.MessageFlagsEphemeral
	}
	return c.respond(dg.InteractionResponseDeferredChannelMessageWithSource, data)
}

// Autocomplete responds to an autocomplete interaction with up to 25 choices.
func (c *Context) Autocomplete(choices []*dg.ApplicationCommandOptionChoice) error {
	return c.respond(dg.InteractionApplicationCommandAutocompleteResult, &dg.InteractionResponseData{
		Choices: choices,
	})
}

// Followup sends a message after the initial response (or falls back to Reply
// when nothing has been sent yet).
func (c *Context) Followup(content string) error {
	if !c.responded {
		return c.Reply(content)
	}
	_, err := c.Session.FollowupMessageCreate(c.Interaction.Interaction, true, &dg.WebhookParams{
		Content: content,
	})
	return err
}

func (c *Context) respond(responseType dg.InteractionResponseType, data *dg.InteractionResponseData) error {
	if c.responded {
		return ErrAlreadyResponded
	}
	err := c.Session.InteractionRespond(c.Interaction.Interaction, &dg.InteractionResponse{
		Type: responseType,
		Data: data,
	})
	if err != nil {
		return err
	}
	c.responded = true
	return nil
}
