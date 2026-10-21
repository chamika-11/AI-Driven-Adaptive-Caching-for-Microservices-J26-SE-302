# ONE-CLICK DEMO: starts Grafana + Prometheus (Docker) and the live replay, waits until data flows, opens the dashboard.
#   powershell -ExecutionPolicy Bypass -File live\start_demo.ps1                 (real Twitter trace, default)
#   powershell -ExecutionPolicy Bypass -File live\start_demo.ps1 -Trace synthetic
# Options: -Speed <simulated seconds per real second>   -NoBrowser
param([ValidateSet("real", "synthetic")][string]$Trace = "real", [double]$Speed = 0, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Docker Desktop is not running. Start Docker Desktop, wait for 'Engine running', then run this script again." -ForegroundColor Yellow; exit 1 }

# stop an older replay
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*live_dashboard*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

if ($Trace -eq "real") {
    $newModel = "results\dqn_ckpt\real_cluster52.000-002_k1_dqn_cap0.01_s0.npz"
    if (Test-Path $newModel) { $prep = "data\processed\cluster52_000-002_k1.npz"; $model = $newModel; $label = "REAL Twitter cluster 52, 5.7 h sample" }
    else { $prep = "data\processed\cluster52_000_k1.npz"; $model = "results\dqn_ckpt\real_cluster52.000_k1_dqn_cap0.01_s0.npz"; $label = "REAL Twitter cluster 52, 2.2 h sample" }
    if ($Speed -le 0) { $Speed = 30 }
    $args = @("scripts\live_dashboard.py", "--trace", "real", "--prepared", $prep, "--cap", "0.01", "--model", $model, "--speed", "$Speed", "--loop")
} else {
    $label = "SYNTHETIC (made-up) traffic"
    if ($Speed -le 0) { $Speed = 60 }
    $args = @("scripts\live_dashboard.py", "--trace", "synthetic", "--seed", "0", "--cap", "0.01", "--model", "results\dqn_ckpt\dqn_cap0.01_s0.npz", "--speed", "$Speed", "--loop")
}
Write-Host "Starting demo: $label, speed x$Speed" -ForegroundColor Cyan
docker compose -f live\docker-compose.yml up -d | Out-Null
New-Item -ItemType Directory -Force results\logs | Out-Null
Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList $args -WindowStyle Minimized -RedirectStandardOutput "results\logs\live_dashboard.log" -RedirectStandardError "results\logs\live_dashboard.err.log"

Write-Host "Waiting for the replay to start (about 20-40 s) ..."
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    try { $m = (Invoke-WebRequest -UseBasicParsing http://localhost:8000/metrics -TimeoutSec 3).Content; if ($m -match "rlcache_recent_decision") { $ok = $true; break } } catch {}
}
if (-not $ok) { Write-Host "The replay did not start. See results\logs\live_dashboard.err.log" -ForegroundColor Red; exit 1 }
Write-Host "Waiting for Grafana ..."
for ($i = 0; $i -lt 60; $i++) { try { if ((Invoke-WebRequest -UseBasicParsing http://localhost:3000/api/health -TimeoutSec 3).Content -match '"ok"') { break } } catch {}; Start-Sleep -Seconds 2 }
$url = "http://localhost:3000/d/rl-cache-live/rl-cache-decision-engine-live-replay?orgId=1&refresh=2s&from=now-3m&to=now"
Write-Host "READY: $url" -ForegroundColor Green
if (-not $NoBrowser) { Start-Process $url }
Write-Host "Stop everything with:  powershell -ExecutionPolicy Bypass -File live\stop_demo.ps1"
