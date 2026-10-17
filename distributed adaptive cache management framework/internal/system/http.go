package system

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func JSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}
func decode(w http.ResponseWriter, r *http.Request, limit int, v any) error {
	r.Body = http.MaxBytesReader(w, r.Body, int64(limit))
	d := json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	if e := d.Decode(v); e != nil {
		return e
	}
	if e := d.Decode(&struct{}{}); e != io.EOF {
		return errors.New("expected one JSON object")
	}
	return nil
}
func post(ctx context.Context, client *http.Client, url string, input, output any) error {
	b, e := json.Marshal(input)
	if e != nil {
		return e
	}
	req, e := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(b))
	if e != nil {
		return e
	}
	req.Header.Set("Content-Type", "application/json")
	res, e := client.Do(req)
	if e != nil {
		return e
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return errors.New("upstream HTTP " + res.Status)
	}
	d := json.NewDecoder(io.LimitReader(res.Body, 8<<20))
	d.DisallowUnknownFields()
	if e = d.Decode(output); e != nil {
		return e
	}
	if e = d.Decode(&struct{}{}); e != io.EOF {
		return errors.New("trailing upstream JSON")
	}
	return nil
}
func CommonRoutes(mux *http.ServeMux, m *Metrics, ready func(context.Context) error) {
	mux.Handle("GET /metrics", promhttp.HandlerFor(m.Registry, promhttp.HandlerOpts{}))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { JSON(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("GET /readyz", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), time.Second)
		defer cancel()
		if e := ready(ctx); e != nil {
			JSON(w, 503, map[string]string{"status": "not_ready"})
			return
		}
		JSON(w, 200, map[string]string{"status": "ready"})
	})
}

// HTTP drains before component shutdown, so no producer can send after queue closure.
func Serve(c Config, h http.Handler, closeFn func(context.Context) error) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	srv := &http.Server{Addr: c.Addr, Handler: h, ReadHeaderTimeout: 2 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 15 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16 << 10}
	done := make(chan error, 1)
	go func() { done <- srv.ListenAndServe() }()
	slog.Info("listening", "addr", c.Addr, "mode", c.Mode)
	var runErr error
	select {
	case <-ctx.Done():
	case runErr = <-done:
	}
	shutdown, cancel := context.WithTimeout(context.Background(), c.ShutdownTimeout)
	defer cancel()
	if e := srv.Shutdown(shutdown); e != nil {
		_ = srv.Close()
		slog.Warn("HTTP drain deadline", "error", e)
	}
	if closeFn != nil {
		if e := closeFn(shutdown); e != nil {
			slog.Warn("shutdown", "error", e)
		}
	}
	if errors.Is(runErr, http.ErrServerClosed) {
		return nil
	}
	return runErr
}
