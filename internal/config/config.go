// Package config loads process-wide configuration from the environment.
//
// Guild-level configuration lives in PostgreSQL; this package only holds
// process settings (token, database credentials, Lavalink node).
package config

import (
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/url"
	"os"
	"strconv"
	"strings"
)

const (
	defaultDatabasePort = "5432"
	defaultDatabaseName = "nebot"
	defaultBotStatus    = "NEBOT (Go port)"
	defaultLavalinkPort = 2333
)

// Config is the process-wide configuration.
type Config struct {
	DiscordToken string
	OwnerID      int64
	DevGuildID   string

	DatabaseURL string
	BotStatus   string

	LavalinkHost     string
	LavalinkPort     int
	LavalinkPassword string

	LogLevel slog.Level
}

// Load reads configuration from the environment and validates it.
//
// DATABASE_URL takes precedence. When it is empty, the same DATABASE_* variable
// names used by the Python bot are assembled into a PostgreSQL URL.
func Load() (Config, error) {
	token := strings.TrimSpace(os.Getenv("DISCORD_TOKEN"))
	if token == "" {
		return Config{}, errors.New("DISCORD_TOKEN is required")
	}

	ownerID, err := optionalPositiveInt64("OWNER_ID")
	if err != nil {
		return Config{}, err
	}

	devGuildID, err := optionalSnowflake("DISCORD_DEV_GUILD_ID")
	if err != nil {
		return Config{}, err
	}

	databaseURL := strings.TrimSpace(os.Getenv("DATABASE_URL"))
	if databaseURL == "" {
		databaseURL, err = databaseURLFromParts()
		if err != nil {
			return Config{}, err
		}
	}

	lavalinkPort, err := optionalPort("LAVALINK_PORT", defaultLavalinkPort)
	if err != nil {
		return Config{}, err
	}

	logLevel, err := parseLogLevel(envOr("LOG_LEVEL", "info"))
	if err != nil {
		return Config{}, err
	}

	status := strings.TrimSpace(envOr("BOT_STATUS", defaultBotStatus))
	if status == "" {
		status = defaultBotStatus
	}

	return Config{
		DiscordToken:     token,
		OwnerID:          ownerID,
		DevGuildID:       devGuildID,
		DatabaseURL:      databaseURL,
		BotStatus:        status,
		LavalinkHost:     envOr("LAVALINK_HOST", "127.0.0.1"),
		LavalinkPort:     lavalinkPort,
		LavalinkPassword: os.Getenv("LAVALINK_PASSWORD"),
		LogLevel:         logLevel,
	}, nil
}

func databaseURLFromParts() (string, error) {
	host := envOr("DATABASE_HOST", "127.0.0.1")
	port := envOr("DATABASE_PORT", defaultDatabasePort)
	if p, err := strconv.Atoi(port); err != nil || p < 1 || p > 65535 {
		return "", fmt.Errorf("DATABASE_PORT must be a valid TCP port, got %q", port)
	}

	user := envOr("DATABASE_USER", "postgres")
	password := os.Getenv("DATABASE_PASSWORD")
	name := envOr("DATABASE_NAME", defaultDatabaseName)

	u := &url.URL{
		Scheme:   "postgres",
		Host:     net.JoinHostPort(host, port),
		Path:     "/" + name,
		RawQuery: "sslmode=disable",
	}
	if password == "" {
		u.User = url.User(user)
	} else {
		u.User = url.UserPassword(user, password)
	}
	return u.String(), nil
}

func envOr(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func optionalPositiveInt64(name string) (int64, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return 0, nil
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer, got %q", name, raw)
	}
	return value, nil
}

func optionalSnowflake(name string) (string, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return "", nil
	}
	if _, err := strconv.ParseUint(raw, 10, 64); err != nil {
		return "", fmt.Errorf("%s must be a Discord snowflake, got %q", name, raw)
	}
	return raw, nil
}

func optionalPort(name string, fallback int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	port, err := strconv.Atoi(raw)
	if err != nil || port < 1 || port > 65535 {
		return 0, fmt.Errorf("%s must be a valid TCP port, got %q", name, raw)
	}
	return port, nil
}

func parseLogLevel(raw string) (slog.Level, error) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "debug":
		return slog.LevelDebug, nil
	case "", "info":
		return slog.LevelInfo, nil
	case "warn", "warning":
		return slog.LevelWarn, nil
	case "error":
		return slog.LevelError, nil
	default:
		return 0, fmt.Errorf("LOG_LEVEL must be debug, info, warn, or error, got %q", raw)
	}
}
