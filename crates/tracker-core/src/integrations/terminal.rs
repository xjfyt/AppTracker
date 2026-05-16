use crate::integrations::shell_files::read_shell_cwds;
use crate::models::{TerminalContext, TerminalProcess, WindowInfo};
use crate::tools::{normalize_path_lossy, redact_cmdline};
use std::collections::{HashMap, HashSet};
use sysinfo::{Pid, System};

const SHELL_NAMES: &[&str] = &[
    "bash",
    "zsh",
    "fish",
    "sh",
    "dash",
    "ash",
    "ksh",
    "tcsh",
    "csh",
    "pwsh",
    "pwsh.exe",
    "powershell",
    "powershell.exe",
    "cmd.exe",
    "nu",
    "elvish",
    "xonsh",
];

const RUNNING_BLACKLIST_NAMES: &[&str] = &["login", "tmux", "screen", "less", "more", "tail"];

const TERMINAL_EXECUTABLES: &[(&str, &str)] = &[
    ("com.apple.Terminal", "macos_terminal"),
    ("com.googlecode.iterm2", "iterm2"),
    ("io.alacritty", "alacritty"),
    ("net.kovidgoyal.kitty", "kitty"),
    ("com.github.wez.wezterm", "wezterm"),
    ("dev.warp.Warp-Stable", "warp"),
    ("co.zeit.hyper", "hyper"),
    ("com.mitchellh.ghostty", "ghostty"),
    ("org.tabby", "tabby"),
    ("Terminal", "macos_terminal"),
    ("iTerm", "iterm2"),
    ("iTerm2", "iterm2"),
    ("Alacritty", "alacritty"),
    ("kitty", "kitty"),
    ("WezTerm", "wezterm"),
    ("Warp", "warp"),
    ("Hyper", "hyper"),
    ("Ghostty", "ghostty"),
    ("Tabby", "tabby"),
    ("WindowsTerminal.exe", "windows_terminal"),
    ("wt.exe", "windows_terminal"),
    ("conhost.exe", "conhost"),
    ("cmd.exe", "cmd"),
    ("powershell.exe", "powershell"),
    ("pwsh.exe", "pwsh"),
    ("mintty.exe", "mintty"),
    ("gnome-terminal-server", "gnome_terminal"),
    ("konsole", "konsole"),
    ("xterm", "xterm"),
    ("alacritty", "alacritty"),
    ("tilix", "tilix"),
    ("terminator", "terminator"),
    ("xfce4-terminal", "xfce4_terminal"),
    ("wezterm-gui", "wezterm"),
    ("urxvt", "urxvt"),
];

pub async fn query(info: &WindowInfo) -> Option<TerminalContext> {
    if detect_terminal(info).is_none() {
        return None;
    }
    let root_pid = info.process.as_ref()?.pid;
    tokio::task::spawn_blocking(move || query_blocking(root_pid))
        .await
        .ok()
        .flatten()
}

pub fn detect_terminal(info: &WindowInfo) -> Option<&'static str> {
    let bundle = info.app_bundle_id.as_deref().unwrap_or_default();
    let app = info.app_name.as_str();
    let exe = info
        .process
        .as_ref()
        .and_then(|p| p.executable.as_deref())
        .unwrap_or_default();
    let name = info
        .process
        .as_ref()
        .map(|p| p.name.as_str())
        .unwrap_or_default();
    for candidate in [
        bundle,
        app,
        basename_cross_platform(exe).as_str(),
        basename_without_ext(&basename_cross_platform(exe)).as_str(),
        name,
    ] {
        if let Some((_, key)) = TERMINAL_EXECUTABLES.iter().find(|(k, _)| *k == candidate) {
            return Some(*key);
        }
    }
    None
}

fn query_blocking(root_pid: u32) -> Option<TerminalContext> {
    let mut system = System::new_all();
    system.refresh_all();
    let shell_files = read_shell_cwds();
    let descendants = descendants_of(&system, Pid::from_u32(root_pid));
    let mut shells = Vec::new();
    let mut running = Vec::new();
    for pid in descendants {
        let Some(proc_) = system.process(pid) else {
            continue;
        };
        let name = proc_.name().to_string_lossy().to_string();
        let lower = name.to_lowercase();
        let is_shell = SHELL_NAMES.iter().any(|s| *s == lower);
        let cwd_from_file = shell_files.get(&pid.as_u32()).cloned();
        let cwd = cwd_from_file
            .clone()
            .or_else(|| proc_.cwd().map(|p| normalize_path_lossy(p.to_path_buf())));
        let raw_cmd = proc_
            .cmd()
            .iter()
            .map(|s| s.to_string_lossy().to_string())
            .collect::<Vec<_>>();
        let (cmdline, redacted) = redact_cmdline(&raw_cmd);
        let tp = TerminalProcess {
            pid: pid.as_u32(),
            name,
            cwd,
            cmdline,
            cmdline_redacted: redacted,
            create_time: Some(proc_.start_time() as f64),
            is_shell,
            cwd_source: if cwd_from_file.is_some() {
                "shell_file".to_string()
            } else {
                "process".to_string()
            },
        };
        if is_shell {
            shells.push(tp);
        } else if !RUNNING_BLACKLIST_NAMES.iter().any(|s| *s == lower) {
            running.push(tp);
        }
    }
    shells.sort_by(|a, b| {
        b.create_time
            .unwrap_or_default()
            .total_cmp(&a.create_time.unwrap_or_default())
    });
    running.sort_by(|a, b| {
        b.create_time
            .unwrap_or_default()
            .total_cmp(&a.create_time.unwrap_or_default())
    });
    if shells.is_empty() && running.is_empty() {
        None
    } else {
        Some(TerminalContext {
            source: "process_tree".to_string(),
            shells,
            running,
        })
    }
}

fn descendants_of(system: &System, root: Pid) -> Vec<Pid> {
    let mut by_parent: HashMap<Pid, Vec<Pid>> = HashMap::new();
    for (pid, proc_) in system.processes() {
        if let Some(parent) = proc_.parent() {
            by_parent.entry(parent).or_default().push(*pid);
        }
    }
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    let mut stack = vec![root];
    while let Some(parent) = stack.pop() {
        let Some(children) = by_parent.get(&parent) else {
            continue;
        };
        for child in children {
            if seen.insert(*child) {
                out.push(*child);
                stack.push(*child);
            }
        }
    }
    out
}

fn basename_cross_platform(path: &str) -> String {
    path.rsplit(['/', '\\']).next().unwrap_or(path).to_string()
}

fn basename_without_ext(path: &str) -> String {
    path.rsplit_once('.')
        .map(|(stem, _)| stem.to_string())
        .unwrap_or_else(|| path.to_string())
}
