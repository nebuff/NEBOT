// Package store owns the PostgreSQL connection pool and schema migrations.
package store

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Store is the shared PostgreSQL handle. It is safe for concurrent use.
type Store struct {
	Pool *pgxpool.Pool
}

// Open creates a pool and verifies connectivity before returning.
func Open(ctx context.Context, databaseURL string) (*Store, error) {
	if databaseURL == "" {
		return nil, fmt.Errorf("database URL is empty")
	}

	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse database URL: %w", err)
	}
	cfg.MaxConns = 10
	cfg.MinConns = 1
	cfg.MaxConnLifetime = time.Hour
	cfg.MaxConnIdleTime = 30 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("create PostgreSQL pool: %w", err)
	}

	pingCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping PostgreSQL: %w", err)
	}

	return &Store{Pool: pool}, nil
}

// Close releases the pool.
func (s *Store) Close() {
	if s != nil && s.Pool != nil {
		s.Pool.Close()
	}
}

// Ping checks that the database is still reachable.
func (s *Store) Ping(ctx context.Context) error {
	return s.Pool.Ping(ctx)
}
