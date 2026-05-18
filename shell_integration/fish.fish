# Active Tracker fish shell integration.
#
# 在 ~/.config/fish/config.fish 末尾追加：
#   source /path/to/active_tracker/shell_integration/fish.fish
#
# 写入两个文件：
#   ~/.active_tracker/shells/<PID>.cwd  当前工作目录
#   ~/.active_tracker/shells/<PID>.cmd  最近一次命令
#
# 双通道：
#   1) PWD variable hook —— 切目录后立刻写 .cwd（等价 PowerShell 的
#      LocationChangedAction，不受任何 prompt 框架影响）
#   2) fish_prompt event  —— 每次 prompt 前再写一次保险

set -g _active_tracker_dir "$HOME/.active_tracker/shells"

function _active_tracker_write_cwd
    mkdir -p $_active_tracker_dir 2>/dev/null
    echo $PWD > "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
end

function _active_tracker_on_pwd --on-variable PWD
    _active_tracker_write_cwd
end

function _active_tracker_on_prompt --on-event fish_prompt
    _active_tracker_write_cwd
end

function _active_tracker_cmd --on-event fish_postexec
    if test -n "$argv[1]"
        echo $argv[1] > "$_active_tracker_dir/$fish_pid.cmd" 2>/dev/null
        chmod 600 "$_active_tracker_dir/$fish_pid.cmd" 2>/dev/null
    end
end

function _active_tracker_cleanup --on-event fish_exit
    rm -f "$_active_tracker_dir/$fish_pid.cwd" "$_active_tracker_dir/$fish_pid.cmd" 2>/dev/null
end

# 启动时立刻写一次。
_active_tracker_write_cwd
