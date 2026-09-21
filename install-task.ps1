$ErrorActionPreference = "Stop"

$taskName = "Tiwall Kourosh Showtime Watcher"
$watcherPath = Join-Path $PSScriptRoot "watcher.py"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    throw "Python environment is missing: $pythonPath"
}
$arguments = '"' + $watcherPath + '"'

$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Checks Tiwall for new Kourosh showtimes every 10 minutes." `
    -Force | Out-Null

Write-Host "Scheduled task installed: $taskName"
Write-Host "The watcher will run every 10 minutes while this PC is on."
