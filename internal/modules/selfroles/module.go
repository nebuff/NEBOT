package selfroles

import (
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"strings"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/audit"
	"github.com/nebuff/n-bot/internal/auth"
	"github.com/nebuff/n-bot/internal/guild"
	"github.com/nebuff/n-bot/internal/interact"
	"github.com/nebuff/n-bot/internal/module"
)

const permissionMessage = "I do not have permissions to manage roles. Please verify my hierarchy position."

// Module implements self-assignable role menus and their configuration.
type Module struct {
	module.Base

	guilds  *guild.Cache
	ownerID int64
	log     *slog.Logger
}

// New creates the self-roles module.
func New(guilds *guild.Cache, ownerID int64, log *slog.Logger) *Module {
	if guilds == nil {
		panic("selfroles: nil guild cache")
	}
	if log == nil {
		log = slog.Default()
	}
	return &Module{guilds: guilds, ownerID: ownerID, log: log}
}

// Name implements module.Module.
func (m *Module) Name() string { return "selfroles" }

// Components implements module.ComponentProvider.
func (m *Module) Components() []module.Route {
	return []module.Route{
		{Prefix: OpenCustomID, Name: "open", Handler: m.open},
		{Prefix: ToggleCustomID, Name: "toggle", Handler: m.toggle},
		{Prefix: CreateCustomID, Name: "create", Handler: m.create},
		{Prefix: GroupSelectCustomID, Name: "group", Handler: m.selectGroup},
		{Prefix: BackCustomID, Name: "back", Handler: m.back},
		{Prefix: ToggleModePrefix, Name: "mode", Handler: m.toggleMode},
		{Prefix: EditLimitsPrefix, Name: "limits", Handler: m.editLimits},
		{Prefix: DeletePrefix, Name: "delete", Handler: m.deleteGroup},
		{Prefix: AddRolePrefix, Name: "addrole", Handler: m.addRole},
		{Prefix: RemoveRolePrefix, Name: "removerole", Handler: m.removeRole},
		{Prefix: DeployPrefix, Name: "deploy", Handler: m.deploy},
		{Prefix: DetailsPrefix, Name: "details", Handler: m.details},
		{Prefix: StylePrefix, Name: "style", Handler: m.style},
		{Prefix: StyleBackPrefix, Name: "styleback", Handler: m.styleBack},
		{Prefix: StyleRolePrefix, Name: "stylerole", Handler: m.styleRole},
		{Prefix: StyleColorPrefix, Name: "stylecolor", Handler: m.styleColor},
		{Prefix: RoleTogglePrefix, Name: "roletoggle", Handler: m.roleToggle},
		{Prefix: LegacyPrefix, Name: "legacyroletoggle", Handler: m.legacyRoleToggle},
	}
}

// Modals implements module.ModalProvider.
func (m *Module) Modals() []module.Route {
	return []module.Route{
		{Prefix: CreateModalID, Name: "create", Handler: m.createGroup},
		{Prefix: LimitsModalPrefix, Name: "limits", Handler: m.limitsModal},
		{Prefix: TitleModalPrefix, Name: "title", Handler: m.titleModal},
		{Prefix: DescModalPrefix, Name: "description", Handler: m.descriptionModal},
		{Prefix: ColorModalPrefix, Name: "color", Handler: m.colorModal},
	}
}

func (m *Module) open(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	return m.renderModule(c, cfg, groups)
}

func (m *Module) toggle(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	cfg.SelfRolesEnabled = !cfg.SelfRolesEnabled
	if err := m.guilds.Save(c.Context(), cfg); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Toggled Self-Assignable Roles module to `%s`", enabledWord(cfg.SelfRolesEnabled),
	), m.log)

	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	return m.renderModule(c, cfg, groups)
}

func (m *Module) create(c *interact.Context) error {
	_, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	return c.ShowModal(CreateModalID, "Create Self Role Group", []dg.MessageComponent{
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.TextInput{
				CustomID:    "group_name",
				Label:       "Group Name",
				Style:       dg.TextInputShort,
				Placeholder: "e.g. Pronouns",
				Required:    true,
				MinLength:   2,
				MaxLength:   50,
			},
		}},
		dg.ActionsRow{Components: []dg.MessageComponent{
			dg.TextInput{
				CustomID:    "group_mode",
				Label:       "Mode (single / multi / none)",
				Style:       dg.TextInputShort,
				Placeholder: "none",
				Value:       ModeNone,
				Required:    true,
				MinLength:   4,
				MaxLength:   6,
			},
		}},
	})
}

