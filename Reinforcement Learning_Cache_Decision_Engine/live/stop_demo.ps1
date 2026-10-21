# Stops the replay and the Grafana/Prometheus containers (the dashboard data is discarded).
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*live_dashboard*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
docker compose -f live\docker-compose.yml down
Write-Host "Demo stopped."
