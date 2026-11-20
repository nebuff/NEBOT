// Command nebot is the Go implementation of NEBOT.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	analyticsdata "github.com/nebuff/n-bot/internal/analytics"
	"github.com/nebuff/n-bot/internal/bot"
	"github.com/nebuff/n-bot/internal/config"
	"github.com/nebuff/n-bot/internal/modules/admin"
	analyticsmodule "github.com/nebuff/n-bot/internal/modules/analytics"
	"github.com/nebuff/n-bot/internal/modules/autoroller"
	"github.com/nebuff/n-bot/internal/modules/core"
	"github.com/nebuff/n-bot/internal/modules/fun"
	selfrolesmodule "github.com/nebuff/n-bot/internal/modules/selfroles"
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

	analyticsAggregator := analyticsdata.NewAggregator(st, logger)
	analyticsAggregator.Start(ctx)
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := analyticsAggregator.Close(closeCtx); err != nil {
			logger.Error("closing analytics aggregator", "err", err)
		}
	}()

	b, err := bot.New(cfg, logger, st)
	if err != nil {
		return err
	}
	if err := b.Register(core.New(logger)); err != nil {
		return err
	}
	if err := b.Register(analyticsmodule.New(b.Guilds(), analyticsAggregator, cfg.OwnerID, logger)); err != nil {
		return err
	}
	if err := b.Register(fun.NewNebuff(b.Guilds(), logger)); err != nil {
		return err
	}
	if err := b.Register(fun.NewGrok(logger)); err != nil {
		return err
	}
	if err := b.Register(admin.New(b.Guilds(), cfg.OwnerID, logger)); err != nil {
		return err
	}
	if err := b.Register(autoroller.New(b.Guilds(), cfg.OwnerID, logger)); err != nil {
		return err
	}
	if err := b.Register(selfrolesmodule.New(b.Guilds(), cfg.OwnerID, logger)); err != nil {
		return err
	}

	return b.Run(ctx)
}