func (m *Module) createGroup(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}

	name := strings.TrimSpace(modalValue(c, "group_name"))
	mode := strings.TrimSpace(modalValue(c, "group_mode"))
	group, err := NewGroup(name, mode)
	if err != nil {
		return c.ReplyEphemeral(err.Error())
	}

	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	for _, existing := range groups {
		if strings.EqualFold(existing.Name, group.Name) {
			return c.ReplyEphemeral("A group with that name already exists!")
		}
	}
	groups = append(groups, group)
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Created self role group: %s (mode: %s)", group.Name, group.Mode,
	), m.log)
	return m.renderModule(c, cfg, groups)
}

func (m *Module) selectGroup(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Select a group.")
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, values[0])
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	return m.renderGroup(c, groups, *group, GroupKey(group.Name))
}

func (m *Module) back(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	return m.renderModule(c, cfg, groups)
}

func (m *Module) toggleMode(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, ToggleModePrefix)
	if err != nil {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}

	modes := []string{ModeNone, ModeSingle, ModeMulti}
	group.Mode = modes[(indexOf(modes, group.Mode)+1)%len(modes)]
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Updated mode of self role group %s to %s", group.Name, group.Mode,
	), m.log)
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) editLimits(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, EditLimitsPrefix)
	if err != nil {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}

	switch group.Mode {
	case ModeSingle:
		group.AutoTakeAway = !group.AutoTakeAway
		group.RequireOne = !group.RequireOne
		if err := m.saveGroups(c, &cfg, groups); err != nil {
			return err
		}
		return m.renderGroup(c, groups, *group, key)
	case ModeMulti:
		return c.ShowModal(LimitsModalPrefix+key, "Edit Group Multi Limits", []dg.MessageComponent{
			dg.ActionsRow{Components: []dg.MessageComponent{
				dg.TextInput{
					CustomID:  "min_amount",
					Label:     "Minimum Amount",
					Style:     dg.TextInputShort,
					Value:     strconv.Itoa(group.MinAmount),
					Required:  true,
					MinLength: 1,
					MaxLength: 2,
				},
			}},
			dg.ActionsRow{Components: []dg.MessageComponent{
				dg.TextInput{
					CustomID:  "max_amount",
					Label:     "Maximum Amount",
					Style:     dg.TextInputShort,
					Value:     strconv.Itoa(group.MaxAmount),
					Required:  true,
					MinLength: 1,
					MaxLength: 2,
				},
			}},
		})
	default:
		return c.ReplyEphemeral("Limits are only configurable in `single` or `multi` mode.")
	}
}

func (m *Module) limitsModal(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.ModalSubmitData().CustomID, LimitsModalPrefix)
	if err != nil {
		return err
	}
	minValue, err := strconv.Atoi(strings.TrimSpace(modalValue(c, "min_amount")))
	if err != nil || minValue < 0 {
		return c.ReplyEphemeral("Invalid integers!")
	}
	maxValue, err := strconv.Atoi(strings.TrimSpace(modalValue(c, "max_amount")))
	if err != nil || maxValue < 0 {
		return c.ReplyEphemeral("Invalid integers!")
	}

	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	group.MinAmount = minValue
	group.MaxAmount = maxValue
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Updated limits on group %s: min=%d, max=%d", group.Name, minValue, maxValue,
	), m.log)
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) deleteGroup(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, DeletePrefix)
	if err != nil {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	name := group.Name
	filtered := make([]Group, 0, len(groups))
	for _, item := range groups {
		if GroupKey(item.Name) != key {
			filtered = append(filtered, item)
		}
	}
	if err := m.saveGroups(c, &cfg, filtered); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, "Deleted self role group: "+name, m.log)
	return m.renderModule(c, cfg, filtered)
}

