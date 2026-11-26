$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryDirectory = Split-Path -Parent $scriptDirectory
$pythonPath = Join-Path $repositoryDirectory ".venv\Scripts\python.exe"
$scriptPath = Join-Path $scriptDirectory "BBC Sport data retrieval.py"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project Python interpreter not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "BBC Sport retrieval script not found: $scriptPath"
}
if (-not $env:OneDrive -or -not (Test-Path -LiteralPath $env:OneDrive)) {
    throw "OneDrive is not configured for the current Windows user."
}

$taskName = "AI Automation BBC Football Weekly Report"
$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument ('"{0}"' -f $scriptPath) `
    -WorkingDirectory $scriptDirectory
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At "9:00AM"
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal `
    -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Retrieves the last seven days of BBC Premier League results and team xG as JSON." `
    -Force | Out-Null

Write-Output "Registered '$taskName' for Tuesdays at 9:00 AM."
Write-Output "The current user must be signed in for the task to access OneDrive."
