# Active Tracker PowerShell shell integration.
#
# Add this line to your PowerShell profile:
#   . 'C:\path\to\active_tracker\shell_integration\powershell.ps1'

$ActiveTrackerDir = Join-Path $HOME ".active_tracker\shells"
$ActiveTrackerUtf8 = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $ActiveTrackerDir)) {
    New-Item -ItemType Directory -Path $ActiveTrackerDir -Force | Out-Null
}

if (-not (Test-Path Function:\_OriginalPrompt)) {
    $global:_OriginalPrompt = $function:prompt
}

function global:prompt {
    $cwdFile = Join-Path $ActiveTrackerDir "$PID.cwd"
    $cmdFile = Join-Path $ActiveTrackerDir "$PID.cmd"
    try {
        [System.IO.File]::WriteAllText($cwdFile, "$($PWD.Path)`n", $ActiveTrackerUtf8)
        $last = Get-History -Count 1 -ErrorAction SilentlyContinue
        if ($last) {
            [System.IO.File]::WriteAllText($cmdFile, "$($last.CommandLine)`n", $ActiveTrackerUtf8)
        }
    } catch {}
    & $global:_OriginalPrompt
}

$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action {
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cwd") -ErrorAction SilentlyContinue
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cmd") -ErrorAction SilentlyContinue
}

