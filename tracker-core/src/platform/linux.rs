use super::{collect_title_and_cwd_documents, process_info};
use crate::models::{WindowGeometry, WindowInfo};
use std::process::Command;

pub async fn active_window() -> anyhow::Result<WindowInfo> {
    tokio::task::spawn_blocking(query_active_window).await?
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
    let out = Command::new(cmd).args(args).output().ok()?;
    if !out.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&out.stdout).to_string())
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
