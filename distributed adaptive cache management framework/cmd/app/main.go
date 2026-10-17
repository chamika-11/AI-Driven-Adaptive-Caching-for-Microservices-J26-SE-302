package main

import (
	"adaptivecache/internal/system"
	"context"
	"log"
	"time"
)

func main() {
	c, e := system.LoadConfig(":8080")
	if e != nil {
		log.Fatal(e)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	db, e := system.OpenPostgres(ctx, c.DatabaseURL)
	cancel()
	if e != nil {
		log.Fatal(e)
	}
	a := system.NewApp(c, db, system.NewMetrics())
	if e = system.Serve(c, a.Handler(), func(context.Context) error { a.Close(); return nil }); e != nil {
		log.Fatal(e)
	}
}
