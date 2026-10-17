.PHONY: up down seed test race fmt vet smoke bench
up:
	docker compose up -d --build
down:
	docker compose down
seed:
	docker compose run --rm tools -mode seed -keys 1000 -payload 1024
fmt:
	gofmt -w cmd internal
vet:
	go vet ./...
test:
	go test ./...
race:
	go test -race ./...
smoke:
	docker compose -f compose.yaml -f compose.smoke.yaml up -d --build
	docker compose run --rm --entrypoint /smoke tools -app http://app:8080 -sidecar http://sidecar:8081 -workflow http://workflow:8082
	docker compose stop workflow
	docker compose run --rm --entrypoint /smoke tools -app http://app:8080 -sidecar http://sidecar:8081 -failure-only; status=$$?; docker compose start workflow; exit $$status
bench:
	docker compose run --rm --entrypoint /load tools -url http://app:8080 -sidecar http://sidecar:8081 -duration 10s -rate 100 -out /results/smoke.json -samples /results/samples.jsonl
