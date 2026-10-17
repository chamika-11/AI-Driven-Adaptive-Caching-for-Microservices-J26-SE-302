package system

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type memoryShared struct {
	mu        sync.Mutex
	values    map[string]Entry
	fail      bool
	beforeCAS func()
}

func newMemory() *memoryShared { return &memoryShared{values: map[string]Entry{}} }
func (m *memoryShared) Get(_ context.Context, k string) (Entry, string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.fail {
		return Entry{}, "", errors.New("offline")
	}
	v, ok := m.values[k]
	if !ok || !time.Now().Before(v.ExpiresAt) {
		return Entry{}, "", ErrMissing
	}
	b, _ := json.Marshal(v)
	return v, string(b), nil
}
func (m *memoryShared) Put(_ context.Context, k string, v Entry) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.fail {
		return errors.New("offline")
	}
	if old, ok := m.values[k]; ok && old.SourceVersion > v.SourceVersion {
		return errors.New("older version")
	}
	m.values[k] = v
	return nil
}
func (m *memoryShared) CompareExpiry(ctx context.Context, k, raw string, expiry time.Time) error {
	if m.beforeCAS != nil {
		m.beforeCAS()
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	v, ok := m.values[k]
	b, _ := json.Marshal(v)
	if ok && string(b) == raw {
		if expiry.After(time.Now()) {
			v.ExpiresAt = expiry
			m.values[k] = v
		} else {
			delete(m.values, k)
		}
	}
	return nil
}
func (m *memoryShared) Delete(_ context.Context, k string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.values, k)
	return nil
}
func (m *memoryShared) Ping(context.Context) error { return nil }
func (m *memoryShared) Close() error               { return nil }
func fill(key string, version int64, ago time.Duration) FillRequest {
	return FillRequest{key, ProductEndpoint, json.RawMessage(`null`), version, time.Now().Add(-ago), .01}
}
func counter(m *Metrics, kind string) float64 {
	families, _ := m.Registry.Gather()
	for _, f := range families {
		if f.GetName() == "cache_events_total" {
			for _, v := range f.Metric {
				for _, l := range v.Label {
					if l.GetName() == "kind" && l.GetValue() == kind {
						return v.GetCounter().GetValue()
					}
				}
			}
		}
	}
	return 0
}
func waitFor(t *testing.T, fn func() bool) {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for !fn() {
		if time.Now().After(deadline) {
			t.Fatal("condition timed out")
		}
		time.Sleep(time.Millisecond)
	}
}
func TestCacheTiersPoliciesAndExpiry(t *testing.T) {
	ctx := context.Background()
	c := DefaultConfig()
	c.Bounds = Bounds{1, 120, 60, 120}
	c.LocalCapacity = 1
	c.PolicyCapacity = 1
	m := NewMetrics()
	shared := newMemory()
	cache := NewCache(c, shared, m)
	r, e := cache.Lookup(ctx, "a")
	if e != nil || r.Hit {
		t.Fatal(r, e)
	}
	f := fill("a", 1, 10*time.Second)
	if e = cache.Fill(ctx, f); e != nil {
		t.Fatal(e)
	}
	r, e = cache.Lookup(ctx, "a")
	if e != nil || !r.Hit || r.Tier != "local" || string(r.Value) != "null" {
		t.Fatal(r, e)
	}
	original := r.ExpiresAt
	_ = cache.Fill(ctx, fill("b", 1, 0))
	r, e = cache.Lookup(ctx, "a")
	if e != nil || r.Tier != "redis" || !r.ExpiresAt.Equal(original) {
		t.Fatal("promotion restarted lifetime", r, e)
	}
	if e = cache.Apply(ctx, Decision{"a", 30}); e != nil {
		t.Fatal(e)
	}
	r, _ = cache.Lookup(ctx, "a")
	if !r.ExpiresAt.Equal(f.FetchedAt.Add(30 * time.Second)) {
		t.Fatal("TTL not relative to original fetch")
	}
	f2 := fill("a", 2, 0)
	_ = cache.Fill(ctx, f2)
	r, _ = cache.Lookup(ctx, "a")
	if !r.ExpiresAt.Equal(f2.FetchedAt.Add(30 * time.Second)) {
		t.Fatal("learned TTL not used")
	}
	_ = cache.Apply(ctx, Decision{"missing", 20})
	if _, _, e = shared.Get(ctx, "missing"); !errors.Is(e, ErrMissing) {
		t.Fatal("policy fetched/created missing entry")
	}
	if len(cache.policies.items) > 1 {
		t.Fatal("unbounded policies")
	}
	if e = cache.Apply(ctx, Decision{"a", 121}); e == nil {
		t.Fatal("accepted invalid TTL")
	}
	cache.policies.put("a", Policy{20, time.Now().Add(-time.Hour), time.Now().Add(-time.Second)})
	_ = cache.Fill(ctx, fill("a", 3, 0))
	r, _ = cache.Lookup(ctx, "a")
	if r.ExpiresAt.Sub(r.FetchedAt) != 60*time.Second {
		t.Fatal("expired policy did not default")
	}
	old := fill("old", 1, 20*time.Second)
	_ = cache.Fill(ctx, old)
	_ = cache.Apply(ctx, Decision{"old", 1})
	r, _ = cache.Lookup(ctx, "old")
	if r.Hit {
		t.Fatal("expired policy retained entry")
	}
	cache.Maintain()
}
func TestPolicyCASDoesNotOverwriteConcurrentFill(t *testing.T) {
	ctx := context.Background()
	s := newMemory()
	c := NewCache(DefaultConfig(), s, NewMetrics())
	_ = c.Fill(ctx, fill("a", 1, 0))
	fresh := Entry{json.RawMessage(`"new"`), 2, time.Now(), time.Now().Add(time.Minute)}
	s.beforeCAS = func() { _ = s.Put(ctx, "a", fresh) }
	if e := c.Apply(ctx, Decision{"a", 5}); e != nil {
		t.Fatal(e)
	}
	got, _, _ := s.Get(ctx, "a")
	if got.SourceVersion != 2 || string(got.Value) != `"new"` || !got.ExpiresAt.Equal(fresh.ExpiresAt) {
		t.Fatal("fresh fill overwritten", got)
	}
}
func TestConcurrentLocalFillAndPolicy(t *testing.T) {
	c := NewCache(DefaultConfig(), newMemory(), NewMetrics())
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(2)
		go func(i int) { defer wg.Done(); _ = c.Fill(context.Background(), fill("a", int64(i+1), 0)) }(i)
		go func() { defer wg.Done(); _ = c.Apply(context.Background(), Decision{"a", 10}) }()
	}
	wg.Wait()
	r, e := c.Lookup(context.Background(), "a")
	if e != nil || !r.Hit || r.SourceVersion != 50 || r.ExpiresAt.After(r.FetchedAt.Add(time.Hour)) {
		t.Fatal(r, e)
	}
}
func event(key string) AccessEvent {
	return AccessEvent{key, ProductEndpoint, "miss", time.Now(), false, time.Millisecond}
}
func pipelineFor(t *testing.T, c Config) (*Pipeline, *Metrics) {
	t.Helper()
	m := NewMetrics()
	p := NewPipeline(c, NewCache(c, newMemory(), m), m)
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = p.Close(ctx)
	})
	return p, m
}
func TestBatchCountsSizeTimerAndHistory(t *testing.T) {
	received := make(chan AnalysisRequest, 10)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req AnalysisRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		received <- req
		decisions := []Decision{}
		for k := range req.Current.Keys {
			decisions = append(decisions, Decision{k, 60})
		}
		JSON(w, 200, AnalysisResponse{1, req.JobID, decisions})
	}))
	defer srv.Close()
	c := DefaultConfig()
	c.AIURL = srv.URL
	c.BatchSize = 2
	c.FlushInterval = 50 * time.Millisecond
	p, m := pipelineFor(t, c)
	p.Fill(fill("a", 1, 0), "ok")
	p.Record(event("a"))
	p.Record(event("a"))
	var first AnalysisRequest
	select {
	case first = <-received:
	case <-time.After(time.Second):
		t.Fatal("size flush failed")
	}
	if first.Current.TotalRequests != 2 || first.Current.Keys["a"].Accesses != 2 || counter(m, "access") != 2 || counter(m, "fill_ok") != 1 || first.Current.RequestsPerSecond <= 0 {
		t.Fatal("incorrect counts", first)
	}
	p.Record(event("a"))
	select {
	case second := <-received:
		if second.Current.TotalRequests != 1 || len(second.History) != 1 || second.History[0].TotalRequests != 2 {
			t.Fatal("history/timer", second)
		}
	case <-time.After(time.Second):
		t.Fatal("timer flush failed")
	}
}
func TestQueueSaturationAndShutdown(t *testing.T) {
	entered := make(chan struct{}, 1)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case entered <- struct{}{}:
		default:
		}
		select {
		case <-r.Context().Done():
		case <-time.After(200 * time.Millisecond):
		}
		JSON(w, 503, map[string]string{"error": "offline"})
	}))
	defer srv.Close()
	c := DefaultConfig()
	c.AIURL = srv.URL
	c.BatchSize = 1
	c.QueueCapacity = 1
	c.Workers = 1
	c.AITimeout = 100 * time.Millisecond
	c.Retries = 0
	p, m := pipelineFor(t, c)
	p.Record(event("a"))
	<-entered
	for i := 0; i < 10; i++ {
		p.Record(event("a"))
	}
	if counter(m, "batch_dropped") == 0 {
		t.Fatal("expected drops")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	start := time.Now()
	_ = p.Close(ctx)
	if time.Since(start) > time.Second {
		t.Fatal("shutdown did not cancel worker")
	}
	p.Record(event("a"))
	p.Flush()
}
func TestOutOfOrderAndMalformedDecisions(t *testing.T) {
	c := DefaultConfig()
	p, _ := pipelineFor(t, c)
	req := AnalysisRequest{SchemaVersion: 1, JobID: "new", Sequence: 2, Endpoint: ProductEndpoint, Bounds: c.Bounds, Current: Aggregate{Keys: map[string]KeyAggregate{"a": {Accesses: 1}}}}
	if e := p.apply(req, AnalysisResponse{1, "new", []Decision{{"a", 20}}}); e != nil {
		t.Fatal(e)
	}
	req.Sequence = 1
	req.JobID = "old"
	if e := p.apply(req, AnalysisResponse{1, "old", []Decision{{"a", 100}}}); e == nil {
		t.Fatal("accepted old decision")
	}
	req.Sequence = 3
	for _, res := range []AnalysisResponse{{1, "wrong", []Decision{{"a", 30}}}, {1, "old", []Decision{{"evil", 30}}}, {1, "old", []Decision{{"a", 0}}}, {1, "old", []Decision{{"a", 30}, {"a", 40}}}} {
		if e := p.apply(req, res); e == nil {
			t.Fatal("accepted malformed decision")
		}
	}
	if got := p.cache.Policies(req.Current.Keys)["a"].TTLSeconds; got != 20 {
		t.Fatal("previous policy changed", got)
	}
	var res AnalysisResponse
	if e := json.Unmarshal([]byte(`{"ttlSeconds":1.5}`), &Decision{}); e == nil {
		t.Fatal("fraction accepted")
	}
	_ = res
}

