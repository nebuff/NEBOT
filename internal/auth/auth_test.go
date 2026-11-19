package auth

import (
	"testing"

	dg "github.com/bwmarrin/discordgo"

	"github.com/nebuff/n-bot/internal/guild"
)

func roleID(value int64) *int64 { return &value }

func testConfig() guild.Config {
	cfg := guild.Default(100)
	cfg.AdminRoleID = roleID(200)
	cfg.ModRoleID = roleID(300)
	return cfg
}

func TestOwnerIsAdminAndMod(t *testing.T) {
	cfg := testConfig()
	user := &dg.User{ID: "999"}

	if !IsAdmin(nil, "", nil, user, cfg, 999) {
		t.Error("owner should be admin")
	}
	if !IsMod(nil, "", nil, user, cfg, 999) {
		t.Error("owner should be mod")
	}
}

func TestDMNonOwnerIsNotStaff(t *testing.T) {
	cfg := testConfig()
	if IsAdmin(nil, "", nil, &dg.User{ID: "1"}, cfg, 999) {
		t.Error("non-owner DM user should not be admin")
	}
	if IsMod(nil, "", nil, &dg.User{ID: "1"}, cfg, 999) {
		t.Error("non-owner DM user should not be mod")
	}
}

func TestAdministratorPermission(t *testing.T) {
	cfg := testConfig()
	member := &dg.Member{
		User:        &dg.User{ID: "1"},
		Permissions: dg.PermissionAdministrator,
	}
	if !IsAdmin(nil, "", member, nil, cfg, 0) {
		t.Error("member with Administrator should be admin")
	}
	if !IsMod(nil, "", member, nil, cfg, 0) {
		t.Error("admin should also be mod")
	}
}

func TestConfiguredAdminAndModRoles(t *testing.T) {
	cfg := testConfig()
	admin := &dg.Member{User: &dg.User{ID: "2"}, Roles: []string{"200"}}
	mod := &dg.Member{User: &dg.User{ID: "3"}, Roles: []string{"300"}}

	if !IsAdmin(nil, "", admin, nil, cfg, 0) {
		t.Error("configured admin role should grant admin")
	}
	if IsAdmin(nil, "", mod, nil, cfg, 0) {
		t.Error("configured mod role should not grant admin")
	}
	if !IsMod(nil, "", mod, nil, cfg, 0) {
		t.Error("configured mod role should grant mod")
	}
}

func TestMemberWithoutRolesHasNoAccess(t *testing.T) {
	cfg := testConfig()
	member := &dg.Member{User: &dg.User{ID: "4"}}
	if IsAdmin(nil, "", member, nil, cfg, 0) {
		t.Error("plain member should not be admin")
	}
	if IsMod(nil, "", member, nil, cfg, 0) {
		t.Error("plain member should not be mod")
	}
}

func TestGuildStateAdministratorRole(t *testing.T) {
	session, err := dg.New("Bot test-token")
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	guildState := &dg.Guild{
		ID:      "100",
		OwnerID: "900",
		Roles: []*dg.Role{
			{ID: "400", Permissions: dg.PermissionAdministrator},
		},
	}
	if err := session.State.GuildAdd(guildState); err != nil {
		t.Fatalf("add guild state: %v", err)
	}

	member := &dg.Member{
		GuildID: "100",
		User:    &dg.User{ID: "5"},
		Roles:   []string{"400"},
	}
	if !IsAdmin(session, "100", member, nil, testConfig(), 0) {
		t.Error("role with Administrator in guild state should grant admin")
	}

	owner := &dg.Member{GuildID: "100", User: &dg.User{ID: "900"}}
	if !IsAdmin(session, "100", owner, nil, testConfig(), 0) {
		t.Error("guild owner should grant admin")
	}
}
