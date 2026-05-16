# Active Tracker — PowerShell shell integration
#
# 在 PowerShell profile (`$PROFILE`) 末尾追加：
#   . 'C:\path\to\active_tracker\shell_integration\powershell.ps1'
#
# 作用：每次 prompt 把 $PWD 写到 ~/.active_tracker/shells/<PID>.cwd，
#       并把最近一次执行的命令写到 ~/.active_tracker/shells/<PID>.cmd。

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
    $cmdFile = Join-Path $ActiveTrackerDir "$PID.cmd"
    try {
        $PWD.Path | Out-File -FilePath $cwdFile -Encoding utf8 -Force -ErrorAction SilentlyContinue
        $last = Get-History -Count 1 -ErrorAction SilentlyContinue
        if ($last) {
            $last.CommandLine | Out-File -FilePath $cmdFile -Encoding utf8 -Force -ErrorAction SilentlyContinue
        }
    } catch {}
    & $global:_OriginalPrompt
}

# 退出时清理
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action {
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cwd") -ErrorAction SilentlyContinue
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cmd") -ErrorAction SilentlyContinue
}
