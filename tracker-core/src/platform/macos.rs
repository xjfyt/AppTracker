use super::{collect_title_and_cwd_documents, process_info};
use crate::models::{WindowGeometry, WindowInfo};
use std::process::Command;

pub async fn active_window() -> anyhow::Result<WindowInfo> {
    tokio::task::spawn_blocking(query_active_window).await?
}

fn query_active_window() -> anyhow::Result<WindowInfo> {
    let mut info = WindowInfo {
        platform: "darwin".to_string(),
        ..WindowInfo::default()
    };
    let script = r#"
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    set pidVal to unix id of frontApp
    set bundleVal to ""
    try
        set bundleVal to bundle identifier of frontApp
    end try
    set titleVal to ""
    set xVal to 0
    set yVal to 0
    set wVal to 0
    set hVal to 0
    try
        set winRef to front window of frontApp
        set titleVal to name of winRef
        set posVal to position of winRef
        set sizeVal to size of winRef
        set xVal to item 1 of posVal
        set yVal to item 2 of posVal
        set wVal to item 1 of sizeVal
        set hVal to item 2 of sizeVal
    end try
    return appName & tab & pidVal & tab & bundleVal & tab & titleVal & tab & xVal & tab & yVal & tab & wVal & tab & hVal
end tell
"#;
    let output = Command::new("osascript").arg("-e").arg(script).output();
    let output = match output {
        Ok(out) => out,
        Err(exc) => {
            info.errors.push(format!("osascript unavailable: {exc}"));
            return Ok(info);
        }
    };
    if !output.status.success() {
        info.errors.push(format!(
            "osascript failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ));
        return Ok(info);
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let parts = text.trim_end().split('\t').collect::<Vec<_>>();
    info.app_name = parts.get(0).copied().unwrap_or_default().to_string();
    let pid = parts.get(1).and_then(|s| s.parse::<u32>().ok());
    info.app_bundle_id = parts
        .get(2)
        .map(|s| s.to_string())
        .filter(|s| !s.is_empty());
    info.window_title = parts.get(3).copied().unwrap_or_default().to_string();
    if let (Some(x), Some(y), Some(w), Some(h)) = (
        parts.get(4).and_then(|s| s.parse::<i32>().ok()),
        parts.get(5).and_then(|s| s.parse::<i32>().ok()),
        parts.get(6).and_then(|s| s.parse::<i32>().ok()),
        parts.get(7).and_then(|s| s.parse::<i32>().ok()),
    ) {
        if w > 0 && h > 0 {
            info.geometry = Some(WindowGeometry {
                x,
                y,
                width: w,
                height: h,
                screen_index: 0,
            });
        }
    }
    if let Some(pid) = pid {
        info.process = process_info(pid);
    }
    collect_title_and_cwd_documents(&mut info);
    Ok(info)
}
