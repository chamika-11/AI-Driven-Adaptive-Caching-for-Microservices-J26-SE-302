package bench

import (
	"adaptivecache/internal/system"
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"
)

type Sample struct {
	ID        int64     `json:"id"`
	Version   int64     `json:"version"`
	Started   time.Time `json:"started"`
	Finished  time.Time `json:"finished"`
	LatencyMS float64   `json:"latencyMs"`
	Status    int       `json:"status"`
	Tier      string    `json:"tier"`
	Error     string    `json:"error,omitempty"`
}

func Request(ctx context.Context, client *http.Client, url string, id int64) Sample {
	s := Sample{ID: id, Started: time.Now()}
	req, e := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("%s/products/%d", url, id), nil)
	if e != nil {
		s.Error = e.Error()
		return s
	}
	r, e := client.Do(req)
	if e != nil {
		s.Finished = time.Now()
		s.LatencyMS = float64(s.Finished.Sub(s.Started).Microseconds()) / 1000
		s.Error = e.Error()
		return s
	}
	body, e := io.ReadAll(io.LimitReader(r.Body, 8<<20))
	r.Body.Close()
	s.Finished = time.Now()
	s.LatencyMS = float64(s.Finished.Sub(s.Started).Microseconds()) / 1000
	s.Status = r.StatusCode
	s.Tier = r.Header.Get("X-Cache-Tier")
	if e != nil {
		s.Error = e.Error()
		return s
	}
	if r.StatusCode == 200 {
		var p system.Product
		if e = json.Unmarshal(body, &p); e != nil {
			s.Error = e.Error()
		} else {
			s.Version = p.Version
		}
	}
	return s
}
func Key(rng *rand.Rand, scenario string, i, keys int, phase float64) int64 {
	switch scenario {
	case "unique":
		return int64(i + 1)
	case "hot", "updates", "burst":
		if rng.Float64() < .9 {
			return int64(rng.Intn(max(1, keys/100)) + 1)
		}
	case "changing":
		if rng.Float64() < .9 {
			hot := max(1, keys/100)
			offset := int(phase*4) * max(1, keys/4)
			return int64((offset+rng.Intn(hot))%keys + 1)
		}
	}
	return int64(rng.Intn(keys) + 1)
}
func Percentile(v []float64, p float64) float64 {
	if len(v) == 0 {
		return 0
	}
	sort.Float64s(v)
	return v[min(len(v)-1, int(float64(len(v)-1)*p))]
}
func Metrics(ctx context.Context, url string) (map[string]float64, error) {
	req, e := http.NewRequestWithContext(ctx, "GET", url+"/metrics", nil)
	if e != nil {
		return nil, e
	}
	r, e := (&http.Client{Timeout: 2 * time.Second}).Do(req)
	if e != nil {
		return nil, e
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return nil, fmt.Errorf("metrics status %d", r.StatusCode)
	}
	out := map[string]float64{}
	sc := bufio.NewScanner(io.LimitReader(r.Body, 4<<20))
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Fields(line)
		if len(parts) == 2 {
			v, e := strconv.ParseFloat(parts[1], 64)
			if e == nil {
				out[parts[0]] = v
			}
		}
	}
	return out, sc.Err()
}

type Freshness struct {
	Checked           int      `json:"checked"`
	Fresh             int      `json:"fresh"`
	Stale             int      `json:"stale"`
	Indeterminate     int      `json:"indeterminate"`
	Errors            int      `json:"errors"`
	ValidationDBReads int      `json:"validationDatabaseReads"`
	StaleRate         *float64 `json:"staleRate"`
}

// Queries are deliberately separate from production timing. A later update cannot
// prove a response was stale at request start; classify it as indeterminate.
func MetricDelta(before, after map[string]any, service, metric string) *float64 {
	a, okA := before[service].(map[string]float64)
	b, okB := after[service].(map[string]float64)
	if !okA || !okB {
		return nil
	}
	v := b[metric] - a[metric]
	if v < 0 {
		return nil
	}
	return &v
}

func Validate(ctx context.Context, db system.Database, samples []Sample) Freshness {
	var out Freshness
	for _, s := range samples {
		if s.Status != 200 || s.Error != "" {
			continue
		}
		out.Checked++
		out.ValidationDBReads++
		qctx, cancel := context.WithTimeout(ctx, 2*time.Second)
		p, e := db.Product(qctx, s.ID)
		cancel()
		if e != nil {
			out.Errors++
			continue
		}
		if p.Version == s.Version {
			out.Fresh++
		} else if p.Version > s.Version && !p.UpdatedAt.After(s.Started) {
			out.Stale++
		} else {
			out.Indeterminate++
		}
	}
	if n := out.Fresh + out.Stale; n > 0 {
		v := float64(out.Stale) / float64(n)
		out.StaleRate = &v
	}
	return out
}
