# Start the full GigBid stack on this PC and expose it publicly with a Cloudflare quick tunnel.
# Usage (PowerShell, from the repo root):  powershell -ExecutionPolicy Bypass -File scripts\start_live.ps1
# Prints the public https://....trycloudflare.com URL at the end (also saved to logs\public_url.txt).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
New-Item -ItemType Directory -Force logs | Out-Null

# Postgres and Redis (scoop installs)
& pg_isready -q | Out-Null
if ($LASTEXITCODE -ne 0) { & pg_ctl -D $env:PGDATA -l "$root\logs\postgres.log" start | Out-Null; Start-Sleep 3 }
try { if ((& redis-cli ping) -ne "PONG") { throw "no redis" } } catch {
  Start-Process -WindowStyle Hidden -FilePath (Get-Command redis-server).Source -ArgumentList "--port", "6379"; Start-Sleep 2 }

$env:APP_ENV = "production"      # secure cookies over the https tunnel
$env:PYTHONIOENCODING = "utf-8"

function Start-Svc($name, $argv) {
  Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList $argv `
    -RedirectStandardOutput "$root\logs\$name.out.log" -RedirectStandardError "$root\logs\$name.log" -WorkingDirectory $root
}
Start-Svc "gigsim" @("-m", "uvicorn", "gigsim.app:app", "--port", "8081")
Start-Sleep 3
Start-Svc "mcp" @("-m", "scripts.run_mcp_servers")
Start-Sleep 20
Start-Svc "api" @("-m", "scripts.serve_api", "--port", "8000")
Start-Sleep 8
Start-Svc "worker" @("-m", "worker.main")

$cf = (Get-ChildItem "C:\Program Files*\cloudflared\cloudflared.exe" | Select-Object -First 1).FullName
Remove-Item "$root\logs\tunnel.log" -ErrorAction SilentlyContinue
Start-Process -WindowStyle Hidden -FilePath $cf -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://localhost:8000" `
  -RedirectStandardError "$root\logs\tunnel.log" -RedirectStandardOutput "$root\logs\tunnel.out.log"
$url = $null
for ($i = 0; $i -lt 30 -and -not $url; $i++) {
  Start-Sleep 2
  $m = Select-String -Path "$root\logs\tunnel.log" -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($m) { $url = $m.Matches[0].Value }
}
$url | Out-File -Encoding utf8 "$root\logs\public_url.txt"
"GigBid public URL: $url"
