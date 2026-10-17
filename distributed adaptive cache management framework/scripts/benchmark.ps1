param(
    [ValidateSet('none', 'fixed', 'adaptive')][string[]]$Modes = @('none', 'fixed', 'adaptive'),
    [ValidateSet('hot', 'changing', 'burst', 'uniform', 'unique', 'updates')][string[]]$Scenarios = @('hot'),
    [int]$Rate = 100,
    [string]$Duration = '10s',
    [int]$Keys = 1000,
    [int]$Payload = 1024,
    [int]$Seed = 42,
    [int]$UpdateRate = 10
)
$ErrorActionPreference = 'Stop'
function Check { if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" } }
$previousMode = $env:MODE
New-Item -ItemType Directory -Force results | Out-Null
try {
    foreach ($mode in $Modes) {
        $env:MODE = $mode
        foreach ($scenario in $Scenarios) {
            # Operates only on this Compose project's disposable cache.
            docker compose stop app sidecar
            Check
            docker compose exec -T redis redis-cli FLUSHDB
            Check
            docker compose run --rm tools -mode seed -keys $Keys -payload $Payload
            Check
            docker compose up -d --force-recreate app sidecar
            Check
            $label = "$mode-$scenario"
            docker compose run --rm --entrypoint /load tools -url http://app:8080 -sidecar http://sidecar:8081 -scenario $scenario -rate $Rate -duration $Duration -keys $Keys -payload $Payload -seed $Seed -update-rate $UpdateRate -validate -out "/results/$label.json" -samples "/results/$label-samples.jsonl" > "results/$label.log"
            Check
            Write-Output "Completed $label; results/$label.json"
        }
    }
} finally {
    $env:MODE = $previousMode
    docker compose up -d app sidecar
}
