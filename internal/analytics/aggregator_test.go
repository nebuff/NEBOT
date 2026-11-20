package analytics

import (
	"context"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"
)

type fakeRepository struct {
	mu      sync.Mutex
	records map[int64]Record
	saves   int
	deletes int
}

func newFakeRepository() *fakeRepository {
	return &fakeRepository{records: make(map[int64]Record)}
}

func (f *fakeRepository) LoadAnalytics(_ context.Context, guildID int64) (Record, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if record, ok := f.records[guildID]; ok {
		return record.Clone(), nil
	}
	return NewRecord(guildID), nil
}

func (f *fakeRepository) SaveAnalytics(_ context.Context, record Record) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.saves++
	f.records[record.GuildID] = record.Clone()
	return nil
}

func (f *fakeRepository) DeleteAnalytics(_ context.Context, guildID int64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.deletes++
	delete(f.records, guildID)
	return nil
}

func testLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func TestAggregatorRecordsAndBatches(t *testing.T) {
	repo := newFakeRepository()
	agg := NewAggregator(repo, testLogger())
	now := time.Date(2026, 11, 19, 12, 34, 0, 0, time.UTC)
	agg.now = func() time.Time { return now }
	ctx := context.Background()

	if err := agg.RecordMessage(ctx, 1, "100", now); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordMessage(ctx, 1, "100", now); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordJoin(ctx, 1, 10, now); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordLeave(ctx, 1, 11, now); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordVoice(ctx, 1, 3, now); err != nil {
		t.Fatal(err)
	}

	snapshot, err := agg.Snapshot(ctx, 1)
	if err != nil {
		t.Fatal(err)
	}
	if got := snapshot.Messages["100"][HourKey(now)]; got != 2 {
		t.Errorf("message count = %d, want 2", got)
	}
	if len(snapshot.Churn) != 2 {
		t.Errorf("churn events = %d, want 2", len(snapshot.Churn))
	}
	if len(snapshot.Voice) != 1 || snapshot.Voice[0].Count != 3 {
		t.Errorf("voice points = %+v", snapshot.Voice)
	}

	if err := agg.Flush(ctx); err != nil {
		t.Fatal(err)
	}
	if repo.saves != 1 {
		t.Errorf("saves = %d, want 1", repo.saves)
	}
	if err := agg.Flush(ctx); err != nil {
		t.Fatal(err)
	}
	if repo.saves != 1 {
		t.Errorf("second flush saves = %d, want 1", repo.saves)
	}
}

func TestAggregatorPrunesOldRecords(t *testing.T) {
	repo := newFakeRepository()
	agg := NewAggregator(repo, testLogger())
	now := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	old := now.Add(-31 * 24 * time.Hour)
	agg.now = func() time.Time { return now }
	ctx := context.Background()

	if err := agg.RecordMessage(ctx, 1, "100", old); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordMessage(ctx, 1, "100", now); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordJoin(ctx, 1, 10, old); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordJoin(ctx, 1, 11, now); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordVoice(ctx, 1, 1, old); err != nil {
		t.Fatal(err)
	}
	if err := agg.RecordVoice(ctx, 1, 2, now); err != nil {
		t.Fatal(err)
	}

	snapshot, err := agg.Snapshot(ctx, 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := snapshot.Messages["100"][HourKey(old)]; ok {
		t.Error("old message bucket was not pruned")
	}
	if len(snapshot.Churn) != 1 || snapshot.Churn[0].UserID != 11 {
		t.Errorf("churn after prune = %+v", snapshot.Churn)
	}
	if len(snapshot.Voice) != 1 || snapshot.Voice[0].Count != 2 {
		t.Errorf("voice after prune = %+v", snapshot.Voice)
	}
}

func TestAggregatorClear(t *testing.T) {
	repo := newFakeRepository()
	agg := NewAggregator(repo, testLogger())
	now := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	agg.now = func() time.Time { return now }
	ctx := context.Background()

	if err := agg.RecordMessage(ctx, 1, "100", now); err != nil {
		t.Fatal(err)
	}
	if err := agg.Flush(ctx); err != nil {
		t.Fatal(err)
	}
	if err := agg.Clear(ctx, 1); err != nil {
		t.Fatal(err)
	}
	if repo.deletes != 1 {
		t.Errorf("deletes = %d, want 1", repo.deletes)
	}
	snapshot, err := agg.Snapshot(ctx, 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Messages) != 0 {
		t.Errorf("messages after clear = %+v", snapshot.Messages)
	}
}

func TestAggregatorConcurrentRecording(t *testing.T) {
	repo := newFakeRepository()
	agg := NewAggregator(repo, testLogger())
	now := time.Date(2026, 11, 19, 12, 0, 0, 0, time.UTC)
	agg.now = func() time.Time { return now }

	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := agg.RecordMessage(context.Background(), 1, "100", now); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()

	snapshot, err := agg.Snapshot(context.Background(), 1)
	if err != nil {
		t.Fatal(err)
	}
	if got := snapshot.Messages["100"][HourKey(now)]; got != 100 {
		t.Errorf("message count = %d, want 100", got)
	}
}
