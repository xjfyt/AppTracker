use crate::models::{FileManagerState, FileManagerWindow, WindowInfo};
#[cfg(any(target_os = "windows", target_os = "macos"))]
use std::process::Command;

pub async fn query(info: &WindowInfo) -> Option<FileManagerState> {
    #[cfg(target_os = "windows")]
    {
        return windows_explorer(info).await;
    }
    #[cfg(target_os = "macos")]
    {
        return macos_finder(info).await;
    }
    #[cfg(target_os = "linux")]
    {
        return linux_file_manager(info).await;
    }
    #[allow(unreachable_code)]
    None
}

#[cfg(target_os = "windows")]
async fn windows_explorer(info: &WindowInfo) -> Option<FileManagerState> {
    let class = info.window_class.as_deref().unwrap_or_default();
    let exe = info
        .process
        .as_ref()
        .and_then(|p| p.executable.as_deref())
        .unwrap_or_default()
        .to_lowercase();
    if class != "CabinetWClass" && !exe.ends_with("explorer.exe") {
        return None;
    }
    let active_hwnd = info
        .window_id
        .as_deref()
        .and_then(|s| s.parse::<i64>().ok())
        .unwrap_or_default();
    tokio::task::spawn_blocking(move || {
        let script = format!(
            r#"
$ErrorActionPreference = 'SilentlyContinue'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$active = {active_hwnd}
$shell = New-Object -ComObject Shell.Application
foreach ($w in $shell.Windows()) {{
  try {{
    if (-not ($w.FullName -like '*explorer.exe')) {{ continue }}
    $hwnd = [int64]$w.HWND
    $url = [string]$w.LocationURL
    if (-not $url.StartsWith('file:')) {{ continue }}
    $uri = [System.Uri]$url
    $folder = [System.Uri]::UnescapeDataString($uri.LocalPath)
    $flag = if ($hwnd -eq $active) {{ 'W*' }} else {{ 'W' }}
    Write-Output "$flag|$hwnd|$folder"
    try {{
      foreach ($item in $w.Document.SelectedItems()) {{
        if ($item.Path) {{ Write-Output "S|$hwnd|$($item.Path)" }}
      }}
    }} catch {{}}
  }} catch {{}}
}}
"#
        );
        let out = Command::new("powershell.exe")
            .args([
                "-NoLogo",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                &script,
            ])
            .output()
            .ok()?;
        if !out.status.success() {
            return None;
        }
        parse_windows_explorer(&decode_process_output(&out.stdout))
    })
    .await
    .ok()
    .flatten()
}

#[cfg(target_os = "windows")]
fn decode_process_output(bytes: &[u8]) -> String {
    if bytes.starts_with(&[0xff, 0xfe]) {
        let units = bytes[2..]
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .collect::<Vec<_>>();
        return String::from_utf16_lossy(&units);
    }
    if bytes.len() > 2 {
        let nul_odd = bytes.iter().skip(1).step_by(2).filter(|b| **b == 0).count();
        if nul_odd > bytes.len() / 8 {
            let units = bytes
                .chunks_exact(2)
                .map(|c| u16::from_le_bytes([c[0], c[1]]))
                .collect::<Vec<_>>();
            return String::from_utf16_lossy(&units);
        }
    }
    String::from_utf8_lossy(bytes).to_string()
}

#[cfg(target_os = "windows")]
fn parse_windows_explorer(text: &str) -> Option<FileManagerState> {
    let mut windows = Vec::<FileManagerWindow>::new();
    for line in text.lines() {
        if line.starts_with("W|") || line.starts_with("W*|") {
            let active = line.starts_with("W*|");
            let mut parts = line.splitn(3, '|');
            let _ = parts.next();
            let hwnd = parts.next()?.to_string();
            let folder = parts.next()?.to_string();
            windows.push(FileManagerWindow {
                folder,
                selected_items: Vec::new(),
                hwnd_or_id: Some(hwnd),
                is_active: active,
            });
        } else if line.starts_with("S|") {
            let mut parts = line.splitn(3, '|');
            let _ = parts.next();
            let hwnd = parts.next().unwrap_or_default();
            let selected = parts.next().unwrap_or_default().to_string();
            if let Some(window) = windows
                .iter_mut()
                .find(|w| w.hwnd_or_id.as_deref() == Some(hwnd))
            {
                window.selected_items.push(selected);
            }
        }
    }
    if windows.is_empty() {
        None
    } else {
        Some(FileManagerState {
            source: "explorer_com_powershell".to_string(),
            windows,
        })
    }
}

