use crate::models::{FileManagerState, FileManagerWindow, WindowInfo};
#[cfg(any(target_os = "windows", target_os = "macos"))]
use std::process::{Command, Stdio};
#[cfg(any(target_os = "windows", target_os = "macos"))]
use std::time::{Duration, Instant};

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
const WINDOWS_EXPLORER_SELECTION_CAP: usize = 50;

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
    // Win11 同窗口多 TAB 共享 HWND，光看 HWND 没法分辨真正激活的 TAB。
    // 把前台窗口标题（通常就是激活 TAB 的文件夹叶子名）传给 PS，
    // PS 端按"folder leaf == title leaf"在同 HWND 下挑一个 TAB 标 W*。
    let active_title_escaped = info.window_title.replace('\'', "''");
    let cap = WINDOWS_EXPLORER_SELECTION_CAP;
    tokio::task::spawn_blocking(move || {
        let script = format!(
            r#"
$ErrorActionPreference = 'SilentlyContinue'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$active = {active_hwnd}
$activeTitle = '{active_title_escaped}'
$cap = {cap}

# 截取标题左侧到第一个分隔符（' - ', ' | ', '–', '—'）之前作为
# 激活 TAB 的"叶子名"。Win11 Explorer 默认标题是裸文件夹名，但配合
# 一些工具会出现 "node_modules - 文件资源管理器" 之类。
$titleLeaf = $activeTitle
foreach ($sep in @(' - ', ' | ', ' – ', ' — ')) {{
  $idx = $titleLeaf.IndexOf($sep)
  if ($idx -gt 0) {{ $titleLeaf = $titleLeaf.Substring(0, $idx) }}
}}
$titleLeaf = $titleLeaf.Trim()

$shell = New-Object -ComObject Shell.Application
$entries = New-Object 'System.Collections.Generic.List[object]'
foreach ($w in $shell.Windows()) {{
  try {{
    if (-not ($w.FullName -like '*explorer.exe')) {{ continue }}
    $hwnd = [int64]$w.HWND
    $url = [string]$w.LocationURL
    if (-not $url.StartsWith('file:')) {{ continue }}
    $uri = [System.Uri]$url
    $folder = [System.Uri]::UnescapeDataString($uri.LocalPath)
    $entries.Add([pscustomobject]@{{ Hwnd = $hwnd; Folder = $folder; W = $w }})
  }} catch {{}}
}}

# 在共享 HWND=$active 的多个 TAB 里挑唯一的"真激活"：
#   1) folder leaf 与标题 leaf 全等
#   2) 否则取第一个
$activeIdx = -1
$candidates = @()
for ($i = 0; $i -lt $entries.Count; $i++) {{
  if ($entries[$i].Hwnd -eq $active) {{ $candidates += $i }}
}}
if ($candidates.Count -gt 0) {{
  if ($titleLeaf) {{
    foreach ($i in $candidates) {{
      $leaf = Split-Path -Leaf $entries[$i].Folder
      if ($leaf -and ($leaf -eq $titleLeaf)) {{ $activeIdx = $i; break }}
    }}
  }}
  if ($activeIdx -lt 0) {{ $activeIdx = $candidates[0] }}
}}

for ($i = 0; $i -lt $entries.Count; $i++) {{
  $e = $entries[$i]
  $flag = if ($i -eq $activeIdx) {{ 'W*' }} else {{ 'W' }}
  Write-Output "$flag|$($e.Hwnd)|$($e.Folder)"
  try {{
    $sel = $e.W.Document.SelectedItems()
    $total = 0
    try {{ $total = [int]$sel.Count }} catch {{ $total = 0 }}
    $emitted = 0
    foreach ($item in $sel) {{
      if ($emitted -ge $cap) {{ break }}
      try {{
        $p = $item.Path
        if ($p) {{ Write-Output "S|$($e.Hwnd)|$p"; $emitted++ }}
      }} catch {{}}
    }}
    if ($total -gt $emitted) {{
      Write-Output "T|$($e.Hwnd)|$total|$emitted"
    }}
  }} catch {{}}
}}
"#
        );
        let text = run_powershell_utf8(&script, Duration::from_millis(2500))?;
        parse_windows_explorer(&text)
    })
    .await
    .ok()
    .flatten()
}

