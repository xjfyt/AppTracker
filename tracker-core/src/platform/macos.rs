use super::{collect_title_and_cwd_documents, process_info};
use crate::models::{DocumentCategory, DocumentSource, WindowGeometry, WindowInfo};
use crate::tools::{dedupe_documents, document_from_existing_path};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub async fn active_window() -> anyhow::Result<WindowInfo> {
    tokio::task::spawn_blocking(query_active_window).await?
}

pub async fn enrich_platform_window_documents(mut info: WindowInfo) -> WindowInfo {
    let Some(pid) = info.process.as_ref().map(|p| p.pid) else {
        return info;
    };
    let bundle = info.app_bundle_id.clone();
    let title = info.window_title.clone();
    let extras =
        tokio::task::spawn_blocking(move || collect_documents(pid, bundle.as_deref(), &title))
            .await
            .unwrap_or_default();
    info.document_paths.extend(extras);
    info.document_paths = dedupe_documents(std::mem::take(&mut info.document_paths));
    info
}

fn collect_documents(pid: u32, bundle: Option<&str>, title: &str) -> Vec<DocumentSource> {
    let mut docs = Vec::new();
    docs.extend(ax_documents_for_pid(pid));
    let mut title_hints: Vec<String> = Vec::new();
    if !title.trim().is_empty() {
        title_hints.push(title.to_string());
    }
    if let Some(b) = bundle {
        docs.extend(per_bundle_documents(b));
        title_hints.extend(bundle_title_hints(b));
    }
    docs.extend(lsof_documents(pid, &title_hints));
    docs
}

