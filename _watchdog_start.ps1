$ErrorActionPreference = "Stop"
$projectRoot = "C:\Users\PC\Desktop\Quotex Signal"
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$script = Join-Path $projectRoot "skills\quotex-trader\scripts\quotex_bot.py"

$logOut = Join-Path $projectRoot "bot_out.log"
$logErr = Join-Path $projectRoot "bot_err.log"

Set-Location $projectRoot

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $python
$psi.Arguments = "`"$script`""
$psi.WorkingDirectory = $projectRoot
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
$psi.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)

$p = [System.Diagnostics.Process]::Start($psi)

# Wait a moment to check if it started
Start-Sleep -Seconds 2
if (!$p.HasExited) {
    Write-Host "Bot started successfully (PID: $($p.Id))"
    exit 0
} else {
    Write-Host "Bot exited immediately with code $($p.ExitCode)"
    exit 1
}
