# Active Tracker — bash shell integration
#
# 在 ~/.bashrc 末尾追加：
#   source /path/to/active_tracker/shell_integration/bash.sh
# 主程序 UI 顶栏 "Shell 脚本目录" 按钮可一键复制路径。
#
# 作用：每次 prompt 把当前 $PWD 写到 ~/.active_tracker/shells/$$.cwd，
#       并把最近一次执行的命令写到 ~/.active_tracker/shells/$$.cmd。

_active_tracker_dir="$HOME/.active_tracker/shells"

_active_tracker_update() {
    mkdir -p "$_active_tracker_dir" 2>/dev/null
    printf '%s\n' "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$$.cwd" 2>/dev/null
    # fc -ln -1 取最近一条历史命令；空 shell 启动时可能没有，错误吞掉
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
