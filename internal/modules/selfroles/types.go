package selfroles

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

const (
	ModeNone   = "none"
	ModeSingle = "single"
	ModeMulti  = "multi"

	StyleBlurple = "blurple"
	StyleGrey    = "grey"
	StyleGreen   = "green"
	StyleRed     = "red"

	ColorBlue   = "blue"
	ColorRed    = "red"
	ColorGreen  = "green"
	ColorTeal   = "teal"
	ColorOrange = "orange"
	ColorPurple = "purple"
	ColorGold   = "gold"
	ColorGrey   = "grey"
)

var validModes = map[string]struct{}{
	ModeNone:   {},
	ModeSingle: {},
	ModeMulti:  {},
}

var validStyles = map[string]struct{}{
	StyleBlurple: {},
	StyleGrey:    {},
	StyleGreen:   {},
	StyleRed:     {},
}

var validColors = map[string]struct{}{
	ColorBlue:   {},
	ColorRed:    {},
	ColorGreen:  {},
	ColorTeal:   {},
	ColorOrange: {},
	ColorPurple: {},
	ColorGold:   {},
	ColorGrey:   {},
}

// Role is one button in a self-assignable role group.
type Role struct {
	RoleID       int64   `json:"role_id"`
	Name         string  `json:"name"`
	AllowTakeOff bool    `json:"allow_take_off"`
	RequireRoles []int64 `json:"require_roles"`
	IgnoreRoles  []int64 `json:"ignore_roles"`
	Style        string  `json:"style"`
}

// Group is one self-assignable role menu.
type Group struct {
	Name         string  `json:"name"`
	Mode         string  `json:"mode"`
	AutoTakeAway bool    `json:"auto_take_away"`
	RequireOne   bool    `json:"require_one"`
	MinAmount    int     `json:"min_amount"`
	MaxAmount    int     `json:"max_amount"`
	RequireRoles []int64 `json:"require_roles"`
	IgnoreRoles  []int64 `json:"ignore_roles"`
	Roles        []Role  `json:"roles"`
	DisplayName  string  `json:"display_name,omitempty"`
	Description  string  `json:"description,omitempty"`
	Color        string  `json:"color,omitempty"`
}

// RoleInfo is the subset of a Discord role needed to build menus and messages.
type RoleInfo struct {
	Name   string
	Exists bool
}

// ParseGroups decodes the Python-compatible self_roles_groups JSON. Missing
// booleans receive the Python defaults; malformed JSON is an error so a broken
// configuration is visible instead of silently erased on the next save.
func ParseGroups(raw json.RawMessage) ([]Group, error) {
	if len(strings.TrimSpace(string(raw))) == 0 || strings.TrimSpace(string(raw)) == "null" {
		return []Group{}, nil
	}

	var wire []groupWire
	if err := json.Unmarshal(raw, &wire); err != nil {
		return nil, fmt.Errorf("selfroles: decode groups: %w", err)
	}

	groups := make([]Group, 0, len(wire))
	for _, item := range wire {
		group := Group{
			Name:         strings.TrimSpace(item.Name),
			Mode:         normalizeMode(item.Mode),
			AutoTakeAway: boolDefault(item.AutoTakeAway, true),
			RequireOne:   boolDefault(item.RequireOne, false),
			MinAmount:    intDefault(item.MinAmount, 0),
			MaxAmount:    intDefault(item.MaxAmount, 0),
			RequireRoles: cloneIDs(item.RequireRoles),
			IgnoreRoles:  cloneIDs(item.IgnoreRoles),
			DisplayName:  strings.TrimSpace(item.DisplayName),
			Description:  strings.TrimSpace(item.Description),
			Color:        normalizeColor(item.Color),
		}
		if group.Mode == "" {
			group.Mode = ModeNone
		}
		for _, role := range item.Roles {
			group.Roles = append(group.Roles, Role{
				RoleID:       role.RoleID,
				Name:         strings.TrimSpace(role.Name),
				AllowTakeOff: boolDefault(role.AllowTakeOff, true),
				RequireRoles: cloneIDs(role.RequireRoles),
				IgnoreRoles:  cloneIDs(role.IgnoreRoles),
				Style:        normalizeStyle(role.Style),
			})
		}
		if group.Roles == nil {
			group.Roles = []Role{}
		}
		if group.Name != "" {
			groups = append(groups, group)
		}
	}
	return groups, nil
}

