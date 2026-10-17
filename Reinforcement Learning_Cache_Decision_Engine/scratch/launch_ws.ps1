Set-Location E:\Research\reinforcement_learning_research
$cmd = '/c start "" /belownormal /b .venv\Scripts\python.exe scripts\run_wsweep.py --procs 5 > results\dqn_wsweep_stdout.log 2>&1'
Start-Process -FilePath cmd.exe -ArgumentList $cmd -WindowStyle Hidden
