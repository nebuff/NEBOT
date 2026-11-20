// Package audit sends setting-change audit embeds.
package audit

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"time"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
)

const auditColor = 0x3498DB

// SettingChange sends the Python-compatible config audit embed to the guild's
// global log channel, if configured. The send is asynchronous so interaction
// handlers are not blocked by channel permissions or rate limits.
func SettingChange(session *dg.Session, cfg guild.Config, interaction *dg.InteractionCreate, action string, log *slog.Logger) {
	if session == nil || cfg.GlobalLogChannelID == nil {
		return
	}
	if log == nil {
		log = slog.Default()
	}

	channelID := strconv.FormatInt(*cfg.GlobalLogChannelID, 10)
	userID, userName := actor(interaction)
	actorText := "unknown user"
	if userID != "" {
		actorText = fmt.Sprintf("<@%s> (%s)", userID, userName)
	}
	embed := &dg.MessageEmbed{
		Title: "Config/Settings Updated",
		Description: fmt.Sprintf(
			"User %s made a change:\n%s",
			actorText, truncateAction(action),
		),
		Color:     auditColor,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	}

	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if _, err := session.ChannelMessageSendEmbed(channelID, embed, dg.WithContext(ctx)); err != nil {
			log.Warn("sending setting-change audit log", "channel_id", channelID, "err", err)
		}
	}()
}

func actor(interaction *dg.InteractionCreate) (id, name string) {
	if interaction == nil {
		return "", ""
	}
	if interaction.Member != nil && interaction.Member.User != nil {
		return interaction.Member.User.ID, interaction.Member.User.Username
	}
	if interaction.User != nil {
		return interaction.User.ID, interaction.User.Username
	}
	return "", ""
}

func truncateAction(action string) string {
	runes := []rune(action)
	if len(runes) <= 3000 {
		return action
	}
	return string(runes[:2997]) + "..."
}
