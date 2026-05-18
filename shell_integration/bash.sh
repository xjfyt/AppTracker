# Active Tracker bash shell integration.
#
# 在 ~/.bashrc 末尾追加：
#   source /path/to/active_tracker/shell_integration/bash.sh
#
# 写入两个文件：
#   ~/.active_tracker/shells/<PID>.cwd  当前工作目录
#   ~/.active_tracker/shells/<PID>.cmd  最近一次命令
#
# 走两条独立的写入通道：
#   1) cd / pushd / popd 函数包装 —— 切目录后立刻写 .cwd
#   2) PROMPT_COMMAND 回调 —— 每次 prompt 前写 .cwd 和 .cmd
# 双通道是因为 bash 没有 chpwd 钩子；如果用户在我们 source 之后再 eval
# starship/oh-my-posh，PROMPT_COMMAND 可能被覆盖，但 cd 包装仍然能保证
# .cwd 准确。

_active_tracker_dir="$HOME/.active_tracker/shells"

_active_tracker_write_cwd() {
    mkdir -p "$_active_tracker_dir" 2>/dev/null
    printf '%s\n' "$PWD" > "$_active_tracker_dir/$$.cwd" 2>/dev/null
    chmod 600 "$_active_tracker_dir/$$.cwd" 2>/dev/null
}

_active_tracker_update() {
    _active_tracker_write_cwd

    local _last
    _last=$(fc -ln -1 2>/dev/null | sed 's/^[[:space:]]*//')
    if [ -n "$_last" ]; then
        printf '%s\n' "$_last" > "$_active_tracker_dir/$$.cmd" 2>/dev/null
        chmod 600 "$_active_tracker_dir/$$.cmd" 2>/dev/null
    fi
}

# bash 没有 zsh 的 chpwd / PowerShell 的 LocationChangedAction，
# 这里包装内建命令在切目录后立刻写 .cwd。第三方工具直接调
# `builtin cd` 仍会绕开，但 PROMPT_COMMAND 兜底。
cd() { builtin cd "$@" && _active_tracker_write_cwd; }
pushd() { builtin pushd "$@" && _active_tracker_write_cwd; }
popd() { builtin popd "$@" && _active_tracker_write_cwd; }

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

# 启动时立刻写一次，保证 agent 第一次读就能拿到真实 cwd。
_active_tracker_write_cwd

trap 'rm -f "$_active_tracker_dir/$$.cwd" "$_active_tracker_dir/$$.cmd" 2>/dev/null' EXIT
