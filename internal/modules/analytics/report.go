package analytics

import (
	"fmt"

	dg "github.com/bwmarrin/discordgo"

	analyticsdata "github.com/nebuff/n-bot/internal/analytics"
)

func reportEmbed(guildName string, report analyticsdata.Report) *dg.MessageEmbed {
	peakHour := "None"
	if !report.PeakHour.IsZero() {
		peakHour = report.PeakHour.Format("15:00 UTC")
	}

	mostActive := "None (0.0% of total volume)"
	if report.MostActiveChannelID != "" {
		mostActive = fmt.Sprintf(
			"<#%s> (%.1f%% of total volume)",
			report.MostActiveChannelID,
			report.MostActivePercent,
		)
	}

	return &dg.MessageEmbed{
		Title:       fmt.Sprintf("Server Analytics Report for %s", guildName),
		Description: "Activity metrics and user churn trends over the selected observation window.",
		Color:       dashboardColor,
		Fields: []*dg.MessageEmbedField{
			{
				Name: "Chat Activity Metrics",
				Value: fmt.Sprintf(
					"Total Messages Processed: %d\nPeak Message Hour: %s with %d messages\nMost Active Text Channel: %s",
					report.TotalMessages, peakHour, report.PeakCount, mostActive,
				),
				Inline: false,
			},
			{
				Name: "Member Churn Trends",
				Value: fmt.Sprintf(
					"Members Joined: %d\nMembers Left: %d\nNet Growth: %d",
					report.Joins, report.Leaves, report.NetGrowth,
				),
				Inline: false,
			},
			{
				Name: "Voice Activity Metrics",
				Value: fmt.Sprintf(
					"Peak Voice Concurrency: %d members\nAverage Voice Concurrency: %.1f members",
					report.VoicePeak, report.VoiceAverage,
				),
				Inline: false,
			},
		},
	}
}
