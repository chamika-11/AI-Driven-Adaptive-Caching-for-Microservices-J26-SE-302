package main

import (
	"adaptivecache/internal/system"
	"context"
	"flag"
	"log"
	"math/rand"
	"os"
	"os/signal"
	"strings"
	"time"
)

func main() {
	mode := flag.String("mode", "seed", "seed or update")
	keys := flag.Int("keys", 1000, "number of products")
	size := flag.Int("payload", 1024, "payload bytes")
	seed := flag.Int64("seed", 42, "PRNG seed")
	duration := flag.Duration("duration", time.Minute, "update duration")
	rate := flag.Int("rate", 10, "updates per second")
	flag.Parse()
	if *keys < 1 || *size < 0 || *rate < 1 || *rate > 100000 {
		log.Fatal("invalid data flags")
	}
	c, e := system.LoadConfig("")
	if e != nil {
		log.Fatal(e)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	db, e := system.OpenPostgres(ctx, c.DatabaseURL)
	if e != nil {
		log.Fatal(e)
	}
	defer db.Close()
	if *mode == "seed" {
		_, e = db.Pool.Exec(ctx, `INSERT INTO products(id,name,payload,version,updated_at) SELECT i,'Product '||i,$2,1,clock_timestamp() FROM generate_series(1,$1::bigint) i ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload,version=products.version+1,updated_at=clock_timestamp()`, *keys, strings.Repeat("x", *size))
		if e != nil {
			log.Fatal(e)
		}
		log.Printf("seeded %d products", *keys)
		return
	}
	if *mode != "update" {
		log.Fatal("mode must be seed or update")
	}
	ctx, cancel := context.WithTimeout(ctx, *duration)
	defer cancel()
	rng := rand.New(rand.NewSource(*seed))
	ticker := time.NewTicker(time.Second / time.Duration(*rate))
	defer ticker.Stop()
	count := 0
	for {
		select {
		case <-ctx.Done():
			log.Printf("updates=%d; invalidation disabled", count)
			return
		case <-ticker.C:
			_, e = db.Pool.Exec(ctx, "UPDATE products SET version=version+1,updated_at=clock_timestamp() WHERE id=$1", rng.Intn(*keys)+1)
			if e != nil {
				log.Print(e)
			} else {
				count++
			}
		}
	}
}
