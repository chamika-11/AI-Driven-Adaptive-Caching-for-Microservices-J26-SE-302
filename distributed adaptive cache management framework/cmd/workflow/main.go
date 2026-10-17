package main

import (
	"adaptivecache/internal/system"
	"log"
)

func main() {
	c, e := system.LoadConfig(":8082")
	if e != nil {
		log.Fatal(e)
	}
	w := &system.Workflow{Config: c, Predictor: system.MockLSTM{}, Agent: system.MockRL{}, Metrics: system.NewMetrics()}
	if e = system.Serve(c, w.Handler(), nil); e != nil {
		log.Fatal(e)
	}
}
