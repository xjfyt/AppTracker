@echo off

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
set "ACTIVE_TRACKER_CMD_CWD=%CD%"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$utf8=[System.Text.UTF8Encoding]::new($false); [System.IO.File]::WriteAllText($env:ACTIVE_TRACKER_CMD_CWD_FILE, $env:ACTIVE_TRACKER_CMD_CWD + [Environment]::NewLine, $utf8)" >nul 2>nul
exit /b 0
