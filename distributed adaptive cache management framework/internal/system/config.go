package system

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Mode, Addr, DatabaseURL, RedisAddr, SidecarURL, AIURL, AIFailure                                  string
	Bounds                                                                                            Bounds
	LocalCapacity, PolicyCapacity, BatchSize, QueueCapacity, Workers, HistorySize, BodyLimit, Retries int
	FlushInterval, PolicyLifetime, CacheTimeout, DBTimeout, AITimeout, AILatency, ShutdownTimeout     time.Duration
	Endpoints                                                                                         []string
}

func DefaultConfig() Config {
	return Config{
		Mode: "adaptive", Addr: ":8080", DatabaseURL: "postgres://cache:cache@localhost:5432/cache?sslmode=disable", RedisAddr: "localhost:6379", SidecarURL: "http://localhost:8081", AIURL: "http://localhost:8082", Bounds: Bounds{Min: 1, Max: 3600, Default: 60, MaxFreshness: 3600},
		LocalCapacity: 1000, PolicyCapacity: 10000, BatchSize: 100, QueueCapacity: 64, Workers: 2, HistorySize: 8, BodyLimit: 1048576, Retries: 2,
		FlushInterval: 5 * time.Second, PolicyLifetime: 10 * time.Minute, CacheTimeout: 100 * time.Millisecond, DBTimeout: 2 * time.Second, AITimeout: 2 * time.Second, ShutdownTimeout: 10 * time.Second, Endpoints: []string{ProductEndpoint},
	}
}
func LoadConfig(addr string) (Config, error) {
	c := DefaultConfig()
	c.Addr = addr
	for name, p := range map[string]*string{"MODE": &c.Mode, "ADDR": &c.Addr, "DATABASE_URL": &c.DatabaseURL, "REDIS_ADDR": &c.RedisAddr, "SIDECAR_URL": &c.SidecarURL, "AI_URL": &c.AIURL, "AI_FAILURE": &c.AIFailure} {
		if s, ok := os.LookupEnv(name); ok {
			*p = s
		}
	}
	for name, p := range map[string]*int{"MIN_TTL_SECONDS": &c.Bounds.Min, "MAX_TTL_SECONDS": &c.Bounds.Max, "DEFAULT_TTL_SECONDS": &c.Bounds.Default, "MAX_FRESHNESS_SECONDS": &c.Bounds.MaxFreshness, "LOCAL_CAPACITY": &c.LocalCapacity, "POLICY_CAPACITY": &c.PolicyCapacity, "BATCH_SIZE": &c.BatchSize, "QUEUE_CAPACITY": &c.QueueCapacity, "WORKERS": &c.Workers, "HISTORY_SIZE": &c.HistorySize, "BODY_LIMIT": &c.BodyLimit, "AI_RETRIES": &c.Retries} {
		if s, ok := os.LookupEnv(name); ok {
			n, e := strconv.Atoi(s)
			if e != nil {
				return c, fmt.Errorf("%s: %w", name, e)
			}
			*p = n
		}
	}
	for name, p := range map[string]*time.Duration{"FLUSH_INTERVAL": &c.FlushInterval, "POLICY_LIFETIME": &c.PolicyLifetime, "CACHE_TIMEOUT": &c.CacheTimeout, "DB_TIMEOUT": &c.DBTimeout, "AI_TIMEOUT": &c.AITimeout, "AI_LATENCY": &c.AILatency, "SHUTDOWN_TIMEOUT": &c.ShutdownTimeout} {
		if s, ok := os.LookupEnv(name); ok {
			d, e := time.ParseDuration(s)
			if e != nil {
				return c, fmt.Errorf("%s: %w", name, e)
			}
			*p = d
		}
	}
	if s := os.Getenv("ENDPOINTS"); s != "" {
		c.Endpoints = strings.Split(s, ",")
	}
	return c, c.Validate()
}
func (c Config) Validate() error {
	if c.Mode != "adaptive" && c.Mode != "fixed" && c.Mode != "none" {
		return fmt.Errorf("MODE must be adaptive, fixed or none")
	}
	if c.Bounds.Min < 1 || c.Bounds.Max < c.Bounds.Min || c.Bounds.Default < c.Bounds.Min || c.Bounds.Default > c.Bounds.Max || c.Bounds.MaxFreshness < c.Bounds.Max {
		return fmt.Errorf("require 1 <= min <= default <= max <= max freshness")
	}
	for _, v := range []int{c.LocalCapacity, c.PolicyCapacity, c.BatchSize, c.QueueCapacity, c.Workers, c.HistorySize, c.BodyLimit} {
		if v < 1 {
			return fmt.Errorf("capacities and counts must be positive")
		}
	}
	for _, v := range []time.Duration{c.FlushInterval, c.PolicyLifetime, c.CacheTimeout, c.DBTimeout, c.AITimeout, c.ShutdownTimeout} {
		if v <= 0 {
			return fmt.Errorf("timeouts must be positive")
		}
	}
	if c.Retries < 0 || c.Retries > 10 || c.AILatency < 0 || len(c.Endpoints) > 32 {
		return fmt.Errorf("invalid retries, latency or endpoint count")
	}
	return nil
}
