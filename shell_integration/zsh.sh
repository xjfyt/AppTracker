# Active Tracker — zsh shell integration
#
# 在 ~/.zshrc 末尾追加：
#   source /path/to/active_tracker/shell_integration/zsh.sh
#
# 作用：每次 prompt 把 $PWD 写到 ~/.active_tracker/shells/$$.cwd

_active_tracker_dir="$HOME/.active_tracker/shells"

_active_tracker_update() {
    mkdir -p "$_active_tracker_dir" 2>/dev/null
    print -r -- "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$$.cwd" 2>/dev/null
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd _active_tracker_update

_active_tracker_cleanup() {
    rm -f "$_active_tracker_dir/$$.cwd" 2>/dev/null
}
add-zsh-hook zshexit _active_tracker_cleanup
