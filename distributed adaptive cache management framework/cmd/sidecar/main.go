package main

import (
	"adaptivecache/internal/system"
	"context"
	"log"
)

func main() {
	c, e := system.LoadConfig(":8081")
	if e != nil {
		log.Fatal(e)
	}
	redis := system.NewRedis(c.RedisAddr)
	m := system.NewMetrics()
	cache := system.NewCache(c, redis, m)
	p := system.NewPipeline(c, cache, m)
	s := &system.Sidecar{Config: c, Cache: cache, Pipeline: p, Metrics: m}
	if e = system.Serve(c, s.Handler(), func(ctx context.Context) error { err := p.Close(ctx); _ = redis.Close(); return err }); e != nil {
		log.Fatal(e)
	}
}
