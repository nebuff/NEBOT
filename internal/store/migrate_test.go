package store

import (
	"strings"
	"testing"
)

func TestSplitStatements(t *testing.T) {
	script := `
-- a comment
CREATE TABLE a (id INT);

CREATE INDEX i ON a(id);
-- trailing comment
`
	got := splitStatements(script)
	want := []string{"CREATE TABLE a (id INT)", "CREATE INDEX i ON a(id)"}

	if len(got) != len(want) {
		t.Fatalf("got %d statements, want %d: %#v", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("statement %d = %q, want %q", i, got[i], want[i])
		}
	}
}

func TestPlatformMigration(t *testing.T) {
	body, err := migrationFS.ReadFile("migrations/0001_platform.sql")
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}

	statements := splitStatements(string(body))
	if len(statements) < 18 {
		t.Fatalf("only %d statements parsed; migration looks truncated", len(statements))
	}

	joined := strings.Join(statements, "\n")
	requiredTables := []string{
		"users",
		"members",
		"proxy_tags",
		"guild_configs",
		"global_configs",
		"battle_stats",
		"warnings",
		"warning_linked_accounts",
		"join_filtering_logs",
		"proxied_messages",
		"sessions",
		"vc_wr_records",
		"vc_wr_sessions",
		"server_analytics",
	}
	for _, table := range requiredTables {
		if !strings.Contains(joined, "CREATE TABLE IF NOT EXISTS "+table) {
			t.Errorf("migration does not create table %q", table)
		}
	}

	requiredColumns := []string{
		"self_roles_groups",
		"automod_filters",
		"warning_ladder",
		"join_filters",
		"verification_verified_role_ids",
	}
	for _, column := range requiredColumns {
		if !strings.Contains(joined, column) {
			t.Errorf("migration does not contain column %q", column)
		}
	}

	for _, statement := range statements {
		if !strings.HasPrefix(strings.ToUpper(statement), "CREATE ") {
			t.Errorf("unexpected non-DDL statement: %.80s", statement)
		}
	}
}
