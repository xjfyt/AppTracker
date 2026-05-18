# Active Tracker zsh shell integration.
#
# 在 ~/.zshrc 末尾追加：
#   source /path/to/active_tracker/shell_integration/zsh.sh
#
# 写入两个文件：
#   ~/.active_tracker/shells/<PID>.cwd  当前工作目录
#   ~/.active_tracker/shells/<PID>.cmd  最近一次命令
#
# 双通道：
#   1) chpwd hook  —— 切目录后立刻写 .cwd（等价 PowerShell 的
#      LocationChangedAction，对 prompt 框架完全免疫）
#   2) precmd hook —— 每次 prompt 前写 .cwd 和 .cmd

_active_tracker_dir="$HOME/.active_tracker/shells"

_active_tracker_write_cwd() {
    mkdir -p "$_active_tracker_dir" 2>/dev/null
    print -r -- "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$$.cwd" 2>/dev/null
}

_active_tracker_update() {
    _active_tracker_write_cwd

    local _last
    _last=$(fc -ln -1 2>/dev/null | sed 's/^[[:space:]]*//')
    if [ -n "$_last" ]; then
        print -r -- "$_last" > "$_active_tracker_dir/$$.cmd" 2>/dev/null
        chmod 600 "$_active_tracker_dir/$$.cmd" 2>/dev/null
    fi
}

autoload -Uz add-zsh-hook
add-zsh-hook chpwd _active_tracker_write_cwd
add-zsh-hook precmd _active_tracker_update

# 启动时立刻写一次。
_active_tracker_write_cwd

_active_tracker_cleanup() {
    rm -f "$_active_tracker_dir/$$.cwd" "$_active_tracker_dir/$$.cmd" 2>/dev/null
}
add-zsh-hook zshexit _active_tracker_cleanup
