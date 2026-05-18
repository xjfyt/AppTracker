$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$powerShellHook = Join-Path $scriptDir "powershell.ps1"
$cmdHook = Join-Path $scriptDir "cmd.cmd"

if (-not (Test-Path $powerShellHook)) {
    throw "PowerShell hook not found: $powerShellHook"
}
if (-not (Test-Path $cmdHook)) {
    throw "CMD hook not found: $cmdHook"
}

$profileDir = Split-Path -Parent $PROFILE
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}

$escapedPowerShellHook = $powerShellHook.Replace("'", "''")
$profileLine = ". '$escapedPowerShellHook'"
$profileText = Get-Content -Path $PROFILE -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
# Get-Content -Raw on an empty file returns $null, and `$null -like "*X*"`
# evaluates to $null (NOT $false), which makes `-notlike` also $null and the
# whole `if` falsy -- so an empty profile would silently report "already
# installed" without ever writing the source line. Coerce to string first.
if (-not $profileText) { $profileText = "" }
if ($profileText.IndexOf($powerShellHook, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
    Add-Content -Path $PROFILE -Encoding UTF8 -Value ""
    Add-Content -Path $PROFILE -Encoding UTF8 -Value "# Active Tracker shell integration"
    Add-Content -Path $PROFILE -Encoding UTF8 -Value $profileLine
    Write-Host "PowerShell integration installed: $PROFILE"
} else {
    Write-Host "PowerShell integration already installed."
}

$keyPath = "HKCU:\Software\Microsoft\Command Processor"
New-Item -Path $keyPath -Force | Out-Null
$autorun = (Get-ItemProperty -Path $keyPath -Name AutoRun -ErrorAction SilentlyContinue).AutoRun
$cmdLine = "if exist `"$cmdHook`" call `"$cmdHook`""
if ([string]::IsNullOrWhiteSpace($autorun)) {
    Set-ItemProperty -Path $keyPath -Name AutoRun -Value $cmdLine
    Write-Host "CMD integration installed."
} elseif ($autorun -notlike "*$cmdHook*") {
    Set-ItemProperty -Path $keyPath -Name AutoRun -Value "$autorun & $cmdLine"
    Write-Host "CMD integration appended to existing AutoRun."
} else {
    Write-Host "CMD integration already installed."
}

Write-Host ""
Write-Host "Done. Restart PowerShell, CMD, or Windows Terminal to activate the integration."
