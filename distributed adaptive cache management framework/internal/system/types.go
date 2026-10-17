package system

import (
	"encoding/json"
	"time"
)

const ProductEndpoint = "GET:/products/:id"

type Product struct {
	ID        int64     `json:"id"`
	Name      string    `json:"name"`
	Payload   string    `json:"payload"`
	Version   int64     `json:"version"`
	UpdatedAt time.Time `json:"updatedAt"`
}
type Entry struct {
	Value         json.RawMessage `json:"value"`
	SourceVersion int64           `json:"sourceVersion"`
	FetchedAt     time.Time       `json:"fetchedAt"`
	ExpiresAt     time.Time       `json:"expiresAt"`
}
type LookupRequest struct {
	CacheKey string `json:"cacheKey"`
	Endpoint string `json:"endpoint"`
}
type LookupResponse struct {
	Hit  bool   `json:"hit"`
	Tier string `json:"tier"`
	*Entry
}
type FillRequest struct {
	CacheKey       string          `json:"cacheKey"`
	Endpoint       string          `json:"endpoint"`
	Value          json.RawMessage `json:"value"`
	SourceVersion  int64           `json:"sourceVersion"`
	FetchedAt      time.Time       `json:"fetchedAt"`
	DBFetchSeconds float64         `json:"dbFetchSeconds"`
}
type Policy struct {
	TTLSeconds int       `json:"ttlSeconds"`
	UpdatedAt  time.Time `json:"updatedAt"`
	ExpiresAt  time.Time `json:"expiresAt"`
}
type KeyAggregate struct {
	Accesses      int     `json:"accesses"`
	Hits          int     `json:"hits"`
	Misses        int     `json:"misses"`
	LookupSeconds float64 `json:"lookupSeconds"`
	LocalHits     int     `json:"localHits"`
	RedisHits     int     `json:"redisHits"`
}
type FillObservation struct {
	SourceVersion                 int64     `json:"sourceVersion"`
	FetchedAt                     time.Time `json:"fetchedAt"`
	DBFetchSeconds                float64   `json:"dbFetchSeconds"`
	PayloadBytes                  int       `json:"payloadBytes"`
	Outcome                       string    `json:"outcome"`
	ObservedUpdateIntervalSeconds *float64  `json:"observedUpdateIntervalSeconds"`
}
type Aggregate struct {
	Start             time.Time               `json:"start"`
	End               time.Time               `json:"end"`
	TotalRequests     int                     `json:"totalRequests"`
	Hits              int                     `json:"hits"`
	Misses            int                     `json:"misses"`
	RequestsPerSecond float64                 `json:"requestsPerSecond"`
	Keys              map[string]KeyAggregate `json:"keys"`
}
type ResourceContext struct {
	LocalEntries     int      `json:"localEntries"`
	LocalCapacity    int      `json:"localCapacity"`
	QueueDepth       int      `json:"queueDepth"`
	HeapBytes        uint64   `json:"heapBytes"`
	RedisMemoryBytes *int64   `json:"redisMemoryBytes"`
	CPUUtilization   *float64 `json:"cpuUtilization"`
}
type Bounds struct {
	Min          int `json:"minTTLSeconds"`
	Max          int `json:"maxTTLSeconds"`
	Default      int `json:"defaultTTLSeconds"`
	MaxFreshness int `json:"maxFreshnessSeconds"`
}
type AnalysisRequest struct {
	SchemaVersion int                        `json:"schemaVersion"`
	JobID         string                     `json:"jobId"`
	Sequence      uint64                     `json:"sequence"`
	Endpoint      string                     `json:"endpoint"`
	History       []Aggregate                `json:"history"`
	Current       Aggregate                  `json:"current"`
	Policies      map[string]Policy          `json:"currentPolicies"`
	Observations  map[string]FillObservation `json:"observations"`
	Resources     ResourceContext            `json:"resources"`
	Bounds        Bounds                     `json:"bounds"`
}
type Decision struct {
	CacheKey   string `json:"cacheKey"`
	TTLSeconds int    `json:"ttlSeconds"`
}
type AnalysisResponse struct {
	SchemaVersion int        `json:"schemaVersion"`
	JobID         string     `json:"jobId"`
	Decisions     []Decision `json:"decisions"`
}