type fakeDB struct {
	reads atomic.Int64
	delay time.Duration
}

func (d *fakeDB) Product(ctx context.Context, id int64) (Product, error) {
	d.reads.Add(1)
	select {
	case <-ctx.Done():
		return Product{}, ctx.Err()
	case <-time.After(d.delay):
	}
	return Product{ID: id, Name: "product", Version: 1, UpdatedAt: time.Now()}, nil
}
func (d *fakeDB) Ping(context.Context) error { return nil }
func (d *fakeDB) Close()                     {}
func TestAppSidecarFailureAndSingleflight(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { JSON(w, 503, map[string]string{"error": "offline"}) }))
	defer srv.Close()
	c := DefaultConfig()
	c.SidecarURL = srv.URL
	db := &fakeDB{delay: 100 * time.Millisecond}
	m := NewMetrics()
	app := &App{Config: c, DB: db, Metrics: m, Client: &http.Client{}}
	server := httptest.NewServer(app.Handler())
	defer server.Close()
	var wg sync.WaitGroup
	start := make(chan struct{})
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-start
			r, e := http.Get(server.URL + "/products/1")
			if e != nil {
				t.Error(e)
				return
			}
			defer r.Body.Close()
			if r.StatusCode != 200 {
				t.Error(r.Status)
			}
		}()
	}
	close(start)
	wg.Wait()
	if db.reads.Load() != 1 {
		t.Fatal("singleflight DB reads", db.reads.Load())
	}
	if counter(m, "insertion_error") != 1 {
		t.Fatal("insert failure missing")
	}
}
func TestMockWorkflowAndFailures(t *testing.T) {
	c := DefaultConfig()
	req := AnalysisRequest{SchemaVersion: 1, JobID: "job", Sequence: 1, Endpoint: ProductEndpoint, Bounds: c.Bounds, Current: Aggregate{Start: time.Now().Add(-time.Second), End: time.Now(), Keys: map[string]KeyAggregate{"a": {Accesses: 100}}}}
	pred, _ := (MockLSTM{}).Predict(context.Background(), req)
	dec, _ := (MockRL{}).Decide(context.Background(), pred, req)
	if dec[0].TTLSeconds != c.Bounds.Default {
		t.Fatal("insufficient history fallback")
	}
	req.History = []Aggregate{req.Current, req.Current}
	dec, _ = (MockRL{}).Decide(context.Background(), pred, req)
	interval := 2.0
	req.Observations = map[string]FillObservation{"a": {ObservedUpdateIntervalSeconds: &interval}}
	short, _ := (MockRL{}).Decide(context.Background(), pred, req)
	if short[0].TTLSeconds >= dec[0].TTLSeconds {
		t.Fatal("updates should shorten TTL")
	}
	for _, mode := range []string{"malformed", "unavailable"} {
		c.AIFailure = mode
		wf := &Workflow{c, MockLSTM{}, MockRL{}, NewMetrics()}
		srv := httptest.NewServer(wf.Handler())
		var response AnalysisResponse
		e := post(context.Background(), srv.Client(), srv.URL+"/analyze", req, &response)
		srv.Close()
		if e == nil {
			t.Fatal("expected failure", mode)
		}
	}
}
func TestSidecarValidationAndNull(t *testing.T) {
	c := DefaultConfig()
	p, m := pipelineFor(t, c)
	s := &Sidecar{c, p.cache, p, m}
	srv := httptest.NewServer(s.Handler())
	defer srv.Close()
	for _, body := range []string{`{"cacheKey":"a","endpoint":"bad"}`, strings.Repeat("x", c.BodyLimit+1), `{"cacheKey":"a","endpoint":"GET:/products/:id","extra":true}`} {
		r, e := http.Post(srv.URL+"/cache/lookup", "application/json", strings.NewReader(body))
		if e != nil {
			t.Fatal(e)
		}
		r.Body.Close()
		if r.StatusCode != 400 {
			t.Fatal("validation accepted", r.Status)
		}
	}
	f := fill("a", 1, 0)
	var ack struct {
		Cached bool `json:"cached"`
	}
	if e := post(context.Background(), srv.Client(), srv.URL+"/cache/insert", f, &ack); e != nil {
		t.Fatal(e)
	}
	var res LookupResponse
	if e := post(context.Background(), srv.Client(), srv.URL+"/cache/lookup", LookupRequest{"a", ProductEndpoint}, &res); e != nil || !res.Hit || string(res.Value) != "null" {
		t.Fatal(res, e)
	}
}
func TestRedisIntegration(t *testing.T) {
	addr := os.Getenv("TEST_REDIS_ADDR")
	if addr == "" {
		t.Skip("set TEST_REDIS_ADDR for real Redis Lua integration")
	}
	r := NewRedis(addr)
	defer r.Close()
	ctx := context.Background()
	key := "integration:" + time.Now().Format("150405.000000000")
	defer r.Delete(ctx, key)
	old := Entry{json.RawMessage(`null`), 1, time.Now(), time.Now().Add(time.Minute)}
	if e := r.Put(ctx, key, old); e != nil {
		t.Fatal(e)
	}
	_, raw, e := r.Get(ctx, key)
	if e != nil {
		t.Fatal(e)
	}
	fresh := old
	fresh.SourceVersion = 2
	fresh.Value = json.RawMessage(`"fresh"`)
	if e = r.Put(ctx, key, fresh); e != nil {
		t.Fatal(e)
	}
	if e = r.CompareExpiry(ctx, key, raw, time.Now().Add(time.Second)); e != nil {
		t.Fatal(e)
	}
	got, raw, e := r.Get(ctx, key)
	if e != nil || got.SourceVersion != 2 || !got.ExpiresAt.Equal(fresh.ExpiresAt) {
		t.Fatal("CAS corruption", got, e)
	}
	_ = r.CompareExpiry(ctx, key, raw, time.Now().Add(-time.Second))
	_, _, e = r.Get(ctx, key)
	if !errors.Is(e, ErrMissing) {
		t.Fatal("expired entry not deleted", e)
	}
}

