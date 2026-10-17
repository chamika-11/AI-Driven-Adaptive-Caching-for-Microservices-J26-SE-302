$ErrorActionPreference = 'Stop'
function Check { if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" } }
docker compose -f compose.yaml -f compose.smoke.yaml up -d --build
Check
docker compose run --rm --entrypoint /smoke tools -app http://app:8080 -sidecar http://sidecar:8081 -workflow http://workflow:8082
Check
try {
    docker compose stop workflow
    Check
    docker compose run --rm --entrypoint /smoke tools -app http://app:8080 -sidecar http://sidecar:8081 -failure-only
    Check
} finally {
    docker compose start workflow
}
