package store

import (
	"strings"
	"testing"

	"github.com/nebuff/n-bot/internal/guild"
)

func TestGuildConfigSQLShape(t *testing.T) {
	columns := guild.Columns()
	if len(columns) != 65 {
		t.Fatalf("got %d guild config columns, want 65", len(columns))
	}

	if !strings.HasPrefix(guildConfigSelectSQL, "SELECT guild_id, prefix, cmd") {
		t.Errorf("unexpected select SQL prefix: %.80s", guildConfigSelectSQL)
	}
	if !strings.Contains(guildConfigSelectSQL, "FROM guild_configs WHERE guild_id = $1") {
		t.Errorf("select SQL is missing the guild filter: %s", guildConfigSelectSQL)
	}

	if !strings.Contains(guildConfigUpsertSQL, "$65") {
		t.Errorf("upsert SQL does not have a placeholder for all 65 columns")
	}
	if got, want := strings.Count(guildConfigUpsertSQL, "EXCLUDED."), 64; got != want {
		t.Errorf("upsert SQL has %d EXCLUDED references, want %d", got, want)
	}
	if strings.Contains(guildConfigUpsertSQL, "guild_id = EXCLUDED.guild_id") {
		t.Error("upsert SQL should not update guild_id")
	}
	if !strings.Contains(guildConfigUpsertSQL, "ON CONFLICT (guild_id) DO UPDATE SET") {
		t.Error("upsert SQL is missing the conflict clause")
	}
}
