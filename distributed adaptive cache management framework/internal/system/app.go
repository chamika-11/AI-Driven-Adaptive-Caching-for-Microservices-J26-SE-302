package system

import (
	"context"
	"encoding/json"
	"errors"
	"golang.org/x/sync/singleflight"
	"net/http"
	"strconv"
	"time"
)

type App struct {
	Config  Config
	DB      Database
	Metrics *Metrics
	Client  *http.Client
	group   singleflight.Group
	base    context.Context
	cancel  context.CancelFunc
}

func NewApp(c Config, db Database, metrics *Metrics) *App {
	ctx, cancel := context.WithCancel(context.Background())
	return &App{Config: c, DB: db, Metrics: metrics, Client: &http.Client{}, base: ctx, cancel: cancel}
}
func (a *App) Close() {
	if a.cancel != nil {
		a.cancel()
	}
	a.DB.Close()
}

type appValue struct {
	value json.RawMessage
	tier  string
}

func (a *App) Handler() http.Handler {
	mux := http.NewServeMux()
	CommonRoutes(mux, a.Metrics, a.DB.Ping)
	mux.HandleFunc("GET /products/{id}", a.product)
	return mux
}
func (a *App) lookup(ctx context.Context, key string) (LookupResponse, error) {
	ctx, cancel := context.WithTimeout(ctx, a.Config.CacheTimeout)
	defer cancel()
	var res LookupResponse
	e := post(ctx, a.Client, a.Config.SidecarURL+"/cache/lookup", LookupRequest{key, ProductEndpoint}, &res)
	return res, e
}
func (a *App) product(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	outcome := "ok"
	defer func() { a.Metrics.Requests.WithLabelValues(outcome).Observe(time.Since(start).Seconds()) }()
	id, e := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if e != nil || id < 1 {
		outcome = "error"
		JSON(w, 400, map[string]string{"error": "positive integer product ID required"})
		return
	}
	key := "product:" + strconv.FormatInt(id, 10)
	if a.Config.Mode != "none" {
		cached, err := a.lookup(r.Context(), key)
		if err == nil && cached.Hit && cached.Entry != nil {
			w.Header().Set("X-Cache-Tier", cached.Tier)
			JSON(w, 200, cached.Value)
			return
		}
		if err != nil {
			a.Metrics.Inc("sidecar_lookup_error")
		}
	}
	// Work stays inside the HTTP handler so server draining also drains DB work.
	// The shared operation has its own bounded deadline; cancellation of the first
	// caller cannot fail other callers waiting for the same product.
	result, err, _ := a.group.Do(key, func() (any, error) {
		base := a.base
		if base == nil {
			base = context.Background()
		}
		ctx, cancel := context.WithTimeout(base, a.Config.DBTimeout+a.Config.CacheTimeout)
		defer cancel()
		dbctx, dbCancel := context.WithTimeout(ctx, a.Config.DBTimeout)
		defer dbCancel()
		fetched := time.Now()
		p, err := a.DB.Product(dbctx, id)
		elapsed := time.Since(fetched)
		dbOutcome := "ok"
		if err != nil {
			dbOutcome = "error"
		}
		a.Metrics.DB.WithLabelValues(dbOutcome).Observe(elapsed.Seconds())
		a.Metrics.Inc("database_read")
		if err != nil {
			return nil, err
		}
		value, _ := json.Marshal(p)
		if a.Config.Mode != "none" {
			fillctx, fillCancel := context.WithTimeout(ctx, a.Config.CacheTimeout)
			var ack struct {
				Cached bool `json:"cached"`
			}
			err = post(fillctx, a.Client, a.Config.SidecarURL+"/cache/insert", FillRequest{key, ProductEndpoint, value, p.Version, fetched, elapsed.Seconds()}, &ack)
			fillCancel()
			if err != nil || !ack.Cached {
				a.Metrics.Inc("insertion_error")
			}
		}
		return appValue{value, "database"}, nil
	})
	if r.Context().Err() != nil {
		outcome = "error"
		return
	}
	if err != nil {
		outcome = "error"
		status := 503
		if errors.Is(err, ErrNotFound) {
			status = 404
		}
		JSON(w, status, map[string]string{"error": err.Error()})
		return
	}
	v := result.(appValue)
	w.Header().Set("X-Cache-Tier", v.tier)
	JSON(w, 200, v.value)
}
