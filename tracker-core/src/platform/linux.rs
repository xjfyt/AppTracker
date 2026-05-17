use super::{collect_title_and_cwd_documents, process_info};
use crate::models::{DocumentCategory, DocumentSource, WindowGeometry, WindowInfo};
use crate::tools::{
    dedupe_documents, document_from_existing_path, has_fd_scan_extension,
    likely_document_name_from_title,
};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub async fn active_window() -> anyhow::Result<WindowInfo> {
    tokio::task::spawn_blocking(query_active_window).await?
}

pub async fn enrich_platform_window_documents(mut info: WindowInfo) -> WindowInfo {
    let Some(pid) = info.process.as_ref().map(|p| p.pid) else {
        return info;
    };
    let title = info.window_title.clone();
    let bundle = info
        .process
        .as_ref()
        .and_then(|p| p.executable.clone())
        .unwrap_or_default();

    // /proc/fd + cmdline lookups are sync; do them on a blocking thread.
    let fd_docs = tokio::task::spawn_blocking(move || collect_documents(pid, &bundle, &title))
        .await
        .unwrap_or_default();
    info.document_paths.extend(fd_docs);

    // AT-SPI is dbus-based and lives in the tokio runtime; cheap to await
    // here. The function itself short-circuits to None within ~700ms if
    // accessibility isn't running.
    let atspi_docs = crate::integrations::linux_dbus::document_url_for(&info).await;
    info.document_paths.extend(atspi_docs);

    info.document_paths = dedupe_documents(std::mem::take(&mut info.document_paths));
    info
}

fn collect_documents(pid: u32, exe: &str, title: &str) -> Vec<DocumentSource> {
    let mut docs = Vec::new();
    // /proc/PID/fd — Linux's native equivalent of lsof; no extra binary needed
    docs.extend(proc_fd_documents(pid, title));
    // App-specific hints (libreoffice via /proc/PID/cmdline arguments, etc.)
    docs.extend(per_executable_documents(pid, exe));
    docs
}

/// Read /proc/PID/fd/<n> symlinks and surface REG files matching either a known
/// document extension or the basename embedded in the window title.
fn proc_fd_documents(pid: u32, title: &str) -> Vec<DocumentSource> {
    let dir = PathBuf::from(format!("/proc/{pid}/fd"));
    let Ok(entries) = std::fs::read_dir(&dir) else {
        return Vec::new();
    };
    let title_basenames: std::collections::HashSet<String> = std::iter::once(title.to_string())
        .filter_map(|t| {
            let trimmed = t.trim().trim_matches('"');
            if trimmed.is_empty() {
                return None;
            }
            likely_document_name_from_title(trimmed).or_else(|| Some(trimmed.to_string()))
        })
        .collect();

    let mut docs = Vec::new();
    let mut count = 0usize;
    for entry in entries.flatten() {
        count += 1;
        if count > 4000 {
            tracing::warn!(pid, "proc_fd_documents: scan cap reached (4000)");
            break;
        }
        let path = entry.path();
        let Ok(target) = std::fs::read_link(&path) else {
            continue;
        };
        let target_str = target.to_string_lossy().to_string();
        // Skip non-file fds: sockets, pipes, anon_inodes, /dev/*, /proc/*
        if !target_str.starts_with('/')
            || target_str.starts_with("/dev/")
            || target_str.starts_with("/proc/")
            || target_str.starts_with("/sys/")
            || target_str.contains("(deleted)")
        {
            continue;
        }
        let basename = std::path::Path::new(&target_str)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default();
        let matches_title = !basename.is_empty() && title_basenames.contains(basename);
        if !matches_title && !has_fd_scan_extension(&target_str) {
            continue;
        }
        let (source, confidence) = if matches_title {
            ("fd:title_match", 0.92f32)
        } else {
            ("fd", 0.45)
        };
        if let Some(doc) =
            document_from_existing_path(&target_str, source, confidence, DocumentCategory::User)
        {
            docs.push(doc);
        }
    }
    docs
}

/// Apps whose document path lives in their argv (LibreOffice opens with the
/// file as first non-flag argument, similar for many CLI-launched editors).
fn per_executable_documents(pid: u32, exe: &str) -> Vec<DocumentSource> {
    let exe_lower = exe.to_lowercase();
    let is_libreoffice = exe_lower.contains("soffice")
        || exe_lower.contains("libreoffice")
        || exe_lower.contains("oosplash");
    if !is_libreoffice {
        return Vec::new();
    }
    let cmdline_path = PathBuf::from(format!("/proc/{pid}/cmdline"));
    let Ok(bytes) = std::fs::read(&cmdline_path) else {
        return Vec::new();
    };
    let mut docs = Vec::new();
    for arg in bytes.split(|b| *b == 0) {
        if arg.is_empty() {
            continue;
        }
        let s = String::from_utf8_lossy(arg);
        if s.starts_with('-') {
            continue;
        }
        if let Some(doc) =
            document_from_existing_path(&s, "libreoffice:argv", 0.85, DocumentCategory::User)
        {
            docs.push(doc);
        }
    }
    docs
}

