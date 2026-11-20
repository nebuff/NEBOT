package analytics

import (
	"fmt"
	"strings"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
)

// Dashboard builds the analytics panel and its components.
func Dashboard(cfg guild.Config) (*dg.MessageEmbed, []dg.MessageComponent) {
	embed := &dg.MessageEmbed{
		Title:       "Nebot Module: Server Analytics",
		Description: "Configure community health tracking parameters, data collection windows, and administrative privacy settings.",
		Color:       dashboardColor,
		Fields: []*dg.MessageEmbedField{
			{Name: "Status", Value: statusText(cfg.AnalyticsEnabled), Inline: true},
			{Name: "Excluded Channels", Value: channelMentions(cfg.AnalyticsExcludedChannels), Inline: false},
		},
	}

	components := []dg.MessageComponent{
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{Label: "Toggle Analytics", Style: dg.PrimaryButton, CustomID: ToggleCustomID},
			dg.Button{Label: "Exclude Channels", Style: dg.SecondaryButton, CustomID: ExcludeCustomID},
		}},
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{Label: "Clear Historical Data", Style: dg.DangerButton, CustomID: ClearCustomID},
			dg.Button{Label: "Back to Modules", Style: dg.DangerButton, CustomID: BackCustomID},
		}},
	}
	return embed, components
}

func excludeComponents() []dg.MessageComponent {
	return []dg.MessageComponent{
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.SelectMenu{
				MenuType:    dg.ChannelSelectMenu,
				CustomID:    ChannelsCustomID,
				Placeholder: "Select channels to exclude...",
				MinValues:   intPointer(0),
				MaxValues:   25,
				ChannelTypes: []dg.ChannelType{
					dg.ChannelTypeGuildText,
					dg.ChannelTypeGuildNews,
					dg.ChannelTypeGuildVoice,
				},
			},
		}},
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{Label: "Back", Style: dg.DangerButton, CustomID: OpenCustomID},
		}},
	}
}

func channelMentions(channelIDs []int64) string {
	if len(channelIDs) == 0 {
		return "None"
	}
	mentions := make([]string, 0, len(channelIDs))
	for _, channelID := range channelIDs {
		mentions = append(mentions, fmt.Sprintf("<#%d>", channelID))
	}
	return strings.Join(mentions, ", ")
}

func statusText(enabled bool) string {
	if enabled {
		return "[ENABLED]"
	}
	return "[DISABLED]"
}

func intPointer(value int) *int { return &value }