func TestEndToEndRealDependencies(t *testing.T) {
	dbURL, addr := os.Getenv("TEST_DATABASE_URL"), os.Getenv("TEST_REDIS_ADDR")
	if dbURL == "" || addr == "" {
		t.Skip("set TEST_DATABASE_URL and TEST_REDIS_ADDR for full integration")
	}
	ctx := context.Background()
	db, err := OpenPostgres(ctx, dbURL)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	shared := NewRedis(addr)
	defer shared.Close()
	c := DefaultConfig()
	c.Bounds = Bounds{1, 3, 2, 3}
	c.BatchSize = 2
	c.FlushInterval = 20 * time.Millisecond
	c.AITimeout = 50 * time.Millisecond
	c.Retries = 0
	wm := NewMetrics()
	wf := &Workflow{c, MockLSTM{}, MockRL{}, wm}
	healthy := wf.Handler()
	var offline atomic.Bool
	workflow := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if offline.Load() {
			JSON(w, 503, map[string]string{"error": "offline"})
			return
		}
		healthy.ServeHTTP(w, r)
	}))
	defer workflow.Close()
	c.AIURL = workflow.URL
	m := NewMetrics()
	cache := NewCache(c, shared, m)
	_ = cache.Invalidate(ctx, "product:1")
	p := NewPipeline(c, cache, m)
	defer func() {
		shutdown, cancel := context.WithTimeout(ctx, time.Second)
		defer cancel()
		_ = p.Close(shutdown)
	}()
	sidecar := httptest.NewServer((&Sidecar{c, cache, p, m}).Handler())
	defer sidecar.Close()
	c.SidecarURL = sidecar.URL
	app := httptest.NewServer((&App{Config: c, DB: db, Metrics: NewMetrics(), Client: &http.Client{}}).Handler())
	defer app.Close()
	request := func() string {
		t.Helper()
		res, e := http.Get(app.URL + "/products/1")
		if e != nil {
			t.Fatal(e)
		}
		res.Body.Close()
		if res.StatusCode != 200 {
			t.Fatal(res.Status)
		}
		return res.Header.Get("X-Cache-Tier")
	}
	if tier := request(); tier != "database" {
		t.Fatal("expected DB miss", tier)
	}
	t.Log("database fetch on miss")
	if tier := request(); tier != "local" {
		t.Fatal("expected local hit", tier)
	}
	t.Log("subsequent local cache hit")
	waitFor(t, func() bool { return counter(m, "policy_update") > 0 })
	if counter(wm, "workflow_call") < 1 || counter(m, "batch_created") < 1 {
		t.Fatal("workflow path not observed")
	}
	t.Log("batch created, workflow invoked, policy applied")
	time.Sleep(3100 * time.Millisecond)
	if tier := request(); tier != "database" {
		t.Fatal("expected expired miss", tier)
	}
	t.Log("later expiry causes DB miss")
	offline.Store(true)
	for i := 0; i < 4; i++ {
		request()
	}
	waitFor(t, func() bool { return counter(m, "ai_failure") > 0 })
	t.Log("requests succeed during AI outage")
}