/// For apps whose windows aren't visible to System Events (Electron, custom-rendered),
/// query their own AppleScript dictionary for the window list and feed those names as
/// title hints for lsof matching.
fn bundle_title_hints(bundle: &str) -> Vec<String> {
    let script = match bundle {
        "abnerworks.Typora" => TYPORA_WINDOW_NAMES_SCRIPT,
        _ => return Vec::new(),
    };
    let text = run_osascript(script, Duration::from_millis(600)).unwrap_or_default();
    text.lines()
        .map(|line| line.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

const TYPORA_WINDOW_NAMES_SCRIPT: &str = r#"
try
    tell application id "abnerworks.Typora"
        set out to ""
        repeat with i from 1 to (count of windows)
            try
                set wn to name of window i
                if wn is not missing value then set out to out & (wn as text) & linefeed
            end try
        end repeat
        return out
    end tell
end try
return ""
"#;

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

// ---------- Generic AX (works for native Cocoa apps without app-specific dict) ----------

fn ax_documents_for_pid(pid: u32) -> Vec<DocumentSource> {
    let script = format!(
        r#"
tell application "System Events"
    set outText to ""
    try
        set proc to first process whose unix id is {pid}
    on error
        return ""
    end try
    try
        set win to front window of proc
        try
            set v to value of attribute "AXDocument" of win
            if v is not missing value then
                set vText to v as text
                if vText is not "" then set outText to outText & "ax:doc|" & vText & linefeed
            end if
        end try
        try
            set v to value of attribute "AXURL" of win
            if v is not missing value then
                set vText to v as text
                if vText is not "" then set outText to outText & "ax:url|" & vText & linefeed
            end if
        end try
    end try
    return outText
end tell
"#
    );
    let text = run_osascript(&script, Duration::from_millis(900)).unwrap_or_default();
    parse_document_lines(&text, 0.9)
}

// ---------- App-specific AppleScript (mirrors Windows COM path) ----------

fn per_bundle_documents(bundle: &str) -> Vec<DocumentSource> {
    let (script, source_tag, confidence) = match bundle {
        // Microsoft Office for Mac
        "com.microsoft.Word" => (OFFICE_WORD_SCRIPT, "office:word:active", 0.99),
        "com.microsoft.Excel" => (OFFICE_EXCEL_SCRIPT, "office:excel:active", 0.99),
        "com.microsoft.Powerpoint" => (OFFICE_PPT_SCRIPT, "office:ppt:active", 0.99),
        // Browsers (URL goes through document_from_existing_path → file:// resolves to a path;
        // http(s) currently get dropped because they're not on disk — that's fine for now).
        "com.google.Chrome" | "com.google.Chrome.canary" => (CHROME_SCRIPT, "browser:chrome", 0.9),
        "company.thebrowser.Browser" => (ARC_SCRIPT, "browser:arc", 0.9),
        "com.brave.Browser" => (BRAVE_SCRIPT, "browser:brave", 0.9),
        "com.microsoft.edgemac" | "com.microsoft.edgemac.beta" | "com.microsoft.edgemac.dev" => {
            (EDGE_SCRIPT, "browser:edge", 0.9)
        }
        "com.apple.Safari" | "com.apple.SafariTechnologyPreview" => {
            (SAFARI_SCRIPT, "browser:safari", 0.9)
        }
        // Editors with AppleScript dicts
        "com.sublimetext.4" | "com.sublimetext.3" | "com.sublimetext" => {
            (SUBLIME_SCRIPT, "editor:sublime", 0.95)
        }
        _ => return Vec::new(),
    };
    let text = run_osascript(script, Duration::from_millis(900)).unwrap_or_default();
    parse_lines_with_tag(&text, source_tag, confidence)
}

const OFFICE_WORD_SCRIPT: &str = r#"
try
    tell application id "com.microsoft.Word"
        if (count of documents) is 0 then return ""
        set out to ""
        try
            set p to full name of active document
            if p is not "" then set out to out & p & linefeed
        end try
        repeat with d in documents
            try
                set p to full name of d
                if p is not "" then set out to out & p & linefeed
            end try
        end repeat
        return out
    end tell
end try
return ""
"#;

const OFFICE_EXCEL_SCRIPT: &str = r#"
try
    tell application id "com.microsoft.Excel"
        if (count of workbooks) is 0 then return ""
        set out to ""
        try
            set p to full name of active workbook
            if p is not "" then set out to out & p & linefeed
        end try
        repeat with wb in workbooks
            try
                set p to full name of wb
                if p is not "" then set out to out & p & linefeed
            end try
        end repeat
        return out
    end tell
end try
return ""
"#;

const OFFICE_PPT_SCRIPT: &str = r#"
try
    tell application id "com.microsoft.Powerpoint"
        if (count of presentations) is 0 then return ""
        set out to ""
        try
            set p to full name of active presentation
            if p is not "" then set out to out & p & linefeed
        end try
        repeat with pr in presentations
            try
                set p to full name of pr
                if p is not "" then set out to out & p & linefeed
            end try
        end repeat
        return out
    end tell
end try
return ""
"#;

const CHROME_SCRIPT: &str = r#"
try
    tell application id "com.google.Chrome"
        if (count of windows) is 0 then return ""
        return URL of active tab of front window
    end tell
end try
return ""
"#;

const ARC_SCRIPT: &str = r#"
try
    tell application id "company.thebrowser.Browser"
        if (count of windows) is 0 then return ""
        return URL of active tab of front window
    end tell
end try
return ""
"#;

const BRAVE_SCRIPT: &str = r#"
try
    tell application id "com.brave.Browser"
        if (count of windows) is 0 then return ""
        return URL of active tab of front window
    end tell
end try
return ""
"#;

const EDGE_SCRIPT: &str = r#"
try
    tell application id "com.microsoft.edgemac"
        if (count of windows) is 0 then return ""
        return URL of active tab of front window
    end tell
end try
return ""
"#;

const SAFARI_SCRIPT: &str = r#"
try
    tell application id "com.apple.Safari"
        if (count of windows) is 0 then return ""
        return URL of front document
    end tell
end try
return ""
"#;

const SUBLIME_SCRIPT: &str = r#"
try
    tell application id "com.sublimetext.4"
        if (count of windows) is 0 then return ""
        return file name of active document
    end tell
end try
return ""
"#;

// ---------- Parsing helpers ----------

fn parse_document_lines(text: &str, default_confidence: f32) -> Vec<DocumentSource> {
    let mut out = Vec::new();
    for raw in text.lines() {
        let Some((source, value)) = raw.split_once('|') else {
            continue;
        };
        let conf = if source.ends_with(":active") || source == "ax:doc" {
            0.95
        } else {
            default_confidence
        };
        if let Some(doc) =
            document_from_existing_path(value, source, conf, DocumentCategory::User)
        {
            out.push(doc);
            continue;
        }
        for cand in crate::tools::extract_paths_from_title(value) {
            if let Some(doc) =
                document_from_existing_path(&cand, source, conf, DocumentCategory::User)
            {
                out.push(doc);
            }
        }
    }
    out
}

fn parse_lines_with_tag(text: &str, tag: &str, confidence: f32) -> Vec<DocumentSource> {
    let mut out = Vec::new();
    for raw in text.lines() {
        let value = raw.trim();
        if value.is_empty() {
            continue;
        }
        if let Some(doc) =
            document_from_existing_path(value, tag, confidence, DocumentCategory::User)
        {
            out.push(doc);
            continue;
        }
        for cand in crate::tools::extract_paths_from_title(value) {
            if let Some(doc) =
                document_from_existing_path(&cand, tag, confidence, DocumentCategory::User)
            {
                out.push(doc);
            }
        }
    }
    out
}

/// `lsof` fallback — catches files held by Electron/Chromium apps (Typora) and
/// sandboxed apps that proxy their docs through Container caches (WPS).
/// AX/AppleScript give nothing for those, but the FD list does.
fn lsof_documents(pid: u32, title_hints: &[String]) -> Vec<DocumentSource> {
    let output = Command::new("lsof")
        .args(["-p", &pid.to_string(), "-F", "nt"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .output()
        .ok();
    let Some(output) = output else {
        return Vec::new();
    };
    if !output.status.success() && output.stdout.is_empty() {
        return Vec::new();
    }
    let text = String::from_utf8_lossy(&output.stdout);
    let basenames: std::collections::HashSet<String> = title_hints
        .iter()
        .filter_map(|t| {
            let trimmed = t.trim().trim_matches('"');
            if trimmed.is_empty() {
                return None;
            }
            // Prefer the cleaned-up filename form (strips " - AppName" suffix).
            crate::tools::likely_document_name_from_title(trimmed)
                .or_else(|| Some(trimmed.to_string()))
        })
        .collect();

    let mut docs = Vec::new();
    let mut current_type: Option<String> = None;
    let mut count = 0usize;
    for line in text.lines() {
        if count >= 4000 {
            break; // cap on giant processes (browsers, IDEs)
        }
        count += 1;
        let Some(first) = line.chars().next() else {
            continue;
        };
        match first {
            'f' => current_type = None, // new file entry
            't' => current_type = Some(line[1..].to_string()),
            'n' => {
                if current_type.as_deref() != Some("REG") {
                    continue;
                }
                let path = &line[1..];
                let basename = std::path::Path::new(path)
                    .file_name()
                    .and_then(|n| n.to_str())
                    .unwrap_or_default();
                let matches_title = !basename.is_empty() && basenames.contains(basename);
                // Tight filter: lsof returns lock/log/db files too, and `is_interesting_path`
                // accepts anything under $HOME without dot-prefix. Restrict to known doc
                // extensions unless the basename matches one of the window titles.
                if !matches_title && !has_document_extension(path) {
                    continue;
                }
                let (source, confidence) = if matches_title {
                    ("lsof:title_match", 0.92f32)
                } else {
                    ("lsof", 0.45)
                };
                if let Some(doc) =
                    document_from_existing_path(path, source, confidence, DocumentCategory::User)
                {
                    docs.push(doc);
                }
            }
            _ => {}
        }
    }
    docs
}

const LSOF_DOC_EXTENSIONS: &[&str] = &[
    ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".markdown", ".pdf", ".xls", ".xlsx", ".ods",
    ".csv", ".tsv", ".ppt", ".pptx", ".odp", ".key", ".pages", ".numbers", ".epub", ".wps",
    ".wpt", ".et", ".ett", ".dps", ".dpt", ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".scss", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".rb", ".php",
    ".sh", ".sql", ".yaml", ".yml", ".toml", ".json", ".xml",
];

fn has_document_extension(path: &str) -> bool {
    let lower = path.to_lowercase();
    LSOF_DOC_EXTENSIONS.iter().any(|ext| lower.ends_with(ext))
}

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
            return Some(String::from_utf8_lossy(&output.stdout).to_string());
        }
        if started.elapsed() >= timeout {
            let _ = child.kill();
            let _ = child.wait();
            return None;
        }
        std::thread::sleep(Duration::from_millis(25));
    }
}
