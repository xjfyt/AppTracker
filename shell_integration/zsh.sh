# Active Tracker zsh shell integration.
#
# Add this line to ~/.zshrc:
#   source /path/to/active_tracker/shell_integration/zsh.sh

_active_tracker_dir="$HOME/.active_tracker/shells"

_active_tracker_update() {
    mkdir -p "$_active_tracker_dir" 2>/dev/null
    print -r -- "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$$.cwd" 2>/dev/null

    local _last
    _last=$(fc -ln -1 2>/dev/null | sed 's/^[[:space:]]*//')
    if [ -n "$_last" ]; then
        print -r -- "$_last" > "$_active_tracker_dir/$$.cmd" 2>/dev/null
        chmod 600 "$_active_tracker_dir/$$.cmd" 2>/dev/null
    fi
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd _active_tracker_update

_active_tracker_cleanup() {
    rm -f "$_active_tracker_dir/$$.cwd" "$_active_tracker_dir/$$.cmd" 2>/dev/null
}
add-zsh-hook zshexit _active_tracker_cleanup

