package system

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/collectors"
)

type Metrics struct {
	Registry                 *prometheus.Registry
	Requests, DB, Lookup, AI *prometheus.HistogramVec
	Events                   *prometheus.CounterVec
	Gauges                   *prometheus.GaugeVec
}

func NewMetrics() *Metrics {
	m := &Metrics{Registry: prometheus.NewRegistry()}
	hist := func(name string) *prometheus.HistogramVec {
		return prometheus.NewHistogramVec(prometheus.HistogramOpts{Name: name, Help: name, Buckets: []float64{.0001, .0005, .001, .005, .01, .025, .05, .1, .25, .5, 1, 2, 5, 10}}, []string{"outcome"})
	}
	m.Requests = hist("app_request_seconds")
	m.DB = hist("database_read_seconds")
	m.Lookup = hist("cache_lookup_seconds")
	m.AI = hist("ai_processing_seconds")
	m.Events = prometheus.NewCounterVec(prometheus.CounterOpts{Name: "cache_events_total", Help: "Bounded event kinds; never cache keys"}, []string{"kind"})
	m.Gauges = prometheus.NewGaugeVec(prometheus.GaugeOpts{Name: "cache_state", Help: "Queue, policy and local cache state"}, []string{"kind"})
	m.Registry.MustRegister(m.Requests, m.DB, m.Lookup, m.AI, m.Events, m.Gauges, collectors.NewGoCollector(), collectors.NewProcessCollector(collectors.ProcessCollectorOpts{}))
	return m
}
func (m *Metrics) Inc(kind string)                  { m.Events.WithLabelValues(kind).Inc() }
func (m *Metrics) Gauge(kind string, value float64) { m.Gauges.WithLabelValues(kind).Set(value) }