// MarshalGroups encodes groups in the same shape Python writes.
func MarshalGroups(groups []Group) (json.RawMessage, error) {
	if groups == nil {
		groups = []Group{}
	}
	for i := range groups {
		groups[i].Mode = normalizeMode(groups[i].Mode)
		if groups[i].Mode == "" {
			groups[i].Mode = ModeNone
		}
		groups[i].Color = normalizeColor(groups[i].Color)
		if groups[i].RequireRoles == nil {
			groups[i].RequireRoles = []int64{}
		}
		if groups[i].IgnoreRoles == nil {
			groups[i].IgnoreRoles = []int64{}
		}
		if groups[i].Roles == nil {
			groups[i].Roles = []Role{}
		}
		for j := range groups[i].Roles {
			groups[i].Roles[j].Style = normalizeStyle(groups[i].Roles[j].Style)
			if groups[i].Roles[j].RequireRoles == nil {
				groups[i].Roles[j].RequireRoles = []int64{}
			}
			if groups[i].Roles[j].IgnoreRoles == nil {
				groups[i].Roles[j].IgnoreRoles = []int64{}
			}
		}
	}

	encoded, err := json.Marshal(groups)
	if err != nil {
		return nil, fmt.Errorf("selfroles: encode groups: %w", err)
	}
	return json.RawMessage(encoded), nil
}

// NewGroup returns the defaults used when a group is created.
func NewGroup(name, mode string) (Group, error) {
	name = strings.TrimSpace(name)
	mode = normalizeMode(mode)
	if len([]rune(name)) < 2 || len([]rune(name)) > 50 {
		return Group{}, errors.New("Group name must be between 2 and 50 characters.")
	}
	if mode == "" {
		return Group{}, errors.New("Invalid mode! Must be one of: `single`, `multi`, or `none`.")
	}
	return Group{
		Name:         name,
		Mode:         mode,
		AutoTakeAway: true,
		RequireRoles: []int64{},
		IgnoreRoles:  []int64{},
		Roles:        []Role{},
		Color:        ColorBlue,
	}, nil
}

// FindGroup returns the group with the exact name, matching Python's lookup.
func FindGroup(groups []Group, name string) *Group {
	for i := range groups {
		if groups[i].Name == name {
			return &groups[i]
		}
	}
	return nil
}

// FindGroupByKey returns the group whose stable custom-id key matches key.
func FindGroupByKey(groups []Group, key string) *Group {
	for i := range groups {
		if GroupKey(groups[i].Name) == key {
			return &groups[i]
		}
	}
	return nil
}

// FindRole returns the configured role with roleID.
func (g Group) FindRole(roleID int64) *Role {
	for i := range g.Roles {
		if g.Roles[i].RoleID == roleID {
			return &g.Roles[i]
		}
	}
	return nil
}

// GroupKey is a short stable identifier used in custom IDs. Group names are
// capped at 50 characters, so the raw name cannot safely fit alongside a role
// ID inside Discord's 100-character custom_id limit.
func GroupKey(name string) string {
	sum := sha256.Sum256([]byte(name))
	return hex.EncodeToString(sum[:6])
}

// ToggleDecision is the pure result of clicking a self-role button.
type ToggleDecision struct {
	Add         bool
	RoleName    string
	RemoveIDs   []int64
	RemoveNames []string
	Message     string
}

