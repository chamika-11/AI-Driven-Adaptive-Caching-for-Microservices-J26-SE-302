package main

import (
	"adaptivecache/internal/bench"
	"adaptivecache/internal/system"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"
)

func main() {
	url := flag.String("url", "http://localhost:8080", "application URL")
	sidecar := flag.String("sidecar", "http://localhost:8081", "sidecar URL")
	scenario := flag.String("scenario", "hot", "hot, changing, burst, uniform, unique, updates")
	rate := flag.Int("rate", 100, "base requests/s; burst uses 3x during middle third")
	duration := flag.Duration("duration", 10*time.Second, "offered load duration")
	keys := flag.Int("keys", 1000, "seeded key count; unique must cover all requests")
	seed := flag.Int64("seed", 42, "PRNG seed")
	workers := flag.Int("workers", 32, "bounded HTTP workers")
	out := flag.String("out", "results/result.json", "result file")
	samplesPath := flag.String("samples", "results/samples.jsonl", "samples file")
	validate := flag.Bool("validate", false, "post-run separate database validation")
	payload := flag.Int("payload", 1024, "expected seeded payload size (recorded metadata)")
	updateRate := flag.Int("update-rate", 10, "updates/s for updates scenario")
	flag.Parse()
	if *rate < 1 || *rate > 100000 || *duration <= 0 || *keys < 1 || *workers < 1 || *updateRate < 1 {
		log.Fatal("invalid load settings")
	}
	switch *scenario {
	case "hot", "changing", "burst", "uniform", "unique", "updates":
	default:
		log.Fatal("invalid scenario")
	}
	ctx := context.Background()
	metricsBefore := map[string]any{}
	for name, u := range map[string]string{"app": *url, "sidecar": *sidecar} {
		m, e := bench.Metrics(ctx, u)
		if e != nil {
			metricsBefore[name] = e.Error()
		} else {
			metricsBefore[name] = m
		}
	}
	var db *system.Postgres
	var err error
	if *validate || *scenario == "updates" {
		c, e := system.LoadConfig("")
		if e != nil {
			log.Fatal(e)
		}
		db, err = system.OpenPostgres(ctx, c.DatabaseURL)
		if err != nil {
			log.Fatal(err)
		}
		defer db.Close()
	}
	updateCtx, stopUpdates := context.WithCancel(ctx)
	var updateWG sync.WaitGroup
	updates := 0
	updateErrors := 0
	if *scenario == "updates" {
		updateWG.Add(1)
		go func() {
			defer updateWG.Done()
			rng := rand.New(rand.NewSource(*seed + 1))
			tick := time.NewTicker(time.Second / time.Duration(*updateRate))
			defer tick.Stop()
			for {
				select {
				case <-updateCtx.Done():
					return
				case <-tick.C:
					qctx, cancel := context.WithTimeout(updateCtx, 2*time.Second)
					_, e := db.Pool.Exec(qctx, "UPDATE products SET version=version+1,updated_at=clock_timestamp() WHERE id=$1", rng.Intn(*keys)+1)
					cancel()
					if e != nil {
						updateErrors++
					} else {
						updates++
					}
				}
			}
		}()
	}
	tasks := make(chan int64, *workers)
	results := make(chan bench.Sample, *workers)
	var wg sync.WaitGroup
	client := &http.Client{Timeout: 5 * time.Second}
	for i := 0; i < *workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for id := range tasks {
				results <- bench.Request(ctx, client, *url, id)
			}
		}()
	}
	var all []bench.Sample
	collected := make(chan struct{})
	go func() {
		defer close(collected)
		for s := range results {
			all = append(all, s)
		}
	}()
	start := time.Now()
	rng := rand.New(rand.NewSource(*seed))
	offered, dropped := 0, 0
	next := start
	for next.Sub(start) < *duration {
		if delay := time.Until(next); delay > 0 {
			time.Sleep(delay)
		}
		phase := float64(next.Sub(start)) / float64(*duration)
		id := bench.Key(rng, *scenario, offered, *keys, phase)
		offered++
		select {
		case tasks <- id:
		default:
			dropped++
		}
		r := *rate
		if *scenario == "burst" && phase >= 1.0/3 && phase < 2.0/3 {
			r *= 3
		}
		next = next.Add(time.Second / time.Duration(r))
	}
	close(tasks)
	wg.Wait()
	close(results)
	<-collected
	elapsed := time.Since(start)
	stopUpdates()
	updateWG.Wait()
	metricsAfter := map[string]any{}
	for name, u := range map[string]string{"app": *url, "sidecar": *sidecar} {
		m, e := bench.Metrics(ctx, u)
		if e != nil {
			metricsAfter[name] = e.Error()
		} else {
			metricsAfter[name] = m
		}
	}
	latencies := []float64{}
	errors, hits, success := 0, 0, 0
	for _, s := range all {
		latencies = append(latencies, s.LatencyMS)
		if s.Error != "" || s.Status != 200 {
			errors++
		} else {
			success++
			if s.Tier == "local" || s.Tier == "redis" {
				hits++
			}
		}
	}
	result := map[string]any{"scenario": *scenario, "seed": *seed, "keys": *keys, "payloadBytes": *payload, "workers": *workers, "requestedBaseRPS": *rate, "offeredRequests": offered, "sentRequests": len(all), "generatorDropped": dropped, "completedRequests": len(all), "achievedRPS": float64(len(all)) / elapsed.Seconds(), "offeredDurationSeconds": duration.Seconds(), "elapsedIncludingDrainSeconds": elapsed.Seconds(), "errors": errors, "p50Ms": bench.Percentile(latencies, .5), "p95Ms": bench.Percentile(latencies, .95), "p99Ms": bench.Percentile(latencies, .99), "hitRate": float64(hits) / float64(max(1, success)), "updates": updates, "updateErrors": updateErrors, "invalidationEnabled": false, "metricsBefore": metricsBefore, "metricsAfter": metricsAfter, "freshness": nil}
	if *validate {
		result["freshness"] = bench.Validate(ctx, db, all)
	}
	result["databaseReads"] = bench.MetricDelta(metricsBefore, metricsAfter, "app", `cache_events_total{kind="database_read"}`)
	result["droppedAnalysisBatches"] = bench.MetricDelta(metricsBefore, metricsAfter, "sidecar", `cache_events_total{kind="batch_dropped"}`)
	result["aiFailures"] = bench.MetricDelta(metricsBefore, metricsAfter, "sidecar", `cache_events_total{kind="ai_failure"}`)
	result["policyUpdates"] = bench.MetricDelta(metricsBefore, metricsAfter, "sidecar", `cache_events_total{kind="policy_update"}`)
	for _, p := range []string{*out, *samplesPath} {
		if e := os.MkdirAll(filepath.Dir(p), 0755); e != nil {
			log.Fatal(e)
		}
	}
	f, e := os.Create(*samplesPath)
	if e != nil {
		log.Fatal(e)
	}
	enc := json.NewEncoder(f)
	for _, s := range all {
		if e = enc.Encode(s); e != nil {
			log.Fatal(e)
		}
	}
	f.Close()
	b, _ := json.MarshalIndent(result, "", "  ")
	if e = os.WriteFile(*out, b, 0644); e != nil {
		log.Fatal(e)
	}
	fmt.Println(string(b))
}
