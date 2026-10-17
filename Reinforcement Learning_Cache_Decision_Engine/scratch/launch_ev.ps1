Set-Location E:\Research\reinforcement_learning_research
$cmd = '/c start "" /belownormal /b .venv\Scripts\python.exe scripts\run_eviction_baselines.py --procs 3 > results\evict_baselines_stdout.log 2>&1'
Start-Process -FilePath cmd.exe -ArgumentList $cmd -WindowStyle Hidden
