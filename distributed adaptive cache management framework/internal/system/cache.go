package system

import (
	"context"
	"errors"
	"sync"
	"time"
)

type Cache struct {
	mu       sync.Mutex
	config   Config
	shared   SharedCache
	local    *lru[Entry]
	policies *lru[Policy]
	metrics  *Metrics
}

func NewCache(c Config, s SharedCache, m *Metrics) *Cache {
	return &Cache{config: c, shared: s, local: newLRU[Entry](c.LocalCapacity), policies: newLRU[Policy](c.PolicyCapacity), metrics: m}
}
func (c *Cache) policyLocked(key string, now time.Time) Policy {
	if p, ok := c.policies.get(key); ok {
		if now.Before(p.ExpiresAt) {
			return p
		}
		c.policies.remove(key)
	}
	return Policy{TTLSeconds: c.config.Bounds.Default}
}
func (c *Cache) Policies(keys map[string]KeyAggregate) map[string]Policy {
	c.mu.Lock()
	defer c.mu.Unlock()
	out := map[string]Policy{}
	for k := range keys {
		out[k] = c.policyLocked(k, time.Now())
	}
	return out
}
func (c *Cache) expiry(fetched time.Time, ttl int) time.Time {
	return fetched.Add(time.Duration(min(ttl, c.config.Bounds.MaxFreshness)) * time.Second)
}
func (c *Cache) putLocal(key string, e Entry) {
	if c.local.put(key, e) {
		c.metrics.Inc("local_eviction")
	}
	c.metrics.Gauge("local_entries", float64(len(c.local.items)))
}
func (c *Cache) Lookup(ctx context.Context, key string) (LookupResponse, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	now := time.Now()
	if e, ok := c.local.get(key); ok {
		if now.Before(e.ExpiresAt) {
			return LookupResponse{true, "local", &e}, nil
		}
		c.local.remove(key)
	}
	e, _, err := c.shared.Get(ctx, key)
	if errors.Is(err, ErrMissing) {
		return LookupResponse{Tier: "miss"}, nil
	}
	if err != nil {
		return LookupResponse{Tier: "miss"}, err
	}
	now = time.Now()
	if !now.Before(e.ExpiresAt) || !now.Before(c.expiry(e.FetchedAt, c.config.Bounds.MaxFreshness)) {
		return LookupResponse{Tier: "miss"}, nil
	}
	c.putLocal(key, e)
	return LookupResponse{true, "redis", &e}, nil
}
func (c *Cache) Fill(ctx context.Context, f FillRequest) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	p := c.policyLocked(f.CacheKey, time.Now())
	e := Entry{f.Value, f.SourceVersion, f.FetchedAt, c.expiry(f.FetchedAt, p.TTLSeconds)}
	if !time.Now().Before(e.ExpiresAt) {
		return errors.New("fill already expired")
	}
	if old, ok := c.local.get(f.CacheKey); ok && old.SourceVersion > e.SourceVersion {
		return errors.New("older source version")
	}
	if err := c.shared.Put(ctx, f.CacheKey, e); err != nil {
		return err
	}
	c.putLocal(f.CacheKey, e)
	return nil
}
func (c *Cache) Apply(ctx context.Context, d Decision) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	now := time.Now()
	if d.TTLSeconds < c.config.Bounds.Min || d.TTLSeconds > c.config.Bounds.Max {
		return errors.New("TTL outside bounds")
	}
	// Read/CAS never creates a missing entry and never replaces concurrent data.
	e, raw, err := c.shared.Get(ctx, d.CacheKey)
	if err != nil && !errors.Is(err, ErrMissing) {
		return err
	}
	if err == nil {
		if err = c.shared.CompareExpiry(ctx, d.CacheKey, raw, c.expiry(e.FetchedAt, d.TTLSeconds)); err != nil {
			return err
		}
	}
	c.policies.put(d.CacheKey, Policy{d.TTLSeconds, now, now.Add(c.config.PolicyLifetime)})
	if e, ok := c.local.get(d.CacheKey); ok {
		e.ExpiresAt = c.expiry(e.FetchedAt, d.TTLSeconds)
		if !now.Before(e.ExpiresAt) {
			c.local.remove(d.CacheKey)
		} else {
			c.putLocal(d.CacheKey, e)
		}
	}
	c.metrics.Inc("policy_update")
	c.metrics.Gauge("policy_last_update_timestamp", float64(now.Unix()))
	return nil
}
func (c *Cache) Invalidate(ctx context.Context, key string) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.local.remove(key)
	return c.shared.Delete(ctx, key)
}
func (c *Cache) Maintain() {
	c.mu.Lock()
	defer c.mu.Unlock()
	now := time.Now()
	for k, e := range c.local.items {
		if !now.Before(e.Value.(item[Entry]).value.ExpiresAt) {
			c.local.remove(k)
			c.metrics.Inc("local_expiration")
		}
	}
	for k, e := range c.policies.items {
		if !now.Before(e.Value.(item[Policy]).value.ExpiresAt) {
			c.policies.remove(k)
		}
	}
	c.metrics.Gauge("local_entries", float64(len(c.local.items)))
	c.metrics.Gauge("policy_entries", float64(len(c.policies.items)))
	var oldest float64
	for _, e := range c.policies.items {
		oldest = max(oldest, now.Sub(e.Value.(item[Policy]).value.UpdatedAt).Seconds())
	}
	c.metrics.Gauge("oldest_policy_age_seconds", oldest)
}
func (c *Cache) Size() int { c.mu.Lock(); defer c.mu.Unlock(); return len(c.local.items) }
