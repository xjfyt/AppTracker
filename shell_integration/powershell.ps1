# Active Tracker PowerShell shell integration.
#
# 在 PowerShell profile (`$PROFILE`) 末尾追加：
#   . 'C:\path\to\active_tracker\shell_integration\powershell.ps1'
#
# 写入两个文件：
#   ~/.active_tracker/shells/<PID>.cwd  当前工作目录
#   ~/.active_tracker/shells/<PID>.cmd  最近一次命令
#
# cd 触发：用 $ExecutionContext.InvokeCommand.LocationChangedAction，
# Set-Location 后必定回调，不受 oh-my-posh / starship / 自定义 prompt
# 覆盖影响（旧版只 hook prompt，加载顺序在前就会被后面的 prompt 覆盖掉）。

$ActiveTrackerDir = Join-Path $HOME ".active_tracker\shells"
$ActiveTrackerUtf8 = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $ActiveTrackerDir)) {
    New-Item -ItemType Directory -Path $ActiveTrackerDir -Force | Out-Null
}

function global:_ActiveTrackerWriteState {
    $cwdFile = Join-Path $ActiveTrackerDir "$PID.cwd"
    $cmdFile = Join-Path $ActiveTrackerDir "$PID.cmd"
    try {
        [System.IO.File]::WriteAllText($cwdFile, "$($PWD.Path)`n", $ActiveTrackerUtf8)
        $last = Get-History -Count 1 -ErrorAction SilentlyContinue
        if ($last) {
            [System.IO.File]::WriteAllText($cmdFile, "$($last.CommandLine)`n", $ActiveTrackerUtf8)
        }
    } catch {}
}

# 启动时先写一次，保证初始 cwd 立刻可读。
_ActiveTrackerWriteState

# cd / Set-Location / Push-Location / Pop-Location 之后必触发，
# 与 prompt 函数无关。即便 starship / oh-my-posh 完全接管 prompt，cwd 文件
# 依旧会被刷新。
$ExecutionContext.InvokeCommand.LocationChangedAction = {
    _ActiveTrackerWriteState
}

# 仍然兜底 hook 一次 prompt：LocationChangedAction 在 Set-Location 时才触发，
# 用户敲完非 cd 命令时也希望刷新 .cmd（最近命令）。如果 prompt 被覆盖
# 也无所谓 —— LocationChangedAction 已经能保证 .cwd 准确。
if (-not (Test-Path Function:\_ActiveTrackerOriginalPrompt)) {
    $global:_ActiveTrackerOriginalPrompt = $function:prompt
}
function global:prompt {
    _ActiveTrackerWriteState
    & $global:_ActiveTrackerOriginalPrompt
}

$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action {
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cwd") -ErrorAction SilentlyContinue
    Remove-Item -Path (Join-Path $ActiveTrackerDir "$PID.cmd") -ErrorAction SilentlyContinue
}

