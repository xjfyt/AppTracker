# Active Tracker PowerShell shell integration. ASCII-only on purpose:
# Windows PowerShell 5.1 reads .ps1 files as the OEM codepage unless they
# have a UTF-8 BOM, so non-ASCII comments get mangled on zh-CN systems and
# can corrupt the script. PowerShell 7 reads UTF-8 by default and is fine.
# Keeping ASCII keeps both happy.
#
# Append to your PowerShell profile ($PROFILE):
#   . 'C:\path\to\active_tracker\shell_integration\powershell.ps1'
#
# Writes:
#   ~/.active_tracker/shells/<PID>.cwd  current working dir
#   ~/.active_tracker/shells/<PID>.cmd  last command line
#
# How the hook stays alive:
#   1) Function proxies for Set-Location / Push-Location / Pop-Location.
#      `cd` is an alias to Set-Location, so this catches every cd call.
#      Function lookup beats cmdlet lookup, so we run first and forward
#      to Microsoft.PowerShell.Management\Set-Location with the full
#      module-qualified name (bypasses our own proxy).
#   2) prompt() override that chains the prior prompt. Catches .cmd
#      (last command) for shells that don't go through Set-Location.
#
# Why proxies, not LocationChangedAction:
#   $ExecutionContext.InvokeCommand.LocationChangedAction is a single slot.
#   starship, oh-my-posh, posh-git etc. can stomp it without chaining.
#   Function proxies survive prompt-framework re-init.

$ActiveTrackerDir = Join-Path $HOME ".active_tracker\shells"
$ActiveTrackerUtf8 = [System.Text.UTF8Encoding]::new($false)

if (-not (Test-Path $ActiveTrackerDir)) {
    New-Item -ItemType Directory -Path $ActiveTrackerDir -Force | Out-Null
}

function global:_ActiveTrackerWriteState {
    $dir = Join-Path $HOME ".active_tracker\shells"
    $cwdFile = Join-Path $dir "$PID.cwd"
    $cmdFile = Join-Path $dir "$PID.cmd"
    $enc = [System.Text.UTF8Encoding]::new($false)
    try {
        [System.IO.File]::WriteAllText($cwdFile, "$($PWD.Path)`n", $enc)
        $last = Get-History -Count 1 -ErrorAction SilentlyContinue
        if ($last) {
            [System.IO.File]::WriteAllText($cmdFile, "$($last.CommandLine)`n", $enc)
        }
    } catch {}
}

# Write once at source-time so the agent's first read finds a current value.
_ActiveTrackerWriteState

# --- Set-Location / Push-Location / Pop-Location proxies ---
# `cd` is an alias to Set-Location. PowerShell command resolution order is
# alias -> function -> cmdlet, so defining a function named Set-Location
# wins over the built-in cmdlet. We forward via the module-qualified name
# `Microsoft.PowerShell.Management\Set-Location` to bypass our own proxy.

function global:Set-Location {
    Microsoft.PowerShell.Management\Set-Location @args
    _ActiveTrackerWriteState
}

function global:Push-Location {
    Microsoft.PowerShell.Management\Push-Location @args
    _ActiveTrackerWriteState
}

function global:Pop-Location {
    Microsoft.PowerShell.Management\Pop-Location @args
    _ActiveTrackerWriteState
}

# --- prompt chain ---
# Save the original prompt once (don't overwrite if we are reloaded by a
# second `. $PROFILE` -- the saved one would then be our own function and
# we'd recurse).
if (-not (Test-Path Function:\_ActiveTrackerOriginalPrompt)) {
    $global:_ActiveTrackerOriginalPrompt = $function:prompt
}
function global:prompt {
    _ActiveTrackerWriteState
    & $global:_ActiveTrackerOriginalPrompt
}

$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action {
    $dir = Join-Path $HOME ".active_tracker\shells"
    Remove-Item -Path (Join-Path $dir "$PID.cwd") -ErrorAction SilentlyContinue
    Remove-Item -Path (Join-Path $dir "$PID.cmd") -ErrorAction SilentlyContinue
}
