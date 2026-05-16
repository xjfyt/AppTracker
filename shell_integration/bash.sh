# Active Tracker bash shell integration.
#
# Add this line to ~/.bashrc:
#   source /path/to/active_tracker/shell_integration/bash.sh

_active_tracker_dir="$HOME/.active_tracker/shells"

_active_tracker_update() {
    mkdir -p "$_active_tracker_dir" 2>/dev/null
    printf '%s\n' "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$$.cwd" 2>/dev/null

    local _last
    _last=$(fc -ln -1 2>/dev/null | sed 's/^[[:space:]]*//')
    if [ -n "$_last" ]; then
        printf '%s\n' "$_last" > "$_active_tracker_dir/$$.cmd" 2>/dev/null
        chmod 600 "$_active_tracker_dir/$$.cmd" 2>/dev/null
    fi
}

case "$PROMPT_COMMAND" in
    *_active_tracker_update*) ;;
    *)
        if [ -n "$PROMPT_COMMAND" ]; then
            PROMPT_COMMAND="_active_tracker_update;${PROMPT_COMMAND}"
        else
            PROMPT_COMMAND="_active_tracker_update"
        fi
        ;;
esac

trap 'rm -f "$_active_tracker_dir/$$.cwd" "$_active_tracker_dir/$$.cmd" 2>/dev/null' EXIT

