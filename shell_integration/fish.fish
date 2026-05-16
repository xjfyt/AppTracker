# Active Tracker fish shell integration.
#
# Add this line to ~/.config/fish/config.fish:
#   source /path/to/active_tracker/shell_integration/fish.fish

set -g _active_tracker_dir "$HOME/.active_tracker/shells"

function _active_tracker_cwd --on-event fish_prompt
    mkdir -p $_active_tracker_dir 2>/dev/null
    echo $PWD > "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$fish_pid.cwd" 2>/dev/null
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

