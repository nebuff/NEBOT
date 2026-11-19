// Command nebot is the Go implementation of NEBOT.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/nebuff/n-bot/internal/bot"
	"github.com/nebuff/n-bot/internal/config"
	"github.com/nebuff/n-bot/internal/modules/core"
	"github.com/nebuff/n-bot/internal/modules/fun"
	"github.com/nebuff/n-bot/internal/store"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "nebot: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("load config: %w", err)
	}

	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level:     cfg.LogLevel,
		AddSource: cfg.LogLevel == slog.LevelDebug,
	}))
	slog.SetDefault(logger)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	st, err := store.Open(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer st.Close()

	if err := st.Migrate(ctx); err != nil {
		return fmt.Errorf("apply database migrations: %w", err)
	}

	b, err := bot.New(cfg, logger, st)
	if err != nil {
		return err
	}
	if err := b.Register(core.New(logger)); err != nil {
		return err
	}
	if err := b.Register(fun.NewNebuff(b.Guilds(), logger)); err != nil {
		return err
	}
	if err := b.Register(fun.NewGrok(logger)); err != nil {
		return err
	}

	return b.Run(ctx)
}
