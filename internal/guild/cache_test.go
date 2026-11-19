package guild

import (
	"context"
	"errors"
	"sync"
	"testing"
)

type fakeRepository struct {
	mu      sync.Mutex
	configs map[int64]Config
	loads   int
	saves   int
	err     error
}

func newFakeRepository() *fakeRepository {
	return &fakeRepository{configs: make(map[int64]Config)}
}

func (f *fakeRepository) LoadGuildConfig(_ context.Context, guildID int64) (Config, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.loads++
	if f.err != nil {
		return Config{}, f.err
	}
	if cfg, ok := f.configs[guildID]; ok {
		return cfg, nil
	}
	return Default(guildID), nil
}

func (f *fakeRepository) SaveGuildConfig(_ context.Context, cfg Config) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.saves++
	if f.err != nil {
		return f.err
	}
	f.configs[cfg.GuildID] = cfg
	return nil
}

func (f *fakeRepository) counts() (loads, saves int) {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.loads, f.saves
}

func TestCacheLoadsOnce(t *testing.T) {
	repo := newFakeRepository()
	cache := NewCache(repo)
	ctx := context.Background()

	first, err := cache.Get(ctx, 10)
	if err != nil {
		t.Fatalf("first Get: %v", err)
	}
	second, err := cache.Get(ctx, 10)
	if err != nil {
		t.Fatalf("second Get: %v", err)
	}
	if first.Prefix != "!" || second.Prefix != "!" {
		t.Errorf("unexpected configs: %#v %#v", first, second)
	}
	if loads, _ := repo.counts(); loads != 1 {
		t.Errorf("repository loads = %d, want 1", loads)
	}
	if cache.Len() != 1 {
		t.Errorf("cache length = %d, want 1", cache.Len())
	}
}

func TestCacheReturnsCopies(t *testing.T) {
	cache := NewCache(newFakeRepository())
	ctx := context.Background()

	first, err := cache.Get(ctx, 11)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	first.WarningPlatforms[0] = "changed"
	first.WarningSeverityPoints["Low"] = 999

	second, err := cache.Get(ctx, 11)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if second.WarningPlatforms[0] != "Discord" {
		t.Errorf("cached platforms mutated: %#v", second.WarningPlatforms)
	}
	if second.WarningSeverityPoints["Low"] != 1 {
		t.Errorf("cached severity mutated: %#v", second.WarningSeverityPoints)
	}
}

func TestCacheSaveAndInvalidate(t *testing.T) {
	repo := newFakeRepository()
	cache := NewCache(repo)
	ctx := context.Background()

	cfg := Default(12)
	cfg.Prefix = "?"
	if err := cache.Save(ctx, cfg); err != nil {
		t.Fatalf("Save: %v", err)
	}
	if _, saves := repo.counts(); saves != 1 {
		t.Errorf("saves = %d, want 1", saves)
	}

	got, err := cache.Get(ctx, 12)
	if err != nil {
		t.Fatalf("Get after Save: %v", err)
	}
	if got.Prefix != "?" {
		t.Errorf("prefix = %q, want ?", got.Prefix)
	}
	if loads, _ := repo.counts(); loads != 0 {
		t.Errorf("loads after Save = %d, want 0", loads)
	}

	cache.Invalidate(12)
	if cache.Len() != 0 {
		t.Errorf("cache length after Invalidate = %d, want 0", cache.Len())
	}
	if _, err := cache.Get(ctx, 12); err != nil {
		t.Fatalf("Get after Invalidate: %v", err)
	}
	if loads, _ := repo.counts(); loads != 1 {
		t.Errorf("loads after Invalidate = %d, want 1", loads)
	}
}

func TestCacheRepositoryError(t *testing.T) {
	repo := newFakeRepository()
	repo.err = errors.New("database down")
	cache := NewCache(repo)

	if _, err := cache.Get(context.Background(), 13); err == nil {
		t.Fatal("expected a repository error")
	}
	if err := cache.Save(context.Background(), Default(13)); err == nil {
		t.Fatal("expected a save error")
	}
}

func TestCacheInvalidGuildID(t *testing.T) {
	cache := NewCache(newFakeRepository())
	if _, err := cache.Get(context.Background(), 0); err == nil {
		t.Fatal("expected an invalid guild ID error")
	}
}

func TestCacheConcurrentGet(t *testing.T) {
	cache := NewCache(newFakeRepository())
	ctx := context.Background()

	var wg sync.WaitGroup
	errs := make(chan error, 50)
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cfg, err := cache.Get(ctx, 14)
			if err != nil {
				errs <- err
				return
			}
			if cfg.Prefix != "!" {
				errs <- errors.New("unexpected prefix")
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Errorf("concurrent Get: %v", err)
	}
}
