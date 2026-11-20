package selfroles

import (
	"fmt"
	"strings"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
)

func moduleDashboard(cfg guild.Config, groups []Group) (*dg.MessageEmbed, []dg.MessageComponent) {
	embed := &dg.MessageEmbed{
		Title: "Nebot Module: Self-Assignable Roles",
		Description: "Manage role menus that allow members to assign roles to themselves via embeds with buttons.\n\n" +
			"**Quick Start:**\n" +
			"1. Click **Create New Group** and set a name and mode.\n" +
			"2. Click the group in the dropdown to add Discord roles and configure restrictions.\n" +
			"3. Deploy the role menu embed to a text channel.",
		Color: 0x3498DB,
		Fields: []*dg.MessageEmbedField{
			{Name: "Module Status", Value: statusText(cfg.SelfRolesEnabled), Inline: true},
			{Name: "Total Groups", Value: fmt.Sprintf("%d group(s)", len(groups)), Inline: true},
		},
	}

	if len(groups) > 0 {
		lines := make([]string, 0, len(groups))
		for _, group := range groups {
			lines = append(lines, fmt.Sprintf("• **%s** (%s mode, %d roles)", group.Name, group.Mode, len(group.Roles)))
		}
		embed.Fields = append(embed.Fields, &dg.MessageEmbedField{
			Name: "Groups Overview", Value: truncate(strings.Join(lines, "\n"), 1024), Inline: false,
		})
	}

	components := []dg.MessageComponent{
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{Label: "Toggle Module", Style: dg.PrimaryButton, CustomID: ToggleCustomID},
			dg.Button{Label: "Create New Group", Style: dg.SuccessButton, CustomID: CreateCustomID},
		}},
	}

	if len(groups) > 0 {
		options := make([]dg.SelectMenuOption, 0, min(len(groups), 25))
		for _, group := range groups {
			if len(options) == 25 {
				break
			}
			options = append(options, dg.SelectMenuOption{
				Label:       truncate(group.Name, 100),
				Description: "Mode: " + group.Mode,
				Value:       GroupKey(group.Name),
			})
		}
		components = append(components, dg.ActionsRow{Components: []dg.MessageComponent{
			dg.SelectMenu{
				MenuType:    dg.StringSelectMenu,
				CustomID:    GroupSelectCustomID,
				Placeholder: "Select a Group to Configure...",
				MinValues:   intPointer(1),
				MaxValues:   1,
				Options:     options,
			},
		}})
	}

	components = append(components, dg.ActionsRow{Components: []dg.MessageComponent{
		dg.Button{Label: "Back to Modules", Style: dg.DangerButton, CustomID: AdminBackCustomID},
	}})
	return embed, components
}

