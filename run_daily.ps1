# Daily run for Windows Task Scheduler: python main.py --log logs\daily_YYYYMMDD.log
# Uses $PSScriptRoot so the project folder can live anywhere (no hard-coded path).
# main.py writes the log itself in UTF-8 (PowerShell 5.1 would garble Python's UTF-8 output).
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"

$py = Join-Path $env:USERPROFILE ".venvs\sto\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$logDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("daily_{0:yyyyMMdd}.log" -f (Get-Date))

& $py main.py --log $log | Out-Null
$code = $LASTEXITCODE

# keep 30 days of logs
Get-ChildItem $logDir -Filter "daily_*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force
exit $code
