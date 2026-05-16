# Active Tracker Shell Integration

Optional shell integration for more accurate terminal cwd detection.

Every time the shell prompt is shown, the script writes the current directory to:

```text
~/.active_tracker/shells/<PID>.cwd
```

Only cwd is required by the Rust agent. Some scripts also write `<PID>.cmd` for future use, but command text is not required for cwd detection.

## Install

### bash

```bash
echo "source /path/to/active_tracker/shell_integration/bash.sh" >> ~/.bashrc
exec bash
```

### zsh

```zsh
echo "source /path/to/active_tracker/shell_integration/zsh.sh" >> ~/.zshrc
exec zsh
```

### fish

```fish
echo "source /path/to/active_tracker/shell_integration/fish.fish" >> ~/.config/fish/config.fish
exec fish
```

### PowerShell

```powershell
$PROFILE
Add-Content -Path $PROFILE -Value ". 'C:\path\to\active_tracker\shell_integration\powershell.ps1'"
```

Restart the shell after installation.

## Verify

```bash
ls ~/.active_tracker/shells/
cat ~/.active_tracker/shells/$$.cwd
```

The file content should be the current directory. Files are written with user-only permissions where the shell supports it.

