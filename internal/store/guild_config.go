package store

import (
	"context"
	"fmt"
	"strings"

	"github.com/nebuff/n-bot/internal/guild"
)

var guildConfigSelectSQL = "SELECT " + strings.Join(guild.Columns(), ", ") +
	" FROM guild_configs WHERE guild_id = $1"

var guildConfigUpsertSQL = buildGuildConfigUpsertSQL()

func buildGuildConfigUpsertSQL() string {
	columns := guild.Columns()
	placeholders := make([]string, len(columns))
	updates := make([]string, 0, len(columns)-1)

	for i, column := range columns {
		placeholders[i] = fmt.Sprintf("$%d", i+1)
		if column == "guild_id" {
			continue
		}
		updates = append(updates, column+" = EXCLUDED."+column)
	}

	return fmt.Sprintf(
		"INSERT INTO guild_configs (%s) VALUES (%s) ON CONFLICT (guild_id) DO UPDATE SET %s",
		strings.Join(columns, ", "),
		strings.Join(placeholders, ", "),
		strings.Join(updates, ", "),
	)
}

// LoadGuildConfig returns one guild's row, or Python-compatible defaults when
// no row exists yet.
func (s *Store) LoadGuildConfig(ctx context.Context, guildID int64) (guild.Config, error) {
	rows, err := s.Pool.Query(ctx, guildConfigSelectSQL, guildID)
	if err != nil {
		return guild.Config{}, fmt.Errorf("query guild config %d: %w", guildID, err)
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return guild.Config{}, fmt.Errorf("read guild config %d: %w", guildID, err)
		}
		return guild.Default(guildID), nil
	}

	values, err := rows.Values()
	if err != nil {
		return guild.Config{}, fmt.Errorf("scan guild config %d: %w", guildID, err)
	}
	columns := guild.Columns()
	if len(values) != len(columns) {
		return guild.Config{}, fmt.Errorf(
			"guild config %d: got %d values for %d columns",
			guildID, len(values), len(columns),
		)
	}

	row := make(map[string]any, len(values))
	for i, field := range rows.FieldDescriptions() {
		row[string(field.Name)] = values[i]
	}
	if err := rows.Err(); err != nil {
		return guild.Config{}, fmt.Errorf("read guild config %d: %w", guildID, err)
	}

	return guild.FromRow(guildID, row), nil
}

// SaveGuildConfig upserts one full guild row. Targeted per-field updates will
// replace this for dashboard writes later; a single row write is already much
// cheaper than the Python bot rewriting every guild on each change.
func (s *Store) SaveGuildConfig(ctx context.Context, cfg guild.Config) error {
	if cfg.GuildID <= 0 {
		return fmt.Errorf("save guild config: invalid guild id %d", cfg.GuildID)
	}
	if _, err := s.Pool.Exec(ctx, guildConfigUpsertSQL, cfg.Values()...); err != nil {
		return fmt.Errorf("save guild config %d: %w", cfg.GuildID, err)
	}
	return nil
}
