package store

import (
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/nebuff/n-bot/internal/analytics"
)

func TestAnalyticsJSONRoundTrip(t *testing.T) {
	now := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	record := analytics.NewRecord(42)
	record.AddMessage("100", now)
	record.AddMessage("100", now)
	record.AddChurn(analytics.ChurnJoin, 7, now)
	record.AddVoice(3, now)

	messages, churn, voice, err := encodeAnalytics(record)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := decodeAnalyticsValues(42, []any{messages, churn, voice})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(record, decoded) {
		t.Fatalf("decoded = %#v, want %#v", decoded, record)
	}
}

func TestAnalyticsSQLShape(t *testing.T) {
	if !strings.Contains(analyticsUpsertSQL, "ON CONFLICT (guild_id) DO UPDATE") {
		t.Errorf("upsert SQL = %q", analyticsUpsertSQL)
	}
	if !strings.Contains(analyticsSelectSQL, "FROM server_analytics") {
		t.Errorf("select SQL = %q", analyticsSelectSQL)
	}
	if !strings.Contains(analyticsDeleteSQL, "DELETE FROM server_analytics") {
		t.Errorf("delete SQL = %q", analyticsDeleteSQL)
	}
}
