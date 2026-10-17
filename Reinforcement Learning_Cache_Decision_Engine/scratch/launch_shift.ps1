Set-Location E:\Research\reinforcement_learning_research
$cmd = '/c start "" /belownormal /b .venv\Scripts\python.exe scripts\run_shifts.py --procs 5 > results\shift_stdout.log 2>&1'
Start-Process -FilePath cmd.exe -ArgumentList $cmd -WindowStyle Hidden