// PlanToggle evaluates requirements and role-group mode rules. It performs no
// Discord calls, which keeps the messy branch logic directly testable.
func PlanToggle(
	enabled bool,
	group Group,
	role Role,
	memberRoleIDs []string,
	roles map[int64]RoleInfo,
	memberInGuild bool,
) (ToggleDecision, bool) {
	if !enabled {
		return ToggleDecision{}, false
	}
	if !memberInGuild {
		return ToggleDecision{}, false
	}

	roleInfo, roleExists := roles[role.RoleID]
	if !roleExists || !roleInfo.Exists {
		return ToggleDecision{}, false
	}

	hasRole := func(roleID int64) bool {
		for _, raw := range memberRoleIDs {
			if raw == fmt.Sprintf("%d", roleID) {
				return true
			}
		}
		return false
	}
	hasAny := func(ids []int64) bool {
		for _, id := range ids {
			if hasRole(id) {
				return true
			}
		}
		return false
	}
	namesFor := func(ids []int64) []string {
		names := make([]string, 0, len(ids))
		for _, id := range ids {
			if info, ok := roles[id]; ok && info.Exists {
				names = append(names, info.Name)
			}
		}
		return names
	}
	roleName := role.Name
	if roleName == "" {
		roleName = roleInfo.Name
	}
	if roleName == "" {
		roleName = fmt.Sprintf("Role %d", role.RoleID)
	}

	if len(group.RequireRoles) > 0 && !hasAny(group.RequireRoles) {
		return ToggleDecision{Message: fmt.Sprintf(
			"You must have at least one of the following roles to use this group: %s",
			strings.Join(namesFor(group.RequireRoles), ", "),
		)}, false
	}
	if len(group.IgnoreRoles) > 0 && hasAny(group.IgnoreRoles) {
		return ToggleDecision{Message: "You have a role that prevents you from using this group."}, false
	}
	if len(role.RequireRoles) > 0 && !hasAny(role.RequireRoles) {
		return ToggleDecision{Message: fmt.Sprintf(
			"You must have at least one of the following roles to assign this role: %s",
			strings.Join(namesFor(role.RequireRoles), ", "),
		)}, false
	}
	if len(role.IgnoreRoles) > 0 && hasAny(role.IgnoreRoles) {
		return ToggleDecision{Message: "You have a role that prevents you from assigning this role."}, false
	}

	memberGroupRoles := make([]int64, 0, len(group.Roles))
	for _, configured := range group.Roles {
		if hasRole(configured.RoleID) {
			memberGroupRoles = append(memberGroupRoles, configured.RoleID)
		}
	}

	if hasRole(role.RoleID) {
		if !role.AllowTakeOff {
			return ToggleDecision{Message: "This role cannot be removed once assigned."}, false
		}
		if group.Mode == ModeSingle && group.RequireOne && len(memberGroupRoles) <= 1 {
			return ToggleDecision{Message: "You must keep at least one role from this group."}, false
		}
		if group.Mode == ModeMulti && group.MinAmount > 0 && len(memberGroupRoles) <= group.MinAmount {
			return ToggleDecision{Message: fmt.Sprintf("You must keep at least %d roles from this group.", group.MinAmount)}, false
		}
		return ToggleDecision{
			RoleName:  roleName,
			RemoveIDs: []int64{role.RoleID},
			Message:   fmt.Sprintf("Removed role: **%s**", roleName),
		}, true
	}

	removeIDs := []int64{}
	if group.Mode == ModeMulti {
		if group.MaxAmount > 0 && len(memberGroupRoles) >= group.MaxAmount {
			for _, configured := range group.Roles {
				if hasRole(configured.RoleID) {
					if info, ok := roles[configured.RoleID]; ok && info.Exists {
						removeIDs = append(removeIDs, configured.RoleID)
						break
					}
				}
			}
		}
	} else if group.Mode == ModeSingle && group.AutoTakeAway {
		for _, configured := range group.Roles {
			if configured.RoleID != role.RoleID && hasRole(configured.RoleID) {
				if info, ok := roles[configured.RoleID]; ok && info.Exists {
					removeIDs = append(removeIDs, configured.RoleID)
				}
			}
		}
	}

	removeNames := make([]string, 0, len(removeIDs))
	for _, id := range removeIDs {
		name := fmt.Sprintf("Role %d", id)
		if info, ok := roles[id]; ok && info.Name != "" {
			name = info.Name
		}
		removeNames = append(removeNames, name)
	}
	message := fmt.Sprintf("Granted role: **%s**", roleName)
	if len(removeNames) > 0 {
		message += fmt.Sprintf(" (and removed %s)", strings.Join(removeNames, ", "))
	}
	return ToggleDecision{
		Add:         true,
		RoleName:    roleName,
		RemoveIDs:   removeIDs,
		RemoveNames: removeNames,
		Message:     message,
	}, true
}

// ProblemMessage returns a user-facing reason for a rejected toggle.
func ProblemMessage(enabled bool, groupFound, roleFound, memberInGuild bool) string {
	switch {
	case !enabled:
		return "Self-assignable roles are currently disabled on this server."
	case !groupFound:
		return "This role group configuration was not found."
	case !roleFound:
		return "This role configuration was not found."
	case !memberInGuild:
		return "This action can only be performed in a server."
	default:
		return "The configured Discord role was not found in this server."
	}
}

type groupWire struct {
	Name         string     `json:"name"`
	Mode         string     `json:"mode"`
	AutoTakeAway *bool      `json:"auto_take_away"`
	RequireOne   *bool      `json:"require_one"`
	MinAmount    *int       `json:"min_amount"`
	MaxAmount    *int       `json:"max_amount"`
	RequireRoles []int64    `json:"require_roles"`
	IgnoreRoles  []int64    `json:"ignore_roles"`
	Roles        []roleWire `json:"roles"`
	DisplayName  string     `json:"display_name"`
	Description  string     `json:"description"`
	Color        string     `json:"color"`
}

type roleWire struct {
	RoleID       int64   `json:"role_id"`
	Name         string  `json:"name"`
	AllowTakeOff *bool   `json:"allow_take_off"`
	RequireRoles []int64 `json:"require_roles"`
	IgnoreRoles  []int64 `json:"ignore_roles"`
	Style        string  `json:"style"`
}

func normalizeMode(mode string) string {
	mode = strings.ToLower(strings.TrimSpace(mode))
	if _, ok := validModes[mode]; !ok {
		return ""
	}
	return mode
}

func normalizeStyle(style string) string {
	style = strings.ToLower(strings.TrimSpace(style))
	if _, ok := validStyles[style]; !ok {
		return StyleBlurple
	}
	return style
}

func normalizeColor(color string) string {
	color = strings.ToLower(strings.TrimSpace(color))
	if _, ok := validColors[color]; !ok {
		return ColorBlue
	}
	return color
}

func boolDefault(value *bool, fallback bool) bool {
	if value == nil {
		return fallback
	}
	return *value
}

func intDefault(value *int, fallback int) int {
	if value == nil {
		return fallback
	}
	return *value
}

func cloneIDs(ids []int64) []int64 {
	if ids == nil {
		return []int64{}
	}
	return append([]int64(nil), ids...)
}
