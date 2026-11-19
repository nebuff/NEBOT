package config

import (
	"log/slog"
	"net/url"
	"testing"
)

func clearEnv(t *testing.T) {
	t.Helper()
	for _, key := range []string{
		"DISCORD_TOKEN",
		"OWNER_ID",
		"DISCORD_DEV_GUILD_ID",
		"DATABASE_URL",
		"DATABASE_HOST",
		"DATABASE_PORT",
		"DATABASE_USER",
		"DATABASE_PASSWORD",
		"DATABASE_NAME",
		"LAVALINK_HOST",
		"LAVALINK_PORT",
		"LAVALINK_PASSWORD",
		"BOT_STATUS",
		"LOG_LEVEL",
	} {
		t.Setenv(key, "")
	}
}

func TestLoadRequiresToken(t *testing.T) {
	clearEnv(t)
	if _, err := Load(); err == nil {
		t.Fatal("expected an error when DISCORD_TOKEN is empty")
	}
}

func TestLoadDefaults(t *testing.T) {
	clearEnv(t)
	t.Setenv("DISCORD_TOKEN", "test-token")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	parsed, err := url.Parse(cfg.DatabaseURL)
	if err != nil {
		t.Fatalf("parse DatabaseURL: %v", err)
	}
	if parsed.Scheme != "postgres" {
		t.Errorf("scheme = %q, want postgres", parsed.Scheme)
	}
	if parsed.Host != "127.0.0.1:5432" {
		t.Errorf("host = %q, want 127.0.0.1:5432", parsed.Host)
	}
	if parsed.Path != "/nebot" {
		t.Errorf("path = %q, want /nebot", parsed.Path)
	}
	if parsed.User == nil || parsed.User.Username() != "postgres" {
		t.Errorf("user = %v, want postgres", parsed.User)
	}
	if parsed.Query().Get("sslmode") != "disable" {
		t.Errorf("sslmode = %q, want disable", parsed.Query().Get("sslmode"))
	}
	if cfg.BotStatus != defaultBotStatus {
		t.Errorf("BotStatus = %q, want %q", cfg.BotStatus, defaultBotStatus)
	}
	if cfg.LavalinkPort != defaultLavalinkPort {
		t.Errorf("LavalinkPort = %d, want %d", cfg.LavalinkPort, defaultLavalinkPort)
	}
	if cfg.LogLevel != slog.LevelInfo {
		t.Errorf("LogLevel = %v, want info", cfg.LogLevel)
	}
}

func TestLoadDatabaseURLFromParts(t *testing.T) {
	clearEnv(t)
	t.Setenv("DISCORD_TOKEN", "test-token")
	t.Setenv("DATABASE_HOST", "db.internal")
	t.Setenv("DATABASE_PORT", "6543")
	t.Setenv("DATABASE_USER", "nebot")
	t.Setenv("DATABASE_PASSWORD", "p@ss word")
	t.Setenv("DATABASE_NAME", "production")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	parsed, err := url.Parse(cfg.DatabaseURL)
	if err != nil {
		t.Fatalf("parse DatabaseURL: %v", err)
	}
	if parsed.Host != "db.internal:6543" {
		t.Errorf("host = %q, want db.internal:6543", parsed.Host)
	}
	if parsed.Path != "/production" {
		t.Errorf("path = %q, want /production", parsed.Path)
	}
	password, ok := parsed.User.Password()
	if !ok || password != "p@ss word" {
		t.Errorf("password = %q, %v; want p@ss word, true", password, ok)
	}
}

func TestLoadUsesExplicitDatabaseURL(t *testing.T) {
	clearEnv(t)
	t.Setenv("DISCORD_TOKEN", "test-token")
	t.Setenv("DATABASE_URL", "postgres://user:pass@example.com:5432/custom?sslmode=require")
	t.Setenv("DATABASE_HOST", "ignored")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.DatabaseURL != "postgres://user:pass@example.com:5432/custom?sslmode=require" {
		t.Errorf("DatabaseURL = %q, want the explicit value", cfg.DatabaseURL)
	}
}

func TestLoadRejectsInvalidValues(t *testing.T) {
	tests := []struct {
		name  string
		key   string
		value string
	}{
		{name: "owner", key: "OWNER_ID", value: "not-a-number"},
		{name: "dev guild", key: "DISCORD_DEV_GUILD_ID", value: "abc"},
		{name: "database port", key: "DATABASE_PORT", value: "70000"},
		{name: "lavalink port", key: "LAVALINK_PORT", value: "0"},
		{name: "log level", key: "LOG_LEVEL", value: "verbose"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			clearEnv(t)
			t.Setenv("DISCORD_TOKEN", "test-token")
			t.Setenv(tt.key, tt.value)
			if _, err := Load(); err == nil {
				t.Fatalf("expected an error for %s=%q", tt.key, tt.value)
			}
		})
	}
}

func TestLoadOptionalValues(t *testing.T) {
	clearEnv(t)
	t.Setenv("DISCORD_TOKEN", "test-token")
	t.Setenv("OWNER_ID", "123456789012345678")
	t.Setenv("DISCORD_DEV_GUILD_ID", "987654321098765432")
	t.Setenv("LOG_LEVEL", "debug")
	t.Setenv("BOT_STATUS", "building things")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.OwnerID != 123456789012345678 {
		t.Errorf("OwnerID = %d", cfg.OwnerID)
	}
	if cfg.DevGuildID != "987654321098765432" {
		t.Errorf("DevGuildID = %q", cfg.DevGuildID)
	}
	if cfg.LogLevel != slog.LevelDebug {
		t.Errorf("LogLevel = %v, want debug", cfg.LogLevel)
	}
	if cfg.BotStatus != "building things" {
		t.Errorf("BotStatus = %q", cfg.BotStatus)
	}
}
