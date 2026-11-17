# Remote access for the presentation laptop.
# Starts Langfuse (docker), the audit console (port 8700) and the dashboard (port 8501) if they are not running,
# then publishes them on fixed https addresses with Tailscale Funnel:
#   dashboard  https://<pc>.<tailnet>.ts.net        console  https://<pc>.<tailnet>.ts.net:8443
# Without Tailscale it falls back to Cloudflare quick tunnels (address changes every time).
#
#   powershell -ExecutionPolicy Bypass -File share.ps1          # open
#   powershell -ExecutionPolicy Bypass -File share.ps1 -Stop    # close public access
#   powershell -ExecutionPolicy Bypass -File share.ps1 -KeepAlive   # (task every 10 min) restart what is down, keep the address
#
# Anyone with the address can open the pages while public access is on.
param([switch]$Stop, [switch]$KeepAlive)

$Root = $PSScriptRoot
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Note = Join-Path $Root "dashboard\.console_url"   # the dashboard tab reads the console address from here
$Ts = "C:\Program Files\Tailscale\tailscale.exe"
$Cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $Cf)) { $Cf = "cloudflared" }

$StopMark = Join-Path $Logs "share_stopped"   # set by -Stop so the 10-minute keep-alive does not reopen
if ($Stop) {
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
    if (Test-Path $Ts) { & $Ts funnel reset *> $null }
    Remove-Item $Note -ErrorAction SilentlyContinue
    New-Item -ItemType File -Force -Path $StopMark | Out-Null
    Write-Host "Public access closed."; exit 0
}
if ($KeepAlive -and (Test-Path $StopMark)) { exit 0 }
Remove-Item $StopMark -ErrorAction SilentlyContinue

# Agent code: agent/ inside this repo, or the working copy in %USERPROFILE%\projects\agent-spike
$Agent = Join-Path $Root "agent"
if (-not (Test-Path (Join-Path $Agent "console\dist"))) { $Agent = Join-Path $env:USERPROFILE "projects\agent-spike" }
$AgentPy = Join-Path $Agent "venv_lg\Scripts\python.exe"
if (-not (Test-Path $AgentPy)) { $AgentPy = "python" }
$Py = Join-Path $env:USERPROFILE ".venvs\sto\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
$Compose = @("lf", "langfuse") | ForEach-Object { Join-Path $Agent $_ } | Where-Object { Test-Path (Join-Path $_ "docker-compose.yml") } | Select-Object -First 1

function Test-Up($url) {
    try { return (Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { return $false }
}
function Wait-Up($url, $what, $sec) {
    for ($i = 0; $i -lt $sec; $i += 2) { if (Test-Up $url) { return } ; Start-Sleep 2 }
    Write-Host "  $what did not come up at $url (see logs\)" -ForegroundColor Yellow
}

# 0. Ollama (the LLM on this PC's GPU); it normally starts at logon by itself
$OllamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
if (-not (Test-Up "http://localhost:11434/api/tags") -and (Test-Path $OllamaApp)) { Start-Process $OllamaApp }

# 1. Docker + Langfuse (trace records)
Write-Host "1/4 Langfuse"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    for ($i = 0; $i -lt 120; $i += 3) { Start-Sleep 3; docker info *> $null; if ($LASTEXITCODE -eq 0) { break } }
}
if ($Compose) { Push-Location $Compose; docker compose up -d *> (Join-Path $Logs "langfuse_up.log"); Pop-Location }
Wait-Up "http://localhost:3000/api/public/health" "Langfuse" 90

# 2. Audit console (LangGraph + AG-UI + React screen)
Write-Host "2/4 Audit console :8700"
if (-not (Test-Up "http://localhost:8700/agent/health")) {
    $env:PYTHONIOENCODING = "utf-8"
    Start-Process $AgentPy -ArgumentList "-m", "uvicorn", "console_api:api", "--app-dir", "`"$Agent`"", "--port", "8700" `
        -WorkingDirectory $Agent -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs "console_api.out.log") -RedirectStandardError (Join-Path $Logs "console_api.err.log")
}
Wait-Up "http://localhost:8700/agent/health" "Audit console" 60

# 3. Dashboard
Write-Host "3/4 Dashboard :8501"
if (-not (Test-Up "http://localhost:8501/_stcore/health")) {
    Start-Process $Py -ArgumentList "-m", "streamlit", "run", "dashboard/app.py", "--server.headless", "true", "--server.port", "8501", "--browser.gatherUsageStats", "false" `
        -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs "dashboard.out.log") -RedirectStandardError (Join-Path $Logs "dashboard.err.log")
}
Wait-Up "http://localhost:8501/_stcore/health" "Dashboard" 60

# 4. Public addresses
Write-Host "4/4 Public addresses"
if ($KeepAlive -and (Test-Path $Note)) {   # address still answers: leave it as is
    $known = (Get-Content $Note -Raw).Trim()
    if ($known -and (Test-Up "$known/agent/health")) { exit 0 }
}
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
$dashUrl = $null
if (Test-Path $Ts) {
    for ($i = 0; $i -lt 30; $i++) {   # wait for Tailscale to connect after logon
        $st = & $Ts status --json 2>$null | ConvertFrom-Json
        if ($st.BackendState -eq "Running") { break }
        Start-Sleep 2
    }
    if ($st.BackendState -eq "Running") {
        & $Ts funnel --bg 8501 *> (Join-Path $Logs "funnel.log")
        & $Ts funnel --bg --https=8443 8700 *>> (Join-Path $Logs "funnel.log")
        $hostName = $st.Self.DNSName.TrimEnd(".")
        $dashUrl = "https://$hostName"
        $consoleUrl = "https://${hostName}:8443"
    } else {
        Write-Host "  Tailscale is not signed in; using Cloudflare quick tunnels" -ForegroundColor Yellow
    }
}
if (-not $dashUrl) {
    function Open-Tunnel($port, $name) {
        $log = Join-Path $Logs "tunnel_$name.log"
        Remove-Item $log -ErrorAction SilentlyContinue
        Start-Process $Cf -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://localhost:$port" -WindowStyle Hidden `
            -RedirectStandardError $log -RedirectStandardOutput (Join-Path $Logs "tunnel_$name.out.log")
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep 1
            if (Test-Path $log) {
                $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
                if ($m) { return $m.Matches[0].Value }
            }
        }
        throw "No tunnel address for $name (see $log)"
    }
    $consoleUrl = Open-Tunnel 8700 "console"
    $dashUrl = Open-Tunnel 8501 "dashboard"
}
[IO.File]::WriteAllText($Note, $consoleUrl)
Wait-Up "$consoleUrl/agent/health" "Console public address" 60
try { Set-Clipboard $dashUrl } catch { }
"$(Get-Date -Format s)  dashboard $dashUrl  console $consoleUrl" | Out-File (Join-Path $Logs "share_urls.txt") -Encoding ascii

Write-Host ""
Write-Host "Open on the laptop:" -ForegroundColor Green
Write-Host "  Dashboard (last tab shows the console):  $dashUrl"
Write-Host "  Console only:                           $consoleUrl"
Write-Host "Close public access with: share.ps1 -Stop"
