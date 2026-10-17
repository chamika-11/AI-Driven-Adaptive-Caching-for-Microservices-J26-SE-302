package bench

import (
	"adaptivecache/internal/system"
	"context"
	"math/rand"
	"testing"
	"time"
)

type dbStub struct{ p system.Product }

func (d dbStub) Product(context.Context, int64) (system.Product, error) { return d.p, nil }
func (d dbStub) Ping(context.Context) error                             { return nil }
func (d dbStub) Close()                                                 {}
func TestFreshnessDoesNotMisclassifyLaterUpdates(t *testing.T) {
	start := time.Now()
	s := []Sample{{ID: 1, Version: 1, Status: 200, Started: start}}
	d := dbStub{system.Product{ID: 1, Version: 2, UpdatedAt: start.Add(time.Second)}}
	f := Validate(context.Background(), d, s)
	if f.Indeterminate != 1 || f.Stale != 0 || f.StaleRate != nil {
		t.Fatal(f)
	}
	d.p.UpdatedAt = start.Add(-time.Second)
	f = Validate(context.Background(), d, s)
	if f.Stale != 1 || f.ValidationDBReads != 1 || *f.StaleRate != 1 {
		t.Fatal(f)
	}
	d.p.Version = 1
	f = Validate(context.Background(), d, s)
	if f.Fresh != 1 {
		t.Fatal(f)
	}
}
func TestSeededScenarios(t *testing.T) {
	for _, s := range []string{"hot", "changing", "burst", "uniform", "unique", "updates"} {
		a := rand.New(rand.NewSource(42))
		b := rand.New(rand.NewSource(42))
		for i := 0; i < 1000; i++ {
			ka := Key(a, s, i, 1000, float64(i)/1000)
			kb := Key(b, s, i, 1000, float64(i)/1000)
			if ka != kb || ka < 1 || ka > 1000 {
				t.Fatal(s, ka, kb)
			}
		}
	}
}
