package guild

import (
	"context"
	"fmt"
	"sync"
)

// Repository is the persistence contract used by Cache. *store.Store
// implements it without the guild package depending on the store package.
type Repository interface {
	LoadGuildConfig(ctx context.Context, guildID int64) (Config, error)
	SaveGuildConfig(ctx context.Context, cfg Config) error
}

// Cache keeps one typed config per guild. Reads return deep copies so modules
// cannot accidentally mutate cached state.
type Cache struct {
	repo Repository

	mu      sync.RWMutex
	configs map[int64]Config
}

// NewCache creates an empty cache backed by repo.
func NewCache(repo Repository) *Cache {
	if repo == nil {
		panic("guild: nil repository")
	}
	return &Cache{repo: repo, configs: make(map[int64]Config)}
}

// Get returns the guild config, loading it from the repository on first use.
func (c *Cache) Get(ctx context.Context, guildID int64) (Config, error) {
	if guildID <= 0 {
		return Config{}, fmt.Errorf("guild: invalid guild id %d", guildID)
	}

	c.mu.RLock()
	cached, ok := c.configs[guildID]
	c.mu.RUnlock()
	if ok {
		return cached.Clone(), nil
	}

	loaded, err := c.repo.LoadGuildConfig(ctx, guildID)
	if err != nil {
		return Config{}, fmt.Errorf("load guild %d config: %w", guildID, err)
	}
	loaded.GuildID = guildID
	loaded = loaded.Clone()

	// Another goroutine may have loaded the same guild while we were waiting.
	c.mu.Lock()
	if existing, ok := c.configs[guildID]; ok {
		loaded = existing
	} else {
		c.configs[guildID] = loaded
	}
	c.mu.Unlock()

	return loaded.Clone(), nil
}

// Save persists the full guild row and updates the cache.
func (c *Cache) Save(ctx context.Context, cfg Config) error {
	if cfg.GuildID <= 0 {
		return fmt.Errorf("guild: cannot save invalid guild id %d", cfg.GuildID)
	}
	if err := c.repo.SaveGuildConfig(ctx, cfg); err != nil {
		return fmt.Errorf("save guild %d config: %w", cfg.GuildID, err)
	}
	c.Set(cfg)
	return nil
}

// Set stores a config in the cache without touching the database.
func (c *Cache) Set(cfg Config) {
	if cfg.GuildID <= 0 {
		return
	}
	c.mu.Lock()
	c.configs[cfg.GuildID] = cfg.Clone()
	c.mu.Unlock()
}

// Invalidate drops one guild from the cache.
func (c *Cache) Invalidate(guildID int64) {
	c.mu.Lock()
	delete(c.configs, guildID)
	c.mu.Unlock()
}

// Clear drops every cached guild.
func (c *Cache) Clear() {
	c.mu.Lock()
	c.configs = make(map[int64]Config)
	c.mu.Unlock()
}

// Len returns the number of cached guilds.
func (c *Cache) Len() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.configs)
}
