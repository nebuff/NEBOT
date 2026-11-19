// Package auth mirrors the Python bot's is_admin / is_mod permission checks.
package auth

import (
	"strconv"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
)

// IsAdmin reports whether the actor is the bot owner, has Administrator, or
// holds the guild's configured admin role.
//
// member is used for guild interactions/messages; user is the DM fallback.
// session may be nil when the caller cannot provide guild state, in which case
// only member.Permissions and the configured role are checked.
func IsAdmin(session *dg.Session, guildID string, member *dg.Member, user *dg.User, cfg guild.Config, ownerID int64) bool {
	actor := actorID(member, user)
	if actor != "" && ownerID > 0 && actor == strconv.FormatInt(ownerID, 10) {
		return true
	}
	if member == nil {
		return false
	}
	if isAdministrator(session, guildID, member, actor) {
		return true
	}
	return cfg.AdminRoleID != nil && hasRole(member, *cfg.AdminRoleID)
}

// IsMod reports whether the actor is an admin or holds the configured mod role.
func IsMod(session *dg.Session, guildID string, member *dg.Member, user *dg.User, cfg guild.Config, ownerID int64) bool {
	if IsAdmin(session, guildID, member, user, cfg, ownerID) {
		return true
	}
	if member == nil {
		return false
	}
	return cfg.ModRoleID != nil && hasRole(member, *cfg.ModRoleID)
}

func isAdministrator(session *dg.Session, guildID string, member *dg.Member, actor string) bool {
	if member.Permissions&dg.PermissionAdministrator != 0 {
		return true
	}
	if session == nil || session.State == nil || guildID == "" {
		return false
	}

	guildState, err := session.State.Guild(guildID)
	if err != nil || guildState == nil {
		return false
	}
	if actor != "" && guildState.OwnerID == actor {
		return true
	}

	for _, roleID := range member.Roles {
		for _, role := range guildState.Roles {
			if role.ID == roleID && role.Permissions&dg.PermissionAdministrator != 0 {
				return true
			}
		}
	}
	return false
}

func actorID(member *dg.Member, user *dg.User) string {
	if member != nil && member.User != nil {
		return member.User.ID
	}
	if user != nil {
		return user.ID
	}
	return ""
}

func hasRole(member *dg.Member, roleID int64) bool {
	if member == nil || roleID <= 0 {
		return false
	}
	wanted := strconv.FormatInt(roleID, 10)
	for _, id := range member.Roles {
		if id == wanted {
			return true
		}
	}
	return false
}
