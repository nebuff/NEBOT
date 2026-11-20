package store

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/nebuff/n-bot/internal/analytics"
)

const analyticsSelectSQL = `SELECT messages, churn, voice FROM server_analytics WHERE guild_id = $1`

const analyticsUpsertSQL = `INSERT INTO server_analytics (guild_id, messages, churn, voice)
VALUES ($1, $2, $3, $4)
ON CONFLICT (guild_id) DO UPDATE SET
    messages = EXCLUDED.messages,
    churn = EXCLUDED.churn,
    voice = EXCLUDED.voice`

const analyticsDeleteSQL = `DELETE FROM server_analytics WHERE guild_id = $1`

// LoadAnalytics returns one guild's analytics row, or an empty record when the
// guild has not been tracked yet.
func (s *Store) LoadAnalytics(ctx context.Context, guildID int64) (analytics.Record, error) {
	if guildID <= 0 {
		return analytics.Record{}, fmt.Errorf("load analytics: invalid guild id %d", guildID)
	}

	rows, err := s.Pool.Query(ctx, analyticsSelectSQL, guildID)
	if err != nil {
		return analytics.Record{}, fmt.Errorf("query analytics for guild %d: %w", guildID, err)
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return analytics.Record{}, fmt.Errorf("read analytics for guild %d: %w", guildID, err)
		}
		return analytics.NewRecord(guildID), nil
	}

	values, err := rows.Values()
	if err != nil {
		return analytics.Record{}, fmt.Errorf("scan analytics for guild %d: %w", guildID, err)
	}
	if len(values) != 3 {
		return analytics.Record{}, fmt.Errorf(
			"analytics for guild %d: got %d values for 3 columns", guildID, len(values),
		)
	}
	if err := rows.Err(); err != nil {
		return analytics.Record{}, fmt.Errorf("read analytics for guild %d: %w", guildID, err)
	}

	record, err := decodeAnalyticsValues(guildID, values)
	if err != nil {
		return analytics.Record{}, fmt.Errorf("decode analytics for guild %d: %w", guildID, err)
	}
	return record, nil
}

// SaveAnalytics upserts one guild row.
func (s *Store) SaveAnalytics(ctx context.Context, record analytics.Record) error {
	if record.GuildID <= 0 {
		return fmt.Errorf("save analytics: invalid guild id %d", record.GuildID)
	}
	record.Normalize(record.GuildID)

	messages, churn, voice, err := encodeAnalytics(record)
	if err != nil {
		return fmt.Errorf("encode analytics for guild %d: %w", record.GuildID, err)
	}
	if _, err := s.Pool.Exec(ctx, analyticsUpsertSQL, record.GuildID, messages, churn, voice); err != nil {
		return fmt.Errorf("save analytics for guild %d: %w", record.GuildID, err)
	}
	return nil
}

// DeleteAnalytics removes one guild's analytics row.
func (s *Store) DeleteAnalytics(ctx context.Context, guildID int64) error {
	if guildID <= 0 {
		return fmt.Errorf("delete analytics: invalid guild id %d", guildID)
	}
	if _, err := s.Pool.Exec(ctx, analyticsDeleteSQL, guildID); err != nil {
		return fmt.Errorf("delete analytics for guild %d: %w", guildID, err)
	}
	return nil
}

func encodeAnalytics(record analytics.Record) (messages, churn, voice string, err error) {
	record.Normalize(record.GuildID)

	encodedMessages, err := json.Marshal(record.Messages)
	if err != nil {
		return "", "", "", err
	}
	encodedChurn, err := json.Marshal(record.Churn)
	if err != nil {
		return "", "", "", err
	}
	encodedVoice, err := json.Marshal(record.Voice)
	if err != nil {
		return "", "", "", err
	}
	return string(encodedMessages), string(encodedChurn), string(encodedVoice), nil
}

func decodeAnalyticsValues(guildID int64, values []any) (analytics.Record, error) {
	record := analytics.NewRecord(guildID)
	if err := decodeJSONText(values[0], &record.Messages); err != nil {
		return analytics.Record{}, fmt.Errorf("messages: %w", err)
	}
	if err := decodeJSONText(values[1], &record.Churn); err != nil {
		return analytics.Record{}, fmt.Errorf("churn: %w", err)
	}
	if err := decodeJSONText(values[2], &record.Voice); err != nil {
		return analytics.Record{}, fmt.Errorf("voice: %w", err)
	}
	record.Normalize(guildID)
	return record, nil
}

func decodeJSONText(value any, target any) error {
	var raw []byte
	switch value := value.(type) {
	case nil:
		return nil
	case string:
		raw = []byte(value)
	case []byte:
		raw = value
	default:
		return fmt.Errorf("unexpected JSON column type %T", value)
	}
	if strings.TrimSpace(string(raw)) == "" || strings.TrimSpace(string(raw)) == "null" {
		return nil
	}
	return json.Unmarshal(raw, target)
}