#[cfg(target_os = "macos")]
async fn macos_finder(info: &WindowInfo) -> Option<FileManagerState> {
    if info.app_bundle_id.as_deref() != Some("com.apple.finder") && info.app_name != "Finder" {
        return None;
    }
    tokio::task::spawn_blocking(|| {
        // Important: `repeat with w in windows` inside `tell application "Finder"`
        // is silently reinterpreted as iterating over the items in the front window
        // (a long-standing Finder/AS quirk). We MUST materialize the list first via
        // `set wList to Finder windows`. `Finder windows` (not just `windows`) also
        // excludes the desktop pseudo-window so we don't get a weird desktop entry.
        let script = r#"
tell application "Finder"
    set outText to ""
    try
        set sList to (get selection)
        repeat with itemRef in sList
            try
                set outText to outText & "S|" & (POSIX path of (itemRef as alias)) & linefeed
            end try
        end repeat
    end try
    set frontWinId to -1
    try
        set frontWinId to id of front Finder window
    end try
    try
        set wList to Finder windows
        repeat with w in wList
            try
                set targetPath to POSIX path of (target of w as alias)
                set wid to id of w
                if wid is frontWinId then
                    set outText to outText & "W*|" & wid & "|" & targetPath & linefeed
                else
                    set outText to outText & "W|" & wid & "|" & targetPath & linefeed
                end if
            end try
        end repeat
    end try
    -- Desktop fallback: no Finder windows open, but user is interacting with
    -- icons on the desktop -> surface ~/Desktop as the active folder.
    if outText is "" then
        try
            set deskPath to POSIX path of (desktop as alias)
            set outText to outText & "W*|desktop|" & deskPath & linefeed
        end try
    end if
    return outText
end tell
"#;
        let out = Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .ok()?;
        if !out.status.success() {
            return None;
        }
        parse_finder(&String::from_utf8_lossy(&out.stdout))
    })
    .await
    .ok()
    .flatten()
}

#[cfg(target_os = "macos")]
fn parse_finder(text: &str) -> Option<FileManagerState> {
    let mut selected = Vec::new();
    let mut windows = Vec::<FileManagerWindow>::new();
    for line in text.lines() {
        if let Some(path) = line.strip_prefix("S|") {
            selected.push(path.trim_end_matches('/').to_string());
        } else if line.starts_with("W|") || line.starts_with("W*|") {
            let active = line.starts_with("W*|");
            let mut parts = line.splitn(3, '|');
            let _ = parts.next();
            let id = parts.next()?.to_string();
            let folder = parts.next()?.trim_end_matches('/').to_string();
            windows.push(FileManagerWindow {
                folder,
                selected_items: Vec::new(),
                hwnd_or_id: Some(id),
                is_active: active,
            });
        }
    }
    if let Some(active) = windows.iter_mut().find(|w| w.is_active) {
        active.selected_items = selected;
    }
    if windows.is_empty() {
        None
    } else {
        Some(FileManagerState {
            source: "finder_applescript".to_string(),
            windows,
        })
    }
}

#[cfg(target_os = "linux")]
async fn linux_file_manager(info: &WindowInfo) -> Option<FileManagerState> {
    let exe = info
        .process
        .as_ref()
        .and_then(|p| p.executable.as_deref())
        .unwrap_or_default()
        .to_lowercase();
    let class = info
        .window_class
        .as_deref()
        .unwrap_or_default()
        .to_lowercase();
    let is_file_manager = exe.contains("nautilus")
        || exe.contains("dolphin")
        || class.contains("nautilus")
        || class.contains("dolphin");
    if !is_file_manager {
        return None;
    }
    let folder = info
        .process
        .as_ref()
        .and_then(|p| p.cwd.clone())
        .filter(|p| std::path::Path::new(p).is_dir())
        .or_else(|| {
            let title = info
                .window_title
                .split(|ch| ch == '\u{2014}' || ch == '\u{2013}')
                .next()?
                .trim();
            if std::path::Path::new(title).is_dir() {
                Some(title.to_string())
            } else {
                None
            }
        })?;
    Some(FileManagerState {
        source: "linux_cwd_title".to_string(),
        windows: vec![FileManagerWindow {
            folder,
            selected_items: Vec::new(),
            hwnd_or_id: info.window_id.clone(),
            is_active: true,
        }],
    })
}