#[cfg(target_os = "windows")]
fn run_powershell_utf8(script: &str, timeout: Duration) -> Option<String> {
    use std::os::windows::process::CommandExt;
    // CREATE_NO_WINDOW = 0x08000000. Release 走 GUI subsystem，没有父控制台，
    // 默认会给子进程分配一个新黑框；前台窗口每变一次都要 spawn 一次 PowerShell，
    // 不加这个 flag 就会出现"切应用就闪终端"的现象。
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let mut child = Command::new("powershell.exe")
        .args([
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ])
        .creation_flags(CREATE_NO_WINDOW)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;

    let started = Instant::now();
    loop {
        if child.try_wait().ok().flatten().is_some() {
            let output = child.wait_with_output().ok()?;
            if !output.status.success() {
                return None;
            }
            return Some(decode_process_output(&output.stdout));
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            tracing::warn!(
                timeout_ms = timeout.as_millis() as u64,
                "windows explorer COM query timed out",
            );
            return None;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
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
        } else if let Some(rest) = line.strip_prefix("S|") {
            // S|<hwnd>|<path>
            let mut parts = rest.splitn(2, '|');
            let hwnd = parts.next().unwrap_or_default();
            let selected = parts.next().unwrap_or_default().to_string();
            if selected.is_empty() {
                continue;
            }
            if let Some(window) = windows
                .iter_mut()
                .find(|w| w.hwnd_or_id.as_deref() == Some(hwnd))
            {
                window.selected_items.push(selected);
            }
        }
        // 其它 sentinel（如 T|hwnd|total|emitted）忽略：UI 当前不展示截断标记，
        // 选中项已自然停在 cap 以内。这里只是为了将来想透出"已截断"提示时
        // 不用再改 PS 端。
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
        let text = run_osascript(script, Duration::from_millis(1200))?;
        parse_finder(&text)
    })
    .await
    .ok()
    .flatten()
}

#[cfg(target_os = "macos")]
fn run_osascript(script: &str, timeout: Duration) -> Option<String> {
    let mut child = Command::new("osascript")
        .arg("-e")
        .arg(script)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let started = Instant::now();
    loop {
        if child.try_wait().ok().flatten().is_some() {
            let output = child.wait_with_output().ok()?;
            if !output.status.success() {
                return None;
            }
            return Some(String::from_utf8_lossy(&output.stdout).to_string());
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            tracing::warn!(
                timeout_ms = timeout.as_millis() as u64,
                "finder AppleScript query timed out",
            );
            return None;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
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
const LINUX_FILE_MANAGER_HINTS: &[&str] = &[
    "nautilus",
    "org.gnome.nautilus",
    "gnome-files",
    "dolphin",
    "org.kde.dolphin",
    "nemo",
    "caja",
    "thunar",
    "pcmanfm",
    "pcmanfm-qt",
    "krusader",
    "doublecmd",
    "nnn",
    "ranger",
    "spacefm",
    "files",
];

#[cfg(target_os = "linux")]
fn linux_detect_file_manager(info: &WindowInfo) -> bool {
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
    let name = info
        .process
        .as_ref()
        .map(|p| p.name.to_lowercase())
        .unwrap_or_default();
    let app = info.app_name.to_lowercase();
    let haystack = format!("{exe} {class} {name} {app}");
    LINUX_FILE_MANAGER_HINTS
        .iter()
        .any(|hint| haystack.contains(hint))
}

#[cfg(target_os = "linux")]
async fn linux_file_manager(info: &WindowInfo) -> Option<FileManagerState> {
    if !linux_detect_file_manager(info) {
        return None;
    }
    // 1) Try DBus (Nautilus / Dolphin / Nemo / Caja expose org.freedesktop.FileManager1)
    //    and zbus call. Returns folder + selection in one go.
    if let Some(state) = crate::integrations::linux_dbus::file_manager_state(info).await {
        return Some(state);
    }
    // 2) Fallback: cwd + title parsing (the path many file managers stuff into
    //    the window title — "Documents - Files", "Documents — Dolphin", etc.).
    let folder = info
        .process
        .as_ref()
        .and_then(|p| p.cwd.clone())
        .filter(|p| std::path::Path::new(p).is_dir())
        .or_else(|| linux_folder_from_title(&info.window_title))?;
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

/// Parse a folder path out of a file-manager window title. File managers
/// usually put the current folder name (not full path) in the title, but some
/// (Nautilus with "Always show paths") put the absolute path or "~/Documents".
#[cfg(target_os = "linux")]
fn linux_folder_from_title(title: &str) -> Option<String> {
    let candidate = title
        .split(|ch: char| ch == '\u{2014}' || ch == '\u{2013}' || ch == '-')
        .next()?
        .trim();
    if candidate.is_empty() {
        return None;
    }
    // Direct path / ~/... / relative-to-home
    let expanded = crate::tools::expand_user(candidate);
    if std::path::Path::new(&expanded).is_dir() {
        return Some(expanded);
    }
    // Bare folder name — search common roots
    let home = dirs::home_dir()?;
    for root in [
        home.clone(),
        home.join("Desktop"),
        home.join("Documents"),
        home.join("Downloads"),
        home.join("Pictures"),
        home.join("Videos"),
        home.join("Music"),
    ] {
        let p = root.join(candidate);
        if p.is_dir() {
            return Some(p.to_string_lossy().to_string());
        }
    }
    None
}
