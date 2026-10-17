package system

import (
	"context"
	"errors"
	"math"
	"net/http"
	"sort"
	"time"
)

type Prediction struct {
	Key   string
	Reuse float64
}
type Predictor interface {
	Predict(context.Context, AnalysisRequest) ([]Prediction, error)
}
type PolicyAgent interface {
	Decide(context.Context, []Prediction, AnalysisRequest) ([]Decision, error)
}
type MockLSTM struct{}

// Exponentially weighted historical request rates: deterministic, no trained model.
func (MockLSTM) Predict(_ context.Context, r AnalysisRequest) ([]Prediction, error) {
	out := make([]Prediction, 0, len(r.Current.Keys))
	for k, a := range r.Current.Keys {
		rate := float64(a.Accesses) / max(r.Current.End.Sub(r.Current.Start).Seconds(), .001)
		var weight, sum float64
		for i, h := range r.History {
			w := float64(i + 1)
			sum += w * float64(h.Keys[k].Accesses) / max(h.End.Sub(h.Start).Seconds(), .001)
			weight += w
		}
		if weight > 0 {
			rate = .5*rate + .5*sum/weight
		}
		out = append(out, Prediction{k, rate})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Key < out[j].Key })
	return out, nil
}

type MockRL struct{}

func (MockRL) Decide(_ context.Context, p []Prediction, r AnalysisRequest) ([]Decision, error) {
	out := make([]Decision, 0, len(p))
	for _, v := range p {
		ttl := r.Bounds.Default
		if len(r.History) >= 2 {
			ttl = r.Bounds.Min + int(math.Log1p(v.Reuse)*15)
			if obs, ok := r.Observations[v.Key]; ok && obs.ObservedUpdateIntervalSeconds != nil {
				ttl = min(ttl, int(*obs.ObservedUpdateIntervalSeconds/2))
			}
		}
		ttl = max(r.Bounds.Min, min(r.Bounds.Max, ttl))
		out = append(out, Decision{v.Key, ttl})
	}
	return out, nil
}

type Workflow struct {
	Config    Config
	Predictor Predictor
	Agent     PolicyAgent
	Metrics   *Metrics
}

func (wf *Workflow) Handler() http.Handler {
	mux := http.NewServeMux()
	CommonRoutes(mux, wf.Metrics, func(context.Context) error { return nil })
	mux.HandleFunc("POST /analyze", wf.analyze)
	return mux
}
func validAnalysis(r AnalysisRequest) error {
	if r.SchemaVersion != 1 || r.JobID == "" || r.Endpoint == "" || r.Sequence == 0 || len(r.Current.Keys) == 0 || !r.Current.End.After(r.Current.Start) || r.Bounds.Min < 1 || r.Bounds.Default < r.Bounds.Min || r.Bounds.Default > r.Bounds.Max || r.Bounds.Max > r.Bounds.MaxFreshness {
		return errors.New("invalid analysis contract")
	}
	return nil
}
func (wf *Workflow) analyze(w http.ResponseWriter, r *http.Request) {
	var input AnalysisRequest
	if e := decode(w, r, wf.Config.BodyLimit, &input); e != nil {
		JSON(w, 400, map[string]string{"error": e.Error()})
		return
	}
	if e := validAnalysis(input); e != nil {
		JSON(w, 400, map[string]string{"error": e.Error()})
		return
	}
	wf.Metrics.Inc("workflow_call")
	timer := time.NewTimer(wf.Config.AILatency)
	defer timer.Stop()
	select {
	case <-r.Context().Done():
		return
	case <-timer.C:
	}
	if wf.Config.AIFailure == "unavailable" {
		JSON(w, 503, map[string]string{"error": "simulated unavailable"})
		return
	}
	predictions, e := wf.Predictor.Predict(r.Context(), input)
	if e != nil {
		JSON(w, 500, map[string]string{"error": e.Error()})
		return
	}
	decisions, e := wf.Agent.Decide(r.Context(), predictions, input)
	if e != nil {
		JSON(w, 500, map[string]string{"error": e.Error()})
		return
	}
	if wf.Config.AIFailure == "malformed" {
		_, _ = w.Write([]byte(`{"schemaVersion":1,"jobId":"wrong","decisions":[{"cacheKey":"unknown","ttlSeconds":1.5}]}`))
		return
	}
	JSON(w, 200, AnalysisResponse{1, input.JobID, decisions})
}
