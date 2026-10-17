package system

import (
	"context"
	"fmt"
	"math"
	"net/http"
	"strings"
	"time"
)

type Sidecar struct {
	Config   Config
	Cache    *Cache
	Pipeline *Pipeline
	Metrics  *Metrics
}

func (s *Sidecar) valid(key, endpoint string) bool {
	if len(key) == 0 || len(key) > 256 || strings.ContainsAny(key, "\r\n\x00") {
		return false
	}
	for _, ep := range s.Config.Endpoints {
		if endpoint == ep {
			return true
		}
	}
	return false
}
func (s *Sidecar) Handler() http.Handler {
	mux := http.NewServeMux()
	CommonRoutes(mux, s.Metrics, s.Cache.shared.Ping)
	mux.HandleFunc("POST /cache/lookup", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		var q LookupRequest
		if e := decode(w, r, s.Config.BodyLimit, &q); e != nil || !s.valid(q.CacheKey, q.Endpoint) {
			JSON(w, 400, map[string]string{"error": "invalid lookup"})
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), s.Config.CacheTimeout)
		defer cancel()
		res, err := s.Cache.Lookup(ctx, q.CacheKey)
		s.Pipeline.Record(AccessEvent{q.CacheKey, q.Endpoint, res.Tier, time.Now(), res.Hit, time.Since(start)})
		if err != nil {
			s.Metrics.Inc("lookup_error")
			JSON(w, 503, map[string]string{"error": "cache unavailable"})
			return
		}
		JSON(w, 200, res)
	})
	mux.HandleFunc("POST /cache/insert", func(w http.ResponseWriter, r *http.Request) {
		var f FillRequest
		if e := decode(w, r, s.Config.BodyLimit, &f); e != nil || !s.valid(f.CacheKey, f.Endpoint) || len(f.Value) == 0 || f.SourceVersion < 0 || f.FetchedAt.IsZero() || f.FetchedAt.After(time.Now().Add(time.Second)) || f.DBFetchSeconds < 0 || math.IsNaN(f.DBFetchSeconds) || math.IsInf(f.DBFetchSeconds, 0) {
			JSON(w, 400, map[string]string{"error": "invalid insertion"})
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), s.Config.CacheTimeout)
		defer cancel()
		err := s.Cache.Fill(ctx, f)
		outcome := "ok"
		if err != nil {
			outcome = "error"
		}
		s.Pipeline.Fill(f, outcome)
		if err != nil {
			JSON(w, 503, map[string]string{"error": fmt.Sprint(err)})
			return
		}
		JSON(w, 200, map[string]bool{"cached": true})
	})
	mux.HandleFunc("POST /cache/invalidate", func(w http.ResponseWriter, r *http.Request) {
		var q LookupRequest
		if e := decode(w, r, s.Config.BodyLimit, &q); e != nil || !s.valid(q.CacheKey, q.Endpoint) {
			JSON(w, 400, map[string]string{"error": "invalid invalidation"})
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), s.Config.CacheTimeout)
		defer cancel()
		if err := s.Cache.Invalidate(ctx, q.CacheKey); err != nil {
			JSON(w, 503, map[string]string{"error": "invalidation failed"})
			return
		}
		JSON(w, 200, map[string]bool{"invalidated": true})
	})
	return mux
}
