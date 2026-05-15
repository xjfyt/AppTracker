# Active Tracker — fish shell integration
#
# 在 ~/.config/fish/config.fish 末尾追加：
#   source /path/to/active_tracker/shell_integration/fish.fish

set -g _active_tracker_dir "$HOME/.active_tracker/shells"

function _active_tracker_update --on-event fish_prompt
    mkdir -p $_active_tracker_dir 2>/dev/null
    echo $PWD > "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
end

function _active_tracker_cleanup --on-event fish_exit
    rm -f "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
end
