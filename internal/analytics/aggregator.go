package analytics

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"
)

// Repository is the persistence contract used by Aggregator. *store.Store
// implements it without the analytics package depending on the store package.
type Repository interface {
	LoadAnalytics(ctx context.Context, guildID int64) (Record, error)
	SaveAnalytics(ctx context.Context, record Record) error
	DeleteAnalytics(ctx context.Context, guildID int64) error
}

const defaultFlushInterval = 5 * time.Second

type guildState struct {
	record Record
	dirty  bool
}

// Aggregator keeps analytics in memory and flushes dirty guild rows in
// batches. One guild's row is written at a time instead of the Python bot
// rewriting every guild row on every event.
type Aggregator struct {
	repo     Repository
	log      *slog.Logger
	now      func() time.Time
	interval time.Duration

	mu      sync.Mutex
	guilds  map[int64]*guildState
	started bool

	flushMu   sync.Mutex
	startOnce sync.Once
	closeOnce sync.Once
	closeErr  error
	stop      chan struct{}
	done      chan struct{}
}

// NewAggregator creates an empty aggregator. Call Start to begin periodic
// flushing and Close to stop and flush on shutdown.
func NewAggregator(repo Repository, log *slog.Logger) *Aggregator {
	if repo == nil {
		panic("analytics: nil repository")
	}
	if log == nil {
		log = slog.Default()
	}
	return &Aggregator{
		repo:     repo,
		log:      log,
		now:      time.Now,
		interval: defaultFlushInterval,
		guilds:   make(map[int64]*guildState),
		stop:     make(chan struct{}),
		done:     make(chan struct{}),
	}
}

// Start begins the periodic flush loop.
func (a *Aggregator) Start(ctx context.Context) {
	a.startOnce.Do(func() {
		a.mu.Lock()
		a.started = true
		a.mu.Unlock()
		go a.loop(ctx)
	})
}

// Close stops the flush loop and performs a final flush.
func (a *Aggregator) Close(ctx context.Context) error {
	a.closeOnce.Do(func() {
		a.mu.Lock()
		started := a.started
		a.mu.Unlock()
		if started {
			close(a.stop)
			<-a.done
		}
		a.closeErr = a.Flush(ctx)
	})
	return a.closeErr
}

// RecordMessage increments a channel's current UTC hour bucket.
func (a *Aggregator) RecordMessage(ctx context.Context, guildID int64, channelID string, at time.Time) error {
	if channelID == "" {
		return errors.New("analytics: empty channel id")
	}
	state, err := a.state(ctx, guildID)
	if err != nil {
		return err
	}
	if at.IsZero() {
		at = a.now()
	}

	a.mu.Lock()
	state.record.AddMessage(channelID, at)
	state.dirty = true
	a.mu.Unlock()
	return nil
}

// RecordJoin records a member join.
func (a *Aggregator) RecordJoin(ctx context.Context, guildID, userID int64, at time.Time) error {
	return a.recordChurn(ctx, guildID, ChurnJoin, userID, at)
}

// RecordLeave records a member leave.
func (a *Aggregator) RecordLeave(ctx context.Context, guildID, userID int64, at time.Time) error {
	return a.recordChurn(ctx, guildID, ChurnLeave, userID, at)
}

// RecordVoice records a non-bot voice concurrency sample.
func (a *Aggregator) RecordVoice(ctx context.Context, guildID, count int64, at time.Time) error {
	state, err := a.state(ctx, guildID)
	if err != nil {
		return err
	}
	if at.IsZero() {
		at = a.now()
	}

	a.mu.Lock()
	state.record.AddVoice(count, at)
	state.dirty = true
	a.mu.Unlock()
	return nil
}

// Snapshot returns a pruned copy of the current in-memory record.
func (a *Aggregator) Snapshot(ctx context.Context, guildID int64) (Record, error) {
	state, err := a.state(ctx, guildID)
	if err != nil {
		return Record{}, err
	}

	a.mu.Lock()
	record := state.record.Clone()
	a.mu.Unlock()
	record.Prune(a.now().Add(-RetentionWindow))
	return record, nil
}

// Clear deletes one guild's persisted and cached analytics.
func (a *Aggregator) Clear(ctx context.Context, guildID int64) error {
	if guildID <= 0 {
		return fmt.Errorf("analytics: invalid guild id %d", guildID)
	}

	a.flushMu.Lock()
	defer a.flushMu.Unlock()
	if err := a.repo.DeleteAnalytics(ctx, guildID); err != nil {
		return fmt.Errorf("delete analytics for guild %d: %w", guildID, err)
	}

	a.mu.Lock()
	delete(a.guilds, guildID)
	a.mu.Unlock()
	return nil
}

// Flush writes every dirty guild row. Failed rows stay dirty for a retry.
func (a *Aggregator) Flush(ctx context.Context) error {
	if ctx == nil {
		ctx = context.Background()
	}

	a.flushMu.Lock()
	defer a.flushMu.Unlock()

	cutoff := a.now().Add(-RetentionWindow)
	pending := make([]Record, 0)
	a.mu.Lock()
	for guildID, state := range a.guilds {
		if !state.dirty {
			continue
		}
		state.dirty = false
		state.record.Prune(cutoff)
		record := state.record.Clone()
		record.GuildID = guildID
		pending = append(pending, record)
	}
	a.mu.Unlock()

	var errs []error
	for _, record := range pending {
		if err := a.repo.SaveAnalytics(ctx, record); err != nil {
			errs = append(errs, fmt.Errorf("save analytics for guild %d: %w", record.GuildID, err))
			a.mu.Lock()
			if state, ok := a.guilds[record.GuildID]; ok {
				state.dirty = true
			}
			a.mu.Unlock()
		}
	}
	return errors.Join(errs...)
}

func (a *Aggregator) recordChurn(ctx context.Context, guildID int64, event string, userID int64, at time.Time) error {
	state, err := a.state(ctx, guildID)
	if err != nil {
		return err
	}
	if at.IsZero() {
		at = a.now()
	}

	a.mu.Lock()
	state.record.AddChurn(event, userID, at)
	state.dirty = true
	a.mu.Unlock()
	return nil
}

func (a *Aggregator) state(ctx context.Context, guildID int64) (*guildState, error) {
	if guildID <= 0 {
		return nil, fmt.Errorf("analytics: invalid guild id %d", guildID)
	}
	if ctx == nil {
		ctx = context.Background()
	}

	a.mu.Lock()
	if state, ok := a.guilds[guildID]; ok {
		a.mu.Unlock()
		return state, nil
	}
	a.mu.Unlock()

	record, err := a.repo.LoadAnalytics(ctx, guildID)
	if err != nil {
		return nil, fmt.Errorf("load analytics for guild %d: %w", guildID, err)
	}
	record.Normalize(guildID)

	a.mu.Lock()
	defer a.mu.Unlock()
	if state, ok := a.guilds[guildID]; ok {
		return state, nil
	}
	state := &guildState{record: record}
	a.guilds[guildID] = state
	return state, nil
}

func (a *Aggregator) loop(ctx context.Context) {
	defer close(a.done)
	ticker := time.NewTicker(a.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			flushCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			if err := a.Flush(flushCtx); err != nil {
				a.log.Error("flushing analytics", "err", err)
			}
			cancel()
		case <-a.stop:
			return
		case <-ctx.Done():
			return
		}
	}
}