func (m *Module) addRole(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, AddRolePrefix)
	if err != nil {
		return err
	}
	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Select a role.")
	}
	roleID, err := parseID(values[0], "role")
	if err != nil {
		return err
	}

	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	if group.FindRole(roleID) != nil {
		return c.ReplyEphemeral("This role is already in the group!")
	}

	roleMap, err := m.roleMap(c, c.Interaction.GuildID)
	if err != nil {
		m.log.Warn("resolving role name for self-role group", "guild_id", c.Interaction.GuildID, "role_id", roleID, "err", err)
	}
	roleName := fmt.Sprintf("Role %d", roleID)
	if info, found := roleMap[roleID]; found && info.Exists {
		roleName = info.Name
	}
	group.Roles = append(group.Roles, Role{
		RoleID:       roleID,
		Name:         roleName,
		AllowTakeOff: true,
		RequireRoles: []int64{},
		IgnoreRoles:  []int64{},
		Style:        StyleBlurple,
	})
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Added role %s to group: %s", roleName, group.Name,
	), m.log)
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) removeRole(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, RemoveRolePrefix)
	if err != nil {
		return err
	}
	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Select a role.")
	}
	roleID, err := parseID(values[0], "role")
	if err != nil {
		return err
	}

	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	filtered := make([]Role, 0, len(group.Roles))
	for _, role := range group.Roles {
		if role.RoleID != roleID {
			filtered = append(filtered, role)
		}
	}
	group.Roles = filtered
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Removed role %d from group: %s", roleID, group.Name,
	), m.log)
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) deploy(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, DeployPrefix)
	if err != nil {
		return err
	}
	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Select a channel.")
	}
	channelID, err := parseID(values[0], "channel")
	if err != nil {
		return err
	}

	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("Group not found!")
	}
	if len(group.Roles) == 0 {
		return c.ReplyEphemeral("Cannot deploy an empty role group!")
	}

	embed, components := roleMenu(*group, key)
	channel := strconv.FormatInt(channelID, 10)
	if c.Session == nil {
		return errors.New("selfroles: nil session")
	}
	if _, err := c.Session.ChannelMessageSendComplex(channel, &dg.MessageSend{
		Embeds:     []*dg.MessageEmbed{embed},
		Components: components,
	}, dg.WithContext(c.Context())); err != nil {
		m.log.Warn("deploying self-role menu", "channel_id", channel, "err", err)
		return c.ReplyEphemeral(fmt.Sprintf("I don't have permissions to send messages to <#%d>.", channelID))
	}
	return c.ReplyEphemeral(fmt.Sprintf("Role Menu deployed successfully to <#%d>!", channelID))
}

func (m *Module) details(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, DetailsPrefix)
	if err != nil {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Select an option.")
	}

	switch values[0] {
	case "title":
		return c.ShowModal(TitleModalPrefix+key, "Set Embed Title", []dg.MessageComponent{
			dg.ActionsRow{Components: []dg.MessageComponent{
				dg.TextInput{
					CustomID:    "title",
					Label:       "Embed Title",
					Style:       dg.TextInputShort,
					Placeholder: "e.g. Select your Pronouns",
					Value:       group.DisplayName,
					Required:    true,
					MinLength:   2,
					MaxLength:   100,
				},
			}},
		})
	case "desc":
		return c.ShowModal(DescModalPrefix+key, "Set Embed Description", []dg.MessageComponent{
			dg.ActionsRow{Components: []dg.MessageComponent{
				dg.TextInput{
					CustomID:    "description",
					Label:       "Embed Description",
					Style:       dg.TextInputParagraph,
					Placeholder: "e.g. Choose one or more options...",
					Value:       group.Description,
					Required:    true,
					MinLength:   2,
					MaxLength:   500,
				},
			}},
		})
	case "color":
		return c.ShowModal(ColorModalPrefix+key, "Set Embed Color", []dg.MessageComponent{
			dg.ActionsRow{Components: []dg.MessageComponent{
				dg.TextInput{
					CustomID:    "color",
					Label:       "Color (blue/red/green/teal/purple/etc)",
					Style:       dg.TextInputShort,
					Placeholder: "blue",
					Value:       normalizeColor(group.Color),
					Required:    true,
					MinLength:   3,
					MaxLength:   10,
				},
			}},
		})
	case "btn_colors":
		return m.renderStyle(c, groups, *group, key, 0)
	default:
		return c.ReplyEphemeral("Unknown group option.")
	}
}

