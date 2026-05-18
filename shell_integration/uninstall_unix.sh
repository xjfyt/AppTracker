#!/usr/bin/env bash
# Active Tracker shell integration uninstaller (bash / zsh / fish).
#
# Removes the `source .../shell_integration/<shell>.sh` line from the
# user's shell rc files, then deletes the cached cwd files.

set -u

removed_any=0

remove_from() {
    local rc="$1"
    local hook_name="$2"
    if [ ! -f "$rc" ]; then
        return
    fi
    if grep -qF "$hook_name" "$rc"; then
        local tmp
        tmp=$(mktemp)
        grep -vF "$hook_name" "$rc" > "$tmp"
        # Drop a trailing comment line we inserted if present.
        sed -i.bak -e '/^# Active Tracker shell integration$/d' "$tmp" 2>/dev/null || \
            sed -i '' -e '/^# Active Tracker shell integration$/d' "$tmp"
        rm -f "$tmp.bak"
        mv "$tmp" "$rc"
        echo "Removed integration line from: $rc"
        removed_any=1
    fi
}

remove_from "$HOME/.bashrc" "shell_integration/bash.sh"
remove_from "$HOME/.bash_profile" "shell_integration/bash.sh"
remove_from "$HOME/.zshrc" "shell_integration/zsh.sh"
remove_from "$HOME/.config/fish/config.fish" "shell_integration/fish.fish"

shells_dir="$HOME/.active_tracker/shells"
if [ -d "$shells_dir" ]; then
    rm -rf "$shells_dir"
    echo "Removed cached shell state: $shells_dir"
fi

if [ "$removed_any" -eq 0 ]; then
    echo "No shell integration lines found in known rc files."
fi

echo
echo "Done. Restart your shell to drop the in-memory hooks."