func groupDashboard(group Group, key string) (*dg.MessageEmbed, []dg.MessageComponent) {
	embed := &dg.MessageEmbed{
		Title:       fmt.Sprintf("Configure Group: %s", group.Name),
		Description: "Manage settings, add/remove roles, and deploy the interactive role selection menu.",
		Color:       0x3498DB,
		Fields: []*dg.MessageEmbedField{
			{Name: "Mode", Value: strings.ToUpper(group.Mode), Inline: true},
		},
	}

	switch group.Mode {
	case ModeSingle:
		embed.Fields = append(embed.Fields,
			&dg.MessageEmbedField{Name: "Auto Take Away", Value: yesNo(group.AutoTakeAway), Inline: true},
			&dg.MessageEmbedField{Name: "Require One", Value: yesNo(group.RequireOne), Inline: true},
		)
	case ModeMulti:
		embed.Fields = append(embed.Fields,
			&dg.MessageEmbedField{Name: "Min Amount", Value: fmt.Sprintf("%d", group.MinAmount), Inline: true},
			&dg.MessageEmbedField{Name: "Max Amount", Value: fmt.Sprintf("%d", group.MaxAmount), Inline: true},
		)
	}

	displayName := group.DisplayName
	if displayName == "" {
		displayName = "Default"
	}
	description := group.Description
	if description == "" {
		description = "Default"
	}
	embed.Fields = append(embed.Fields,
		&dg.MessageEmbedField{Name: "Embed Custom Title", Value: truncate(displayName, 1024), Inline: true},
		&dg.MessageEmbedField{Name: "Embed Custom Desc", Value: truncate(description, 1024), Inline: true},
		&dg.MessageEmbedField{Name: "Embed Color Border", Value: strings.ToUpper(normalizeColor(group.Color)), Inline: true},
	)

	roleLines := "None configured."
	if len(group.Roles) > 0 {
		lines := make([]string, 0, len(group.Roles))
		for _, role := range group.Roles {
			name := role.Name
			if name == "" {
				name = "Unnamed"
			}
			lines = append(lines, fmt.Sprintf("• <@&%d> (%s) [Style: %s]", role.RoleID, name, strings.ToUpper(normalizeStyle(role.Style))))
		}
		roleLines = truncate(strings.Join(lines, "\n"), 1024)
	}
	embed.Fields = append(embed.Fields, &dg.MessageEmbedField{Name: "Configured Roles", Value: roleLines, Inline: false})

	components := []dg.MessageComponent{
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.Button{Label: "Toggle Mode", Style: dg.PrimaryButton, CustomID: groupActionID(ToggleModePrefix, key)},
			dg.Button{Label: "Edit Limits / Flags", Style: dg.PrimaryButton, CustomID: groupActionID(EditLimitsPrefix, key)},
			dg.Button{Label: "Delete Group", Style: dg.DangerButton, CustomID: groupActionID(DeletePrefix, key)},
			dg.Button{Label: "Back to Dashboard", Style: dg.SecondaryButton, CustomID: BackCustomID},
		}},
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.SelectMenu{
				MenuType:    dg.RoleSelectMenu,
				CustomID:    groupActionID(AddRolePrefix, key),
				Placeholder: "Select a Role to Add...",
				MinValues:   intPointer(1),
				MaxValues:   1,
			},
		}},
	}

	if len(group.Roles) > 0 {
		options := make([]dg.SelectMenuOption, 0, min(len(group.Roles), 25))
		for _, role := range group.Roles {
			if len(options) == 25 {
				break
			}
			name := role.Name
			if name == "" {
				name = fmt.Sprintf("Role %d", role.RoleID)
			}
			options = append(options, dg.SelectMenuOption{Label: truncate(name, 100), Value: fmt.Sprintf("%d", role.RoleID)})
		}
		components = append(components, dg.ActionsRow{Components: []dg.MessageComponent{
			dg.SelectMenu{
				MenuType:    dg.StringSelectMenu,
				CustomID:    groupActionID(RemoveRolePrefix, key),
				Placeholder: "Select a Role to Remove...",
				MinValues:   intPointer(1),
				MaxValues:   1,
				Options:     options,
			},
		}})
	}

	components = append(components,
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.SelectMenu{
				MenuType:     dg.ChannelSelectMenu,
				CustomID:     groupActionID(DeployPrefix, key),
				Placeholder:  "Deploy Role Menu to Channel...",
				MinValues:    intPointer(1),
				MaxValues:    1,
				ChannelTypes: []dg.ChannelType{dg.ChannelTypeGuildText},
			},
		}},
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.SelectMenu{
				MenuType:    dg.StringSelectMenu,
				CustomID:    groupActionID(DetailsPrefix, key),
				Placeholder: "Configure Group Embed & Colors...",
				MinValues:   intPointer(1),
				MaxValues:   1,
				Options: []dg.SelectMenuOption{
					{Label: "Set Embed Title", Value: "title", Description: "Customize the embed title"},
					{Label: "Set Embed Description", Value: "desc", Description: "Customize the embed description"},
					{Label: "Set Embed Color", Value: "color", Description: "Customize the embed border color"},
					{Label: "Configure Button Colors", Value: "btn_colors", Description: "Change colors of role buttons"},
				},
			},
		}},
	)
	return embed, components
}

