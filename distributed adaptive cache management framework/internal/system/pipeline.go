package system

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"runtime"
	"sync"
	"time"
)

type AccessEvent struct {
	Key, Endpoint, Tier string
	Timestamp           time.Time
	Hit                 bool
	Duration            time.Duration
}
type endpointBuffer struct {
	current Aggregate
	history []Aggregate
	fills   *lru[FillObservation]
	seq     uint64
}
type job struct {
	request AnalysisRequest
	queued  time.Time
}
type Pipeline struct {
	mu        sync.Mutex
	applyMu   sync.Mutex
	config    Config
	cache     *Cache
	metrics   *Metrics
	buffers   map[string]*endpointBuffer
	applied   map[string]uint64
	queued    map[string]time.Time
	queue     chan job
	closed    bool
	stop      chan struct{}
	loopDone  chan struct{}
	workers   sync.WaitGroup
	ctx       context.Context
	cancel    context.CancelFunc
	client    *http.Client
	closeOnce sync.Once
}

func NewPipeline(c Config, cache *Cache, m *Metrics) *Pipeline {
	ctx, cancel := context.WithCancel(context.Background())
	p := &Pipeline{config: c, cache: cache, metrics: m, buffers: map[string]*endpointBuffer{}, applied: map[string]uint64{}, queued: map[string]time.Time{}, queue: make(chan job, c.QueueCapacity), stop: make(chan struct{}), loopDone: make(chan struct{}), ctx: ctx, cancel: cancel, client: &http.Client{Timeout: c.AITimeout}}
	for _, ep := range c.Endpoints {
		p.buffers[ep] = &endpointBuffer{current: newAggregate(time.Now()), fills: newLRU[FillObservation](c.PolicyCapacity)}
	}
	for i := 0; i < c.Workers; i++ {
		p.workers.Add(1)
		go p.worker()
	}
	go p.loop()
	return p
}
func newAggregate(start time.Time) Aggregate {
	return Aggregate{Start: start, Keys: map[string]KeyAggregate{}}
}
func (p *Pipeline) Record(e AccessEvent) {
	p.metrics.Inc("access")
	p.metrics.Lookup.WithLabelValues(e.Tier).Observe(e.Duration.Seconds())
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.closed || p.config.Mode != "adaptive" {
		return
	}
	b, ok := p.buffers[e.Endpoint]
	if !ok {
		return
	}
	a := b.current.Keys[e.Key]
	a.Accesses++
	a.LookupSeconds += e.Duration.Seconds()
	b.current.TotalRequests++
	if e.Hit {
		a.Hits++
		b.current.Hits++
		if e.Tier == "local" {
			a.LocalHits++
		} else if e.Tier == "redis" {
			a.RedisHits++
		}
	} else {
		a.Misses++
		b.current.Misses++
	}
	b.current.Keys[e.Key] = a
	if b.current.TotalRequests >= p.config.BatchSize {
		p.flushLocked(e.Endpoint, b, e.Timestamp)
	}
}
func (p *Pipeline) Fill(f FillRequest, outcome string) {
	p.metrics.Inc("fill_" + outcome)
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.closed || p.config.Mode != "adaptive" {
		return
	}
	b, ok := p.buffers[f.Endpoint]
	if !ok {
		return
	}
	o := FillObservation{SourceVersion: f.SourceVersion, FetchedAt: f.FetchedAt, DBFetchSeconds: f.DBFetchSeconds, PayloadBytes: len(f.Value), Outcome: outcome}
	if old, ok := b.fills.get(f.CacheKey); ok && f.SourceVersion > old.SourceVersion {
		seconds := f.FetchedAt.Sub(old.FetchedAt).Seconds() / float64(f.SourceVersion-old.SourceVersion)
		if seconds > 0 {
			o.ObservedUpdateIntervalSeconds = &seconds
		}
	}
	b.fills.put(f.CacheKey, o)
}

