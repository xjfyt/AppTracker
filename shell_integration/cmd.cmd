@echo off
rem Active Tracker CMD shell integration.
rem
rem 通过 HKCU\Software\Microsoft\Command Processor\AutoRun 装入。
rem
rem CMD 没有任何 prompt/cwd 钩子，只能靠 doskey 把 cd/chdir/pushd/popd
rem 包装成"先执行 + 再回调 --update"。所以第三方工具直接改 CMD cwd
rem 是采不到的；这是 CMD 自身限制。
rem
rem 写入两个文件：
rem   %USERPROFILE%\.active_tracker\shells\<PID>.cwd  当前工作目录
rem   %USERPROFILE%\.active_tracker\shells\<PID>.cmd  最近一次命令

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

rem AutoRun 在 cmd /c "..." 这种一次性子进程里也会被触发；只在交互模式
rem 下挂 doskey，否则脚本会污染 cmd /c 的退出码。
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
    rem CMD 没有 $$ / $PID，只能借 PowerShell 反查父进程拿一次 cmd 自己的
    rem PID，然后缓存到 ACTIVE_TRACKER_CMD_PID。每个 cmd 会话只跑一次。
    rem 这里启动 PowerShell 不会"闪黑框"——脚本本身就在 cmd 控制台里跑，
    rem PowerShell 复用父控制台。
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
rem 直接用 cmd 自己 echo 写入，不再 spawn powershell.exe —— 每次 cd 都启动
rem 一次 PowerShell（~500ms）会让人能明显感到迟滞。
rem cmd 默认以当前控制台 codepage 写入；如果 chcp 65001 则是 UTF-8。
rem reader 端 (shell_files.rs) 用 from_utf8_lossy，非 UTF-8 路径上的非
rem ASCII 字符会被替换 —— 接受这个 trade-off 换速度。Unicode 路径用户
rem 建议在 profile 里加 `chcp 65001 >nul`。
(echo %CD%)>"%ACTIVE_TRACKER_CMD_CWD_FILE%" 2>nul
exit /b 0