func TestAppShutdownCancelsDatabaseWork(t *testing.T) {
	c := DefaultConfig()
	c.Mode = "none"
	db := &fakeDB{delay: time.Minute}
	app := NewApp(c, db, NewMetrics())
	server := httptest.NewServer(app.Handler())
	defer server.Close()
	done := make(chan struct{})
	go func() {
		defer close(done)
		r, e := http.Get(server.URL + "/products/1")
		if e == nil {
			r.Body.Close()
		}
	}()
	waitFor(t, func() bool { return db.reads.Load() > 0 })
	app.Close()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("shutdown did not cancel DB call")
	}
}

func TestInferenceDoesNotHoldRequestPath(t *testing.T) {
	entered, release := make(chan struct{}), make(chan struct{})
	var once sync.Once
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		once.Do(func() { close(entered) })
		select {
		case <-release:
		case <-r.Context().Done():
			return
		}
		var req AnalysisRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		JSON(w, 200, AnalysisResponse{1, req.JobID, []Decision{{"a", 60}}})
	}))
	defer srv.Close()
	c := DefaultConfig()
	c.AIURL = srv.URL
	c.BatchSize = 1
	c.AITimeout = time.Second
	c.Retries = 0
	p, _ := pipelineFor(t, c)
	_ = p.cache.Fill(context.Background(), fill("a", 1, 0))
	p.Record(event("a"))
	<-entered
	done := make(chan struct{})
	go func() {
		defer close(done)
		r, e := p.cache.Lookup(context.Background(), "a")
		if e != nil || !r.Hit {
			t.Error("cache unavailable during inference")
		}
		p.Record(event("a"))
	}()
	select {
	case <-done:
		close(release)
	case <-time.After(time.Second):
		close(release)
		t.Fatal("request waited for inference")
	}
}