fn query_active_window() -> anyhow::Result<WindowInfo> {
    let mut info = WindowInfo {
        platform: "linux".to_string(),
        ..WindowInfo::default()
    };
    if std::env::var("XDG_SESSION_TYPE").unwrap_or_default() == "wayland" {
        info.errors
            .push("Running under Wayland; generic active-window capture is limited".to_string());
    }

    let window_id = active_window_id().or_else(active_window_id_from_xprop);
    let Some(window_id) = window_id else {
        info.errors
            .push("No active X11 window; install xdotool/xprop or use X11 session".to_string());
        return Ok(info);
    };
    info.window_id = Some(window_id.clone());

    if let Some(props) = cmd_output("xprop", &["-id", &window_id]) {
        info.window_title = parse_xprop_string(&props, "_NET_WM_NAME")
            .or_else(|| parse_xprop_string(&props, "WM_NAME"))
            .unwrap_or_default();
        info.window_class = parse_xprop_string(&props, "WM_CLASS");
        if let Some(pid) = parse_xprop_u32(&props, "_NET_WM_PID") {
            info.process = process_info(pid);
            if let Some(proc_) = &info.process {
                info.app_name = proc_.name.clone();
            }
        }
    }

    if let Some(xwin) = cmd_output("xwininfo", &["-id", &window_id]) {
        info.geometry = parse_xwininfo_geometry(&xwin);
    }

    collect_title_and_cwd_documents(&mut info);
    Ok(info)
}

fn active_window_id() -> Option<String> {
    cmd_output("xdotool", &["getactivewindow"]).map(|s| s.trim().to_string())
}

fn active_window_id_from_xprop() -> Option<String> {
    let text = cmd_output("xprop", &["-root", "_NET_ACTIVE_WINDOW"])?;
    let id = text.split_whitespace().last()?.trim_end_matches(',');
    if id == "0x0" {
        None
    } else {
        Some(id.to_string())
    }
}

fn cmd_output(cmd: &str, args: &[&str]) -> Option<String> {
    let mut child = Command::new(cmd)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let timeout = Duration::from_millis(700);
    let started = Instant::now();
    loop {
        if child.try_wait().ok().flatten().is_some() {
            let out = child.wait_with_output().ok()?;
            if !out.status.success() {
                return None;
            }
            return Some(String::from_utf8_lossy(&out.stdout).to_string());
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            tracing::warn!(command = cmd, "linux window helper command timed out");
            return None;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}

fn parse_xprop_string(text: &str, key: &str) -> Option<String> {
    for line in text.lines() {
        if !line.starts_with(key) {
            continue;
        }
        if key == "WM_CLASS" {
            let values = line
                .split('"')
                .filter(|s| !s.is_empty() && *s != ", ")
                .collect::<Vec<_>>();
            return values.last().map(|s| s.to_string());
        }
        let value = line.split_once(" = ")?.1.trim();
        return Some(value.trim_matches('"').to_string());
    }
    None
}

fn parse_xprop_u32(text: &str, key: &str) -> Option<u32> {
    for line in text.lines() {
        if line.starts_with(key) {
            return line.split_once(" = ")?.1.trim().parse().ok();
        }
    }
    None
}

fn parse_xwininfo_geometry(text: &str) -> Option<WindowGeometry> {
    let mut x = None;
    let mut y = None;
    let mut width = None;
    let mut height = None;
    for line in text.lines() {
        let line = line.trim();
        if let Some(v) = line.strip_prefix("Absolute upper-left X:") {
            x = v.trim().parse::<i32>().ok();
        } else if let Some(v) = line.strip_prefix("Absolute upper-left Y:") {
            y = v.trim().parse::<i32>().ok();
        } else if let Some(v) = line.strip_prefix("Width:") {
            width = v.trim().parse::<i32>().ok();
        } else if let Some(v) = line.strip_prefix("Height:") {
            height = v.trim().parse::<i32>().ok();
        }
    }
    Some(WindowGeometry {
        x: x?,
        y: y?,
        width: width?,
        height: height?,
        screen_index: 0,
    })
}
