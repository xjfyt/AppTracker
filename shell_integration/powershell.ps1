# Active Tracker — PowerShell shell integration
#
# 在 PowerShell profile (`$PROFILE`) 末尾追加：
#   . 'C:\path\to\active_tracker\shell_integration\powershell.ps1'

$ActiveTrackerDir = Join-Path $HOME ".active_tracker\shells"

if (-not (Test-Path $ActiveTrackerDir)) {
    New-Item -ItemType Directory -Path $ActiveTrackerDir -Force | Out-Null
}

# 包装现有 prompt 而非替换
if (-not (Test-Path Function:\_OriginalPrompt)) {
    $global:_OriginalPrompt = $function:prompt
}

function global:prompt {
    $cwdFile = Join-Path $ActiveTrackerDir "$PID.cwd"
    try {
        $PWD.Path | Out-File -FilePath $cwdFile -Encoding utf8 -Force -ErrorAction SilentlyContinue
    } catch {}
    & $global:_OriginalPrompt
}

# 退出时清理
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action {
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cwd") -ErrorAction SilentlyContinue
}