func (m *Module) titleModal(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.ModalSubmitData().CustomID, TitleModalPrefix)
	if err != nil {
		return err
	}
	title := strings.TrimSpace(modalValue(c, "title"))
	if len([]rune(title)) < 2 {
		return c.ReplyEphemeral("Embed title must be at least 2 characters.")
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	group.DisplayName = title
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) descriptionModal(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.ModalSubmitData().CustomID, DescModalPrefix)
	if err != nil {
		return err
	}
	description := strings.TrimSpace(modalValue(c, "description"))
	if len([]rune(description)) < 2 {
		return c.ReplyEphemeral("Embed description must be at least 2 characters.")
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	group.Description = description
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) colorModal(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.ModalSubmitData().CustomID, ColorModalPrefix)
	if err != nil {
		return err
	}
	color := strings.ToLower(strings.TrimSpace(modalValue(c, "color")))
	if _, valid := validColors[color]; !valid {
		return c.ReplyEphemeral("Invalid color name! Must be blue/red/green/teal/orange/purple/gold/grey.")
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	group.Color = color
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) style(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, StylePrefix)
	if err != nil {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	return m.renderStyle(c, groups, *group, key, 0)
}

func (m *Module) styleRole(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, StyleRolePrefix)
	if err != nil {
		return err
	}
	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Select a role.")
	}
	roleID, err := parseID(values[0], "role")
	if err != nil {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	if group.FindRole(roleID) == nil {
		return c.ReplyEphemeral("This role configuration was not found.")
	}
	return m.renderStyle(c, groups, *group, key, roleID)
}

func (m *Module) styleColor(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, roleID, err := roleFromCustomID(c.Interaction.MessageComponentData().CustomID, StyleColorPrefix)
	if err != nil {
		return err
	}
	if roleID <= 0 {
		return c.ReplyEphemeral("Please select a role first!")
	}
	values := c.Interaction.MessageComponentData().Values
	if len(values) == 0 {
		return c.ReplyEphemeral("Choose a button color.")
	}
	style := strings.ToLower(strings.TrimSpace(values[0]))
	if _, valid := validStyles[style]; !valid {
		return c.ReplyEphemeral("Invalid button color.")
	}

	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	role := group.FindRole(roleID)
	if role == nil {
		return c.ReplyEphemeral("This role configuration was not found.")
	}
	role.Style = style
	if err := m.saveGroups(c, &cfg, groups); err != nil {
		return err
	}
	audit.SettingChange(c.Session, cfg, c.Interaction, fmt.Sprintf(
		"Set style of role %d in group %s to %s", roleID, group.Name, style,
	), m.log)
	return m.renderStyle(c, groups, *group, key, roleID)
}

func (m *Module) styleBack(c *interact.Context) error {
	cfg, ok, err := m.requireAdmin(c)
	if err != nil || !ok {
		return err
	}
	key, err := keyFromCustomID(c.Interaction.MessageComponentData().CustomID, StyleBackPrefix)
	if err != nil {
		return err
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}
	group := FindGroupByKey(groups, key)
	if group == nil {
		return c.ReplyEphemeral("This role group configuration was not found.")
	}
	return m.renderGroup(c, groups, *group, key)
}

func (m *Module) roleToggle(c *interact.Context) error {
	key, roleID, err := roleFromCustomID(c.Interaction.MessageComponentData().CustomID, RoleTogglePrefix)
	if err != nil {
		return err
	}
	return m.toggleRole(c, key, roleID, "")
}

func (m *Module) legacyRoleToggle(c *interact.Context) error {
	legacyGuild, groupName, roleID, err := parseLegacyCustomID(c.Interaction.MessageComponentData().CustomID)
	if err != nil {
		return err
	}
	if legacyGuild != c.Interaction.GuildID {
		return c.ReplyEphemeral("This role menu belongs to another server.")
	}
	return m.toggleRole(c, GroupKey(groupName), roleID, groupName)
}

