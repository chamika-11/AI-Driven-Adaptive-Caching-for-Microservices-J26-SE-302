package main

import (
	"adaptivecache/internal/bench"
	"adaptivecache/internal/system"
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"time"
)

func main() {
	app := flag.String("app", "http://localhost:8080", "application")
	sidecar := flag.String("sidecar", "http://localhost:8081", "sidecar")
	workflow := flag.String("workflow", "http://localhost:8082", "workflow")
	ttl := flag.Duration("expiry-wait", 4*time.Second, "must exceed smoke max TTL")
	failureOnly := flag.Bool("failure-only", false, "assert successful requests during workflow outage")
	flag.Parse()
	ctx := context.Background()
	client := &http.Client{Timeout: 5 * time.Second}
	check := func(ok bool, msg string) {
		if !ok {
			log.Fatal(msg)
		}
		fmt.Println("PASS:", msg)
	}
	if *failureOnly {
		before, _ := bench.Metrics(ctx, *sidecar)
		for i := int64(1); i <= 8; i++ {
			s := bench.Request(ctx, client, *app, i)
			check(s.Status == 200, "request succeeds during AI outage")
		}
		deadline := time.Now().Add(10 * time.Second)
		for {
			after, err := bench.Metrics(ctx, *sidecar)
			if err == nil && after[`cache_events_total{kind="ai_failure"}`] > before[`cache_events_total{kind="ai_failure"}`] {
				check(true, "AI failure observed while requests succeed")
				break
			}
			if time.Now().After(deadline) {
				log.Fatal("AI outage was not observed by a worker")
			}
			time.Sleep(50 * time.Millisecond)
		}
		return
	}
	b, _ := json.Marshal(system.LookupRequest{CacheKey: "product:1", Endpoint: system.ProductEndpoint})
	r, e := client.Post(*sidecar+"/cache/invalidate", "application/json", bytes.NewReader(b))
	if e != nil {
		log.Fatal(e)
	}
	r.Body.Close()
	before, _ := bench.Metrics(ctx, *sidecar)
	wfBefore, _ := bench.Metrics(ctx, *workflow)
	s := bench.Request(ctx, client, *app, 1)
	check(s.Status == 200 && s.Tier == "database", "database fetch on miss")
	s = bench.Request(ctx, client, *app, 1)
	check(s.Status == 200 && (s.Tier == "local" || s.Tier == "redis"), "subsequent cache hit")
	for i := 0; i < 8; i++ {
		s = bench.Request(ctx, client, *app, 1)
		check(s.Status == 200, "batch-driving request")
	}
	deadline := time.Now().Add(10 * time.Second)
	for {
		after, _ := bench.Metrics(ctx, *sidecar)
		if after[`cache_events_total{kind="policy_update"}`] > before[`cache_events_total{kind="policy_update"}`] {
			check(after[`cache_events_total{kind="batch_created"}`] > before[`cache_events_total{kind="batch_created"}`], "batch created")
			check(true, "TTL decision applied")
			break
		}
		if time.Now().After(deadline) {
			log.Fatal("no applied decision before deadline")
		}
		time.Sleep(50 * time.Millisecond)
	}
	wfAfter, _ := bench.Metrics(ctx, *workflow)
	check(wfAfter[`cache_events_total{kind="workflow_call"}`] > wfBefore[`cache_events_total{kind="workflow_call"}`], "workflow invoked")
	time.Sleep(*ttl)
	s = bench.Request(ctx, client, *app, 1)
	check(s.Status == 200 && s.Tier == "database", "expiry causes later miss")
}
