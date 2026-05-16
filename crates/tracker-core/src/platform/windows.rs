use super::{collect_title_and_cwd_documents, process_info};
use crate::models::{DocumentSource, WindowGeometry, WindowInfo};
use crate::tools::{dedupe_documents, document_from_existing_path};
use anyhow::Context;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use windows::Win32::Foundation::{HWND, RECT};
use windows::Win32::UI::WindowsAndMessaging::{
    GetClassNameW, GetForegroundWindow, GetWindowRect, GetWindowTextLengthW, GetWindowTextW,
    GetWindowThreadProcessId,
};

pub async fn active_window() -> anyhow::Result<WindowInfo> {
    tokio::task::spawn_blocking(query_active_window)
        .await
        .context("join windows active window query")?
}

pub async fn enrich_platform_window_documents(mut info: WindowInfo) -> WindowInfo {
    let hwnd_id = info
        .window_id
        .as_deref()
        .and_then(|id| id.parse::<isize>().ok())
        .unwrap_or_default();
    if hwnd_id == 0 {
        return info;
    }
    let fallback = info.clone();
    tokio::task::spawn_blocking(move || {
        let hwnd = HWND(hwnd_id as *mut std::ffi::c_void);
        collect_windows_document_sources(&mut info, hwnd);
        info
    })
    .await
    .unwrap_or(fallback)
}

fn query_active_window() -> anyhow::Result<WindowInfo> {
    let mut info = WindowInfo {
        platform: "win32".to_string(),
        ..WindowInfo::default()
    };
    let hwnd = unsafe { GetForegroundWindow() };
    if is_null_hwnd(hwnd) {
        info.errors.push("No foreground window".to_string());
        return Ok(info);
    }

    info.window_id = Some(hwnd_id(hwnd));
    info.extra = serde_json::json!({"hwnd_hex": hwnd_hex(hwnd)});
    info.window_title = unsafe { window_text(hwnd) };
    info.window_class = Some(unsafe { class_name(hwnd) }).filter(|s| !s.is_empty());

    let mut pid = 0u32;
    let tid = unsafe { GetWindowThreadProcessId(hwnd, Some(&mut pid)) };
    if tid != 0 {
        if let Some(obj) = info.extra.as_object_mut() {
            obj.insert("thread_id".to_string(), serde_json::json!(tid));
        }
    }

    let mut rect = RECT::default();
    let ok = unsafe { GetWindowRect(hwnd, &mut rect) }.is_ok();
    if ok {
        info.geometry = Some(WindowGeometry {
            x: rect.left,
            y: rect.top,
            width: rect.right - rect.left,
            height: rect.bottom - rect.top,
            screen_index: 0,
        });
    }

    if pid != 0 {
        info.process = process_info(pid);
        if let Some(proc_) = &info.process {
            info.app_name = proc_
                .executable
                .as_deref()
                .and_then(|p| std::path::Path::new(p).file_stem())
                .and_then(|s| s.to_str())
                .unwrap_or(&proc_.name)
                .to_string();
        }
    }

    collect_title_and_cwd_documents(&mut info);
    Ok(info)
}

fn collect_windows_document_sources(info: &mut WindowInfo, hwnd: HWND) {
    if is_office_like(info) {
        info.document_paths.extend(office_documents());
    }
    if should_scan_uia(info) {
        info.document_paths.extend(uia_documents(hwnd));
    }
    info.document_paths = dedupe_documents(std::mem::take(&mut info.document_paths));
}

fn should_scan_uia(info: &WindowInfo) -> bool {
    if is_office_like(info)
        || crate::tools::likely_document_name_from_title(&info.window_title).is_some()
    {
        return true;
    }
    let app = info.app_name.to_lowercase();
    let exe = info
        .process
        .as_ref()
        .and_then(|p| p.executable.as_deref())
        .unwrap_or_default()
        .to_lowercase();
    let name = info
        .process
        .as_ref()
        .map(|p| p.name.to_lowercase())
        .unwrap_or_default();
    let haystack = format!("{app} {exe} {name}");
    [
        "typora",
        "notepad",
        "notepad++",
        "wordpad",
        "code.exe",
        "visual studio code",
        "sublime",
        "obsidian",
        "acrobat",
        "acrord",
        "foxit",
        "sumatrapdf",
        "wps",
        "kwps",
        "ket",
        "wpp",
    ]
    .iter()
    .any(|needle| haystack.contains(needle))
}

fn is_office_like(info: &WindowInfo) -> bool {
    let app = info.app_name.to_lowercase();
    let exe = info
        .process
        .as_ref()
        .and_then(|p| p.executable.as_deref())
        .unwrap_or_default()
        .to_lowercase();
    let name = info
        .process
        .as_ref()
        .map(|p| p.name.to_lowercase())
        .unwrap_or_default();
    let haystack = format!("{app} {exe} {name}");
    [
        "winword",
        "excel",
        "powerpnt",
        "microsoft word",
        "microsoft excel",
        "powerpoint",
        "wps",
        "kwps",
        "ket",
        "wpp",
        "et.exe",
        "wpp.exe",
    ]
    .iter()
    .any(|needle| haystack.contains(needle))
}