func (m *Module) toggleRole(c *interact.Context, key string, roleID int64, legacyGroupName string) error {
	cfg, ok, err := m.loadConfig(c)
	if err != nil {
		return err
	}
	if !ok {
		return c.ReplyEphemeral("This action can only be performed in a server.")
	}
	groups, err := ParseGroups(cfg.SelfRolesGroups)
	if err != nil {
		return err
	}

	var group *Group
	if legacyGroupName != "" {
		group = FindGroup(groups, legacyGroupName)
	} else {
		group = FindGroupByKey(groups, key)
	}
	groupFound := group != nil
	var role *Role
	roleFound := false
	if group != nil {
		role = group.FindRole(roleID)
		roleFound = role != nil
	}

	member := c.Interaction.Member
	if member == nil || member.User == nil {
		if c.Session != nil && c.Session.State != nil && c.Interaction.User != nil {
			member, _ = c.Session.State.Member(c.Interaction.GuildID, c.Interaction.User.ID)
		}
	}
	if !cfg.SelfRolesEnabled || !groupFound || !roleFound || member == nil || member.User == nil {
		return c.ReplyEphemeral(ProblemMessage(cfg.SelfRolesEnabled, groupFound, roleFound, member != nil && member.User != nil))
	}

	roleMap, err := m.roleMap(c, c.Interaction.GuildID)
	if err != nil {
		return err
	}
	decision, allowed := PlanToggle(cfg.SelfRolesEnabled, *group, *role, member.Roles, roleMap, true)
	if !allowed {
		if decision.Message == "" {
			decision.Message = "The configured Discord role was not found in this server."
		}
		return c.ReplyEphemeral(decision.Message)
	}

	for _, id := range decision.RemoveIDs {
		if err := c.Session.GuildMemberRoleRemove(
			c.Interaction.GuildID,
			member.User.ID,
			strconv.FormatInt(id, 10),
			dg.WithContext(c.Context()),
		); err != nil {
			m.log.Error("removing self-assigned role", "guild_id", c.Interaction.GuildID, "role_id", id, "err", err)
			return c.ReplyEphemeral(permissionMessage)
		}
	}
	if decision.Add {
		if err := c.Session.GuildMemberRoleAdd(
			c.Interaction.GuildID,
			member.User.ID,
			strconv.FormatInt(roleID, 10),
			dg.WithContext(c.Context()),
		); err != nil {
			m.log.Error("adding self-assigned role", "guild_id", c.Interaction.GuildID, "role_id", roleID, "err", err)
			return c.ReplyEphemeral(permissionMessage)
		}
	}
	return c.ReplyEphemeral(decision.Message)
}

func (m *Module) renderModule(c *interact.Context, cfg guild.Config, groups []Group) error {
	embed, components := moduleDashboard(cfg, groups)
	return c.Update("", embed, components)
}

func (m *Module) renderGroup(c *interact.Context, groups []Group, group Group, key string) error {
	embed, components := groupDashboard(group, key)
	return c.Update("", embed, components)
}

func (m *Module) renderStyle(c *interact.Context, groups []Group, group Group, key string, selectedRoleID int64) error {
	embed, components := styleDashboard(group, key, selectedRoleID)
	return c.Update("", embed, components)
}

func (m *Module) saveGroups(c *interact.Context, cfg *guild.Config, groups []Group) error {
	raw, err := MarshalGroups(groups)
	if err != nil {
		return err
	}
	cfg.SelfRolesGroups = raw
	return m.guilds.Save(c.Context(), *cfg)
}

func (m *Module) requireAdmin(c *interact.Context) (guild.Config, bool, error) {
	cfg, ok, err := m.loadConfig(c)
	if err != nil || !ok {
		return cfg, ok, err
	}
	if !auth.IsAdmin(c.Session, c.Interaction.GuildID, c.Interaction.Member, c.Interaction.User, cfg, m.ownerID) {
		return cfg, false, c.ReplyEphemeral("Permission denied")
	}
	return cfg, true, nil
}

func (m *Module) loadConfig(c *interact.Context) (guild.Config, bool, error) {
	if c == nil || c.Interaction == nil {
		return guild.Config{}, false, errors.New("selfroles: nil interaction")
	}
	if c.Interaction.GuildID == "" {
		return guild.Config{}, false, nil
	}
	guildID, err := parseID(c.Interaction.GuildID, "guild")
	if err != nil {
		return guild.Config{}, false, err
	}
	cfg, err := m.guilds.Get(c.Context(), guildID)
	if err != nil {
		return guild.Config{}, false, err
	}
	return cfg, true, nil
}