func styleDashboard(group Group, key string, selectedRoleID int64) (*dg.MessageEmbed, []dg.MessageComponent) {
	embed := &dg.MessageEmbed{
		Title:       fmt.Sprintf("Style Buttons: %s", group.Name),
		Description: "Select a role and then select a button color style to apply.",
		Color:       0x3498DB,
	}

	roleLines := "None configured."
	if len(group.Roles) > 0 {
		lines := make([]string, 0, len(group.Roles))
		for _, role := range group.Roles {
			lines = append(lines, fmt.Sprintf("• <@&%d>: **%s**", role.RoleID, strings.ToUpper(normalizeStyle(role.Style))))
		}
		roleLines = truncate(strings.Join(lines, "\n"), 1024)
	}
	embed.Fields = []*dg.MessageEmbedField{{Name: "Role Button Styles", Value: roleLines, Inline: false}}

	components := []dg.MessageComponent{}
	if len(group.Roles) > 0 {
		options := make([]dg.SelectMenuOption, 0, min(len(group.Roles), 25))
		for _, role := range group.Roles {
			if len(options) == 25 {
				break
			}
			name := role.Name
			if name == "" {
				name = fmt.Sprintf("Role %d", role.RoleID)
			}
			options = append(options, dg.SelectMenuOption{
				Label:       truncate(name, 100),
				Value:       fmt.Sprintf("%d", role.RoleID),
				Description: "Style: " + normalizeStyle(role.Style),
			})
		}
		components = append(components,
			dg.ActionsRow{Components: []dg.MessageComponent{
				dg.SelectMenu{
					MenuType:    dg.StringSelectMenu,
					CustomID:    groupActionID(StyleRolePrefix, key),
					Placeholder: "Select a Role to Style...",
					MinValues:   intPointer(1),
					MaxValues:   1,
					Options:     options,
				},
			}},
			dg.ActionsRow{Components: []dg.MessageComponent{
				dg.SelectMenu{
					MenuType:    dg.StringSelectMenu,
					CustomID:    styleColorID(key, selectedRoleID),
					Placeholder: "Choose Button Color...",
					MinValues:   intPointer(1),
					MaxValues:   1,
					Options: []dg.SelectMenuOption{
						{Label: "Blurple (Primary)", Value: StyleBlurple},
						{Label: "Grey (Secondary)", Value: StyleGrey},
						{Label: "Green (Success)", Value: StyleGreen},
						{Label: "Red (Danger)", Value: StyleRed},
					},
				},
			}},
		)
	}
	components = append(components, dg.ActionsRow{Components: []dg.MessageComponent{
		dg.Button{Label: "Back to Group Config", Style: dg.SecondaryButton, CustomID: groupActionID(StyleBackPrefix, key)},
	}})
	return embed, components
}

func roleMenu(group Group, key string) (*dg.MessageEmbed, []dg.MessageComponent) {
	title := group.DisplayName
	if title == "" {
		title = "Self-Assignable Roles: " + group.Name
	}
	description := group.Description
	if description == "" {
		description = "Select the roles you want to assign/remove by clicking the buttons below."
	}
	mode := "Select multiple roles"
	if group.Mode == ModeSingle {
		mode = "Select one role"
	}
	embed := &dg.MessageEmbed{
		Title:       truncate(title, 256),
		Description: truncate(description, 4096),
		Color:       embedColor(group.Color),
		Fields:      []*dg.MessageEmbedField{{Name: "Mode", Value: mode, Inline: false}},
	}

	buttons := make([]dg.Button, 0, min(len(group.Roles), 25))
	for _, role := range group.Roles {
		if len(buttons) == 25 {
			break
		}
		label := role.Name
		if label == "" {
			label = fmt.Sprintf("Role %d", role.RoleID)
		}
		buttons = append(buttons, dg.Button{
			Label:    truncate(label, 80),
			Style:    buttonStyle(role.Style),
			CustomID: roleToggleID(key, role.RoleID),
		})
	}

	components := make([]dg.MessageComponent, 0, 5)
	for start := 0; start < len(buttons); start += 5 {
		end := min(start+5, len(buttons))
		row := make([]dg.MessageComponent, 0, end-start)
		for _, button := range buttons[start:end] {
			row = append(row, button)
		}
		components = append(components, dg.ActionsRow{Components: row})
	}
	return embed, components
}

func buttonStyle(style string) dg.ButtonStyle {
	switch normalizeStyle(style) {
	case StyleGrey:
		return dg.SecondaryButton
	case StyleGreen:
		return dg.SuccessButton
	case StyleRed:
		return dg.DangerButton
	default:
		return dg.PrimaryButton
	}
}

func embedColor(color string) int {
	switch normalizeColor(color) {
	case ColorRed:
		return 0xE74C3C
	case ColorGreen:
		return 0x2ECC71
	case ColorTeal:
		return 0x1ABC9C
	case ColorOrange:
		return 0xE67E22
	case ColorPurple:
		return 0x9B59B6
	case ColorGold:
		return 0xF1C40F
	case ColorGrey:
		return 0x95A5A6
	default:
		return 0x3498DB
	}
}

func statusText(enabled bool) string {
	if enabled {
		return "[ENABLED]"
	}
	return "[DISABLED]"
}

func yesNo(value bool) string {
	if value {
		return "YES"
	}
	return "NO"
}

func truncate(value string, maxRunes int) string {
	runes := []rune(value)
	if len(runes) <= maxRunes {
		return value
	}
	return string(runes[:maxRunes-3]) + "..."
}

func intPointer(value int) *int { return &value }
