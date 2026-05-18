@echo off
rem Active Tracker CMD shell integration. ASCII-only on purpose: cmd reads
rem .cmd files as the system OEM codepage (936 on zh-CN by default), and
rem UTF-8 multi-byte characters get reinterpreted as random GBK glyphs that
rem break quoting / parameter parsing. Do NOT add non-ASCII comments here.
rem
rem Installed via HKCU\Software\Microsoft\Command Processor\AutoRun.
rem
rem Writes:
rem   %USERPROFILE%\.active_tracker\shells\<PID>.cwd  current dir
rem   %USERPROFILE%\.active_tracker\shells\<PID>.cmd  last command (not yet
rem                                                   wired; doskey can't
rem                                                   capture history easily)

if /I "%~1"=="--update" (
    call :ensure_state
    call :write_cwd
    exit /b 0
)

if /I "%~1"=="--cleanup" (
    call :ensure_state
    if defined ACTIVE_TRACKER_CMD_CWD_FILE del "%ACTIVE_TRACKER_CMD_CWD_FILE%" >nul 2>nul
    if defined ACTIVE_TRACKER_CMD_CMD_FILE del "%ACTIVE_TRACKER_CMD_CMD_FILE%" >nul 2>nul
    exit /b 0
)

rem AutoRun also fires for `cmd /c "..."` one-shot child processes. Skip in
rem that case so we don't pollute exit codes / output of npm scripts etc.
set "ACTIVE_TRACKER_CMDCMDLINE=%CMDCMDLINE%"
if /I not "%ACTIVE_TRACKER_CMDCMDLINE:/c=%"=="%ACTIVE_TRACKER_CMDCMDLINE%" exit /b 0
if /I not "%ACTIVE_TRACKER_CMDCMDLINE:/C=%"=="%ACTIVE_TRACKER_CMDCMDLINE%" exit /b 0

if defined ACTIVE_TRACKER_CMD_INTEGRATED exit /b 0
set "ACTIVE_TRACKER_CMD_INTEGRATED=1"

call :ensure_state
call :write_cwd

doskey cd=cd $* $T call "%~f0" --update
doskey chdir=cd $* $T call "%~f0" --update
doskey pushd=pushd $* $T call "%~f0" --update
doskey popd=popd $* $T call "%~f0" --update
doskey cd..=cd .. $T call "%~f0" --update
doskey atcwd=call "%~f0" --update
doskey exit=call "%~f0" --cleanup $T exit $*

exit /b 0

:ensure_state
if not defined ACTIVE_TRACKER_CMD_PID (
    rem cmd has no $$ / %PID%. Use PowerShell once to walk up to our parent
    rem (which IS this cmd.exe), cache the result for the rest of the session.
    rem This runs inside the existing cmd console, so no extra window flashes.
    for /f %%I in ('powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "(Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID)).ParentProcessId"') do set "ACTIVE_TRACKER_CMD_PID=%%I"
)
if not defined ACTIVE_TRACKER_CMD_PID exit /b 1
set "ACTIVE_TRACKER_CMD_DIR=%USERPROFILE%\.active_tracker\shells"
if not exist "%ACTIVE_TRACKER_CMD_DIR%" mkdir "%ACTIVE_TRACKER_CMD_DIR%" >nul 2>nul
set "ACTIVE_TRACKER_CMD_CWD_FILE=%ACTIVE_TRACKER_CMD_DIR%\%ACTIVE_TRACKER_CMD_PID%.cwd"
set "ACTIVE_TRACKER_CMD_CMD_FILE=%ACTIVE_TRACKER_CMD_DIR%\%ACTIVE_TRACKER_CMD_PID%.cmd"
exit /b 0

:write_cwd
if not defined ACTIVE_TRACKER_CMD_CWD_FILE exit /b 1
rem cmd echo writes with the current console codepage. For non-ASCII paths
rem (e.g. Chinese filenames) the reader will see replacement chars. The
rem agent still gets ASCII-only paths correctly; users wanting full Unicode
rem should `chcp 65001` in their cmd session.
(echo %CD%)>"%ACTIVE_TRACKER_CMD_CWD_FILE%" 2>nul
exit /b 0
