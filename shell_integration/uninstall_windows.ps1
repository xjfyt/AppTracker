$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$powerShellHook = Join-Path $scriptDir "powershell.ps1"
$cmdHook = Join-Path $scriptDir "cmd.cmd"

# --- PowerShell profile cleanup ---
# Remove any line that dot-sources our powershell.ps1, including the
# preceding "# Active Tracker shell integration" marker. Match by hook
# filename, not full path, so a moved-to-different-folder install also
# gets cleaned.
$profiles = @($PROFILE) | Where-Object { $_ -and (Test-Path $_) }
foreach ($p in $profiles) {
    $lines = Get-Content -Path $p -Encoding UTF8
    $kept = @()
    $changed = $false
    foreach ($line in $lines) {
        if ($line -match 'powershell\.ps1' -and $line -match 'Active.?Tracker|active_tracker|shell_integration') {
            $changed = $true
            continue
        }
        if ($line -match '^\s*#\s*Active Tracker shell integration\s*$') {
            $changed = $true
            continue
        }
        $kept += $line
    }
    if ($changed) {
        # Trim trailing blank lines we may have left behind.
        while ($kept.Count -gt 0 -and [string]::IsNullOrWhiteSpace($kept[-1])) {
            $kept = $kept[0..($kept.Count - 2)]
        }
        Set-Content -Path $p -Value $kept -Encoding UTF8
        Write-Host "PowerShell integration removed from: $p"
    } else {
        Write-Host "PowerShell integration not found in: $p"
    }
}

# --- CMD AutoRun cleanup ---
$keyPath = "HKCU:\Software\Microsoft\Command Processor"
if (Test-Path $keyPath) {
    $autorun = (Get-ItemProperty -Path $keyPath -Name AutoRun -ErrorAction SilentlyContinue).AutoRun
    if ($autorun) {
        # Remove any 'if exist "...cmd.cmd" call "...cmd.cmd"' segment, then
        # tidy up leftover ' & ' separators.
        $pattern = 'if exist\s+"[^"]*cmd\.cmd"\s+call\s+"[^"]*cmd\.cmd"'
        $new = [regex]::Replace($autorun, $pattern, '')
        $new = ($new -replace '\s*&\s*&\s*', ' & ').Trim().TrimEnd('&').Trim()
        if ([string]::IsNullOrWhiteSpace($new)) {
            Remove-ItemProperty -Path $keyPath -Name AutoRun -ErrorAction SilentlyContinue
            Write-Host "CMD integration removed (AutoRun value cleared)."
        } elseif ($new -ne $autorun) {
            Set-ItemProperty -Path $keyPath -Name AutoRun -Value $new
            Write-Host "CMD integration removed from AutoRun (other entries preserved)."
        } else {
            Write-Host "CMD integration not found in AutoRun."
        }
    } else {
        Write-Host "CMD AutoRun is empty; nothing to do."
    }
} else {
    Write-Host "No Command Processor key; CMD integration was never installed."
}

# --- Cached shell state ---
$shellsDir = Join-Path $HOME ".active_tracker\shells"
if (Test-Path $shellsDir) {
    try {
        Remove-Item -Path $shellsDir -Recurse -Force -ErrorAction Stop
        Write-Host "Removed cached shell state: $shellsDir"
    } catch {
        Write-Host "Could not remove $shellsDir (in use?): $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "Done. Restart PowerShell / CMD / Windows Terminal to drop the in-memory hooks."