fn office_documents() -> Vec<DocumentSource> {
    let script = r#"
$ErrorActionPreference = 'SilentlyContinue'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

function Emit-Path($source, $path) {
  if ($path) { Write-Output "$source|$path" }
}

$groups = @(
  @{ Source = 'office:word'; ProgIds = @('Word.Application', 'KWPS.Application', 'Kwps.Application', 'WPS.Application'); Active = 'ActiveDocument'; Collection = 'Documents' },
  @{ Source = 'office:excel'; ProgIds = @('Excel.Application', 'KET.Application', 'Ket.Application', 'ET.Application'); Active = 'ActiveWorkbook'; Collection = 'Workbooks' },
  @{ Source = 'office:powerpoint'; ProgIds = @('PowerPoint.Application', 'KWPP.Application', 'Kwpp.Application', 'WPP.Application'); Active = 'ActivePresentation'; Collection = 'Presentations' }
)

foreach ($group in $groups) {
  $source = [string]$group['Source']
  $activeName = [string]$group['Active']
  $collectionName = [string]$group['Collection']
  foreach ($progId in $group['ProgIds']) {
    try {
      $app = [Runtime.InteropServices.Marshal]::GetActiveObject($progId)
      if (-not $app) { continue }
      try {
        $active = $app.$activeName
        if ($active) {
          $activePath = $active.FullName
          if (-not $activePath) { $activePath = $active.Path }
          Emit-Path "$($source):active" $activePath
        }
      } catch {}
      $items = $app.$collectionName
      foreach ($item in $items) {
        try {
          $path = $item.FullName
          if (-not $path) { $path = $item.Path }
          Emit-Path $source $path
        } catch {}
      }
    } catch {}
  }
}
"#;
    run_powershell_utf8(script, Duration::from_millis(900))
        .map(|text| parse_document_lines(&text, 0.95))
        .unwrap_or_default()
}

fn uia_documents(hwnd: HWND) -> Vec<DocumentSource> {
    let hwnd_value = hwnd.0 as isize;
    let script = format!(
        r#"
$ErrorActionPreference = 'SilentlyContinue'
$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{hwnd_value})
if (-not $root) {{ exit }}
$queue = New-Object 'System.Collections.Generic.Queue[System.Windows.Automation.AutomationElement]'
$queue.Enqueue($root)
$seen = 0
while ($queue.Count -gt 0 -and $seen -lt 260) {{
  $el = $queue.Dequeue()
  $seen++
  try {{
    $name = $el.Current.Name
    if ($name) {{ Write-Output "uia:name|$name" }}
  }} catch {{}}
  try {{
    $pattern = $null
    if ($el.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {{
      $value = $pattern.Current.Value
      if ($value) {{ Write-Output "uia:value|$value" }}
    }}
  }} catch {{}}
  try {{
    $children = $el.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($child in $children) {{ $queue.Enqueue($child) }}
  }} catch {{}}
}}
"#
    );
    run_powershell_utf8(&script, Duration::from_millis(1200))
        .map(|text| parse_document_lines(&text, 0.75))
        .unwrap_or_default()
}

fn parse_document_lines(text: &str, confidence: f32) -> Vec<DocumentSource> {
    let mut out = Vec::new();
    for raw in text.lines() {
        let Some((source, value)) = raw.split_once('|') else {
            continue;
        };
        let confidence = if source.ends_with(":active") {
            0.99
        } else {
            confidence
        };
        if let Some(doc) = document_from_existing_path(value, source, confidence) {
            out.push(doc);
            continue;
        }
        for candidate in crate::tools::extract_paths_from_title(value) {
            if let Some(doc) = document_from_existing_path(&candidate, source, confidence) {
                out.push(doc);
            }
        }
    }
    out
}

fn run_powershell_utf8(script: &str, timeout: Duration) -> Option<String> {
    let mut child = Command::new("powershell.exe")
        .args([
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;

    let started = Instant::now();
    loop {
        if child.try_wait().ok().flatten().is_some() {
            let output = child.wait_with_output().ok()?;
            return Some(decode_process_output(&output.stdout));
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            return None;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn decode_process_output(bytes: &[u8]) -> String {
    if bytes.len() >= 2 {
        if bytes.starts_with(&[0xff, 0xfe]) {
            return decode_utf16le(&bytes[2..]);
        }
        if bytes.starts_with(&[0xfe, 0xff]) {
            return decode_utf16be(&bytes[2..]);
        }
        let nul_odd = bytes.iter().skip(1).step_by(2).filter(|b| **b == 0).count();
        if nul_odd > bytes.len() / 8 {
            return decode_utf16le(bytes);
        }
    }
    String::from_utf8_lossy(bytes).to_string()
}

fn decode_utf16le(bytes: &[u8]) -> String {
    let units = bytes
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect::<Vec<_>>();
    String::from_utf16_lossy(&units)
}

fn decode_utf16be(bytes: &[u8]) -> String {
    let units = bytes
        .chunks_exact(2)
        .map(|c| u16::from_be_bytes([c[0], c[1]]))
        .collect::<Vec<_>>();
    String::from_utf16_lossy(&units)
}

unsafe fn window_text(hwnd: HWND) -> String {
    let len = GetWindowTextLengthW(hwnd);
    let mut buf = vec![0u16; (len as usize).saturating_add(1).max(512)];
    let copied = GetWindowTextW(hwnd, &mut buf);
    String::from_utf16_lossy(&buf[..copied as usize])
}

unsafe fn class_name(hwnd: HWND) -> String {
    let mut buf = vec![0u16; 256];
    let copied = GetClassNameW(hwnd, &mut buf);
    String::from_utf16_lossy(&buf[..copied as usize])
}

fn is_null_hwnd(hwnd: HWND) -> bool {
    hwnd.0.is_null()
}

fn hwnd_id(hwnd: HWND) -> String {
    format!("{}", hwnd.0 as isize)
}

fn hwnd_hex(hwnd: HWND) -> String {
    format!("{:#x}", hwnd.0 as usize)
}