// Only immutable snapshots are queued; no network I/O occurs while mu is held.
func (p *Pipeline) flushLocked(ep string, b *endpointBuffer, now time.Time) {
	if b.current.TotalRequests == 0 {
		return
	}
	a := b.current
	a.End = now
	if !a.End.After(a.Start) {
		a.End = a.Start.Add(time.Microsecond)
	}
	a.RequestsPerSecond = float64(a.TotalRequests) / max(a.End.Sub(a.Start).Seconds(), .001)
	b.seq++
	obs := map[string]FillObservation{}
	for k := range a.Keys {
		if o, ok := b.fills.get(k); ok {
			obs[k] = o
		}
	}
	req := AnalysisRequest{SchemaVersion: 1, JobID: fmt.Sprintf("%s:%d", ep, b.seq), Sequence: b.seq, Endpoint: ep, History: append([]Aggregate(nil), b.history...), Current: a, Observations: obs, Bounds: p.config.Bounds}
	b.history = append(b.history, a)
	if len(b.history) > p.config.HistorySize {
		b.history = append([]Aggregate(nil), b.history[len(b.history)-p.config.HistorySize:]...)
	}
	b.current = newAggregate(now)
	j := job{req, time.Now()}
	select {
	case p.queue <- j:
		p.queued[req.JobID] = j.queued
		p.metrics.Inc("batch_created")
	default:
		p.metrics.Inc("batch_dropped")
	}
	p.queueMetricsLocked()
}
func (p *Pipeline) queueMetricsLocked() {
	p.metrics.Gauge("queue_depth", float64(len(p.queue)))
	var oldest float64
	for _, t := range p.queued {
		oldest = max(oldest, time.Since(t).Seconds())
	}
	p.metrics.Gauge("oldest_queued_job_age_seconds", oldest)
}
func (p *Pipeline) Flush() {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.closed {
		return
	}
	for ep, b := range p.buffers {
		p.flushLocked(ep, b, time.Now())
	}
}
func (p *Pipeline) loop() {
	defer close(p.loopDone)
	flush := time.NewTicker(p.config.FlushInterval)
	maintenance := time.NewTicker(time.Second)
	defer flush.Stop()
	defer maintenance.Stop()
	for {
		select {
		case <-p.stop:
			return
		case <-flush.C:
			p.Flush()
		case <-maintenance.C:
			p.cache.Maintain()
			p.mu.Lock()
			p.queueMetricsLocked()
			p.mu.Unlock()
		}
	}
}
func (p *Pipeline) worker() {
	defer p.workers.Done()
	for j := range p.queue {
		p.mu.Lock()
		delete(p.queued, j.request.JobID)
		p.queueMetricsLocked()
		p.mu.Unlock()
		if p.ctx.Err() != nil {
			continue
		}
		p.process(j)
	}
}
func (p *Pipeline) process(j job) {
	start := time.Now()
	req := j.request
	req.Policies = p.cache.Policies(req.Current.Keys)
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)
	req.Resources = ResourceContext{LocalEntries: p.cache.Size(), LocalCapacity: p.config.LocalCapacity, QueueDepth: len(p.queue), HeapBytes: mem.HeapAlloc}
	var response AnalysisResponse
	var err error
	for attempt := 0; attempt <= p.config.Retries; attempt++ {
		ctx, cancel := context.WithTimeout(p.ctx, p.config.AITimeout)
		response = AnalysisResponse{}
		err = post(ctx, p.client, p.config.AIURL+"/analyze", req, &response)
		cancel()
		if err == nil {
			break
		}
		if attempt < p.config.Retries {
			timer := time.NewTimer(time.Duration(50*(1<<attempt)) * time.Millisecond)
			select {
			case <-p.ctx.Done():
				timer.Stop()
				return
			case <-timer.C:
			}
		}
	}
	if err == nil {
		err = p.apply(req, response)
	}
	outcome := "ok"
	if err != nil {
		outcome = "error"
		p.metrics.Inc("ai_failure")
		slog.Warn("analysis failed", "job", req.JobID, "error", err)
	}
	p.metrics.AI.WithLabelValues(outcome).Observe(time.Since(start).Seconds())
}
func validateDecisions(req AnalysisRequest, res AnalysisResponse) error {
	if res.SchemaVersion != 1 || res.JobID != req.JobID || len(res.Decisions) == 0 {
		return fmt.Errorf("invalid response identity or empty decisions")
	}
	seen := map[string]bool{}
	for _, d := range res.Decisions {
		if _, ok := req.Current.Keys[d.CacheKey]; !ok || seen[d.CacheKey] || d.TTLSeconds < req.Bounds.Min || d.TTLSeconds > req.Bounds.Max {
			return fmt.Errorf("invalid key, duplicate, or TTL")
		}
		seen[d.CacheKey] = true
	}
	return nil
}
func (p *Pipeline) apply(req AnalysisRequest, res AnalysisResponse) error {
	if err := validateDecisions(req, res); err != nil {
		p.metrics.Inc("policy_rejected")
		return err
	}
	p.applyMu.Lock()
	defer p.applyMu.Unlock()
	if req.Sequence <= p.applied[req.Endpoint] {
		p.metrics.Inc("policy_out_of_order")
		return fmt.Errorf("out of order decision")
	}
	p.applied[req.Endpoint] = req.Sequence
	for _, d := range res.Decisions {
		ctx, cancel := context.WithTimeout(p.ctx, p.config.CacheTimeout)
		err := p.cache.Apply(ctx, d)
		cancel()
		if err != nil {
			p.metrics.Inc("policy_application_failure")
			return err
		}
	}
	slog.Info("policy applied", "job", req.JobID, "keys", len(res.Decisions))
	return nil
}
func (p *Pipeline) Close(ctx context.Context) error {
	p.closeOnce.Do(func() {
		close(p.stop)
		<-p.loopDone
		p.mu.Lock()
		for ep, b := range p.buffers {
			p.flushLocked(ep, b, time.Now())
		}
		p.closed = true
		close(p.queue)
		p.mu.Unlock()
	})
	done := make(chan struct{})
	go func() { p.workers.Wait(); close(done) }()
	select {
	case <-done:
		p.cancel()
		return nil
	case <-ctx.Done():
		p.cancel()
		<-done
		return ctx.Err()
	}
}