func (m *Module) roleMap(c *interact.Context, guildID string) (map[int64]RoleInfo, error) {
	if c.Session == nil {
		return nil, errors.New("selfroles: nil session")
	}
	roles := map[string]*dg.Role{}
	if c.Session.State != nil {
		if guildState, err := c.Session.State.Guild(guildID); err == nil && guildState != nil {
			for _, role := range guildState.Roles {
				if role != nil {
					roles[role.ID] = role
				}
			}
		}
	}
	if len(roles) == 0 {
		loaded, err := c.Session.GuildRoles(guildID, dg.WithContext(c.Context()))
		if err != nil {
			return nil, fmt.Errorf("selfroles: load guild roles: %w", err)
		}
		for _, role := range loaded {
			if role != nil {
				roles[role.ID] = role
			}
		}
	}

	out := make(map[int64]RoleInfo, len(roles))
	for rawID, role := range roles {
		id, err := parseID(rawID, "role")
		if err != nil {
			continue
		}
		out[id] = RoleInfo{Name: role.Name, Exists: true}
	}
	return out, nil
}

func modalValue(c *interact.Context, customID string) string {
	data := c.Interaction.ModalSubmitData()
	for _, component := range data.Components {
		if value, ok := textInputValue(component, customID); ok {
			return value
		}
	}
	return ""
}

func textInputValue(component dg.MessageComponent, customID string) (string, bool) {
	switch value := component.(type) {
	case dg.TextInput:
		if value.CustomID == customID {
			return value.Value, true
		}
	case *dg.TextInput:
		if value != nil && value.CustomID == customID {
			return value.Value, true
		}
	case dg.ActionsRow:
		for _, child := range value.Components {
			if input, ok := textInputValue(child, customID); ok {
				return input, true
			}
		}
	case *dg.ActionsRow:
		if value == nil {
			return "", false
		}
		for _, child := range value.Components {
			if input, ok := textInputValue(child, customID); ok {
				return input, true
			}
		}
	}
	return "", false
}

func keyFromCustomID(customID, prefix string) (string, error) {
	if !strings.HasPrefix(customID, prefix) {
		return "", fmt.Errorf("selfroles: malformed custom id %q", customID)
	}
	key := strings.TrimPrefix(customID, prefix)
	if key == "" || strings.Contains(key, ":") {
		return "", fmt.Errorf("selfroles: malformed custom id %q", customID)
	}
	return key, nil
}

func roleFromCustomID(customID, prefix string) (string, int64, error) {
	rest := strings.TrimPrefix(customID, prefix)
	if rest == customID {
		return "", 0, fmt.Errorf("selfroles: malformed custom id %q", customID)
	}
	index := strings.LastIndexByte(rest, ':')
	if index <= 0 || index == len(rest)-1 {
		return "", 0, fmt.Errorf("selfroles: malformed custom id %q", customID)
	}
	roleID, err := parseID(rest[index+1:], "role")
	if err != nil {
		return "", 0, err
	}
	return rest[:index], roleID, nil
}

func parseLegacyCustomID(customID string) (string, string, int64, error) {
	rest := strings.TrimPrefix(customID, LegacyPrefix)
	if rest == customID {
		return "", "", 0, fmt.Errorf("selfroles: malformed custom id %q", customID)
	}
	first := strings.IndexByte(rest, ':')
	last := strings.LastIndexByte(rest, ':')
	if first <= 0 || last <= first || last == len(rest)-1 {
		return "", "", 0, fmt.Errorf("selfroles: malformed custom id %q", customID)
	}
	roleID, err := parseID(rest[last+1:], "role")
	if err != nil {
		return "", "", 0, err
	}
	return rest[:first], rest[first+1 : last], roleID, nil
}

func parseID(raw, kind string) (int64, error) {
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		return 0, fmt.Errorf("selfroles: invalid %s id %q", kind, raw)
	}
	return id, nil
}

func enabledWord(enabled bool) string {
	if enabled {
		return "enabled"
	}
	return "disabled"
}

func indexOf(items []string, value string) int {
	for i, item := range items {
		if item == value {
			return i
		}
	}
	return 0
}
