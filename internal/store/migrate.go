package store

import (
	"context"
	"embed"
	"fmt"
	"sort"
	"strings"
)

//go:embed migrations/*.sql
var migrationFS embed.FS

// Migrate applies every embedded migration exactly once.
//
// Migrations must be additive/idempotent: the Python bot may still be running
// against the same database during the transition. The statements in the SQL
// files are split on semicolons; do not put semicolons inside string literals
// or dollar-quoted blocks.
func (s *Store) Migrate(ctx context.Context) error {
	if _, err := s.Pool.Exec(ctx, `CREATE TABLE IF NOT EXISTS schema_migrations (
		version TEXT PRIMARY KEY,
		applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
	)`); err != nil {
		return fmt.Errorf("create schema_migrations: %w", err)
	}

	entries, err := migrationFS.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("read migrations: %w", err)
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })

	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}
		version := strings.TrimSuffix(entry.Name(), ".sql")

		var applied bool
		if err := s.Pool.QueryRow(ctx,
			`SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)`,
			version,
		).Scan(&applied); err != nil {
			return fmt.Errorf("check migration %s: %w", version, err)
		}
		if applied {
			continue
		}

		body, err := migrationFS.ReadFile("migrations/" + entry.Name())
		if err != nil {
			return fmt.Errorf("read migration %s: %w", version, err)
		}
		if err := s.applyMigration(ctx, version, string(body)); err != nil {
			return err
		}
	}

	return nil
}

func (s *Store) applyMigration(ctx context.Context, version, script string) error {
	tx, err := s.Pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin migration %s: %w", version, err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	for _, statement := range splitStatements(script) {
		if _, err := tx.Exec(ctx, statement); err != nil {
			return fmt.Errorf("migration %s: %w", version, err)
		}
	}

	if _, err := tx.Exec(ctx,
		`INSERT INTO schema_migrations (version) VALUES ($1)`,
		version,
	); err != nil {
		return fmt.Errorf("record migration %s: %w", version, err)
	}
	return tx.Commit(ctx)
}

// splitStatements strips whole-line SQL comments and splits a migration into
// individual statements. The migration files are intentionally simple enough
// for this to be safe (no semicolons inside literals).
func splitStatements(script string) []string {
	var cleaned strings.Builder
	for _, line := range strings.Split(script, "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "--") {
			continue
		}
		cleaned.WriteString(line)
		cleaned.WriteByte('\n')
	}

	parts := strings.Split(cleaned.String(), ";")
	statements := make([]string, 0, len(parts))
	for _, part := range parts {
		if statement := strings.TrimSpace(part); statement != "" {
			statements = append(statements, statement)
		}
	}
	return statements
}
