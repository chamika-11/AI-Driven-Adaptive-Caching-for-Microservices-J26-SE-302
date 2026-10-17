package system

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/redis/go-redis/v9"
	"time"
)

var ErrMissing = errors.New("cache missing")

type SharedCache interface {
	Get(context.Context, string) (Entry, string, error)
	Put(context.Context, string, Entry) error
	CompareExpiry(context.Context, string, string, time.Time) error
	Delete(context.Context, string) error
	Ping(context.Context) error
	Close() error
}
type Redis struct{ client *redis.Client }

func NewRedis(addr string) *Redis {
	return &Redis{redis.NewClient(&redis.Options{Addr: addr, MaxRetries: -1, DialTimeout: time.Second, ReadTimeout: time.Second, WriteTimeout: time.Second, ContextTimeoutEnabled: true})}
}
func (r *Redis) Get(ctx context.Context, key string) (Entry, string, error) {
	raw, e := r.client.Get(ctx, "entry:"+key).Result()
	if errors.Is(e, redis.Nil) {
		return Entry{}, "", ErrMissing
	}
	var v Entry
	if e == nil {
		e = json.Unmarshal([]byte(raw), &v)
	}
	return v, raw, e
}

// Compare whole serialized entry atomically. A concurrent fill cannot be overwritten.
const expiryLua = `if redis.call('GET',KEYS[1]) ~= ARGV[1] then return 0 end
local now=redis.call('TIME'); local ms=now[1]*1000+math.floor(now[2]/1000)
if tonumber(ARGV[3]) <= ms then redis.call('DEL',KEYS[1]); return 1 end
redis.call('SET',KEYS[1],ARGV[2],'PXAT',ARGV[3]); return 1`
const putLua = `local old=redis.call('GET',KEYS[1])
if old then local a=cjson.decode(old); local b=cjson.decode(ARGV[1]); if a.sourceVersion > b.sourceVersion then return 0 end end
local now=redis.call('TIME'); local ms=now[1]*1000+math.floor(now[2]/1000)
if tonumber(ARGV[2]) <= ms then return 0 end
redis.call('SET',KEYS[1],ARGV[1],'PXAT',ARGV[2]); return 1`

func (r *Redis) Put(ctx context.Context, key string, v Entry) error {
	b, e := json.Marshal(v)
	if e != nil {
		return e
	}
	n, e := r.client.Eval(ctx, putLua, []string{"entry:" + key}, string(b), v.ExpiresAt.UnixMilli()).Int()
	if e == nil && n == 0 {
		return errors.New("stale fill rejected")
	}
	return e
}
func (r *Redis) CompareExpiry(ctx context.Context, key, raw string, expiry time.Time) error {
	var v Entry
	if e := json.Unmarshal([]byte(raw), &v); e != nil {
		return e
	}
	v.ExpiresAt = expiry
	b, _ := json.Marshal(v)
	_, e := r.client.Eval(ctx, expiryLua, []string{"entry:" + key}, raw, string(b), expiry.UnixMilli()).Result()
	return e
}
func (r *Redis) Delete(ctx context.Context, key string) error {
	return r.client.Del(ctx, "entry:"+key).Err()
}
func (r *Redis) Ping(ctx context.Context) error { return r.client.Ping(ctx).Err() }
func (r *Redis) Close() error                   { return r.client.Close() }
