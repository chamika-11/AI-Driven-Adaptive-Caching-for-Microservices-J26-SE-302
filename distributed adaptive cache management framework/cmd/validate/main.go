package main

import (
	"adaptivecache/internal/bench"
	"adaptivecache/internal/system"
	"context"
	"encoding/json"
	"flag"
	"io"
	"log"
	"os"
)

func main() {
	path := flag.String("samples", "results/samples.jsonl", "load samples")
	flag.Parse()
	f, e := os.Open(*path)
	if e != nil {
		log.Fatal(e)
	}
	defer f.Close()
	var samples []bench.Sample
	d := json.NewDecoder(f)
	for {
		var s bench.Sample
		e = d.Decode(&s)
		if e == io.EOF {
			break
		}
		if e != nil {
			log.Fatal(e)
		}
		samples = append(samples, s)
	}
	c, e := system.LoadConfig("")
	if e != nil {
		log.Fatal(e)
	}
	db, e := system.OpenPostgres(context.Background(), c.DatabaseURL)
	if e != nil {
		log.Fatal(e)
	}
	defer db.Close()
	_ = json.NewEncoder(os.Stdout).Encode(bench.Validate(context.Background(), db, samples))
}
