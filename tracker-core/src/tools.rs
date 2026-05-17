use crate::models::{DocumentCategory, DocumentSource};
use regex::Regex;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

const INTERESTING_EXTENSIONS: &[&str] = &[
    ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pdf", ".xls", ".xlsx", ".ods", ".csv",
    ".tsv", ".ppt", ".pptx", ".odp", ".key", ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".scss", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".rb", ".php",
    ".sh", ".sql", ".yaml", ".yml", ".toml", ".json", ".xml", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".webp", ".mp3", ".wav", ".flac", ".mp4", ".mov", ".mkv", ".psd", ".ai", ".sketch",
    ".fig", ".xd", ".zip", ".tar", ".gz", ".7z", ".epub", ".wps", ".wpt", ".et", ".ett", ".dps",
    ".dpt",
];

/// Subset of [`INTERESTING_EXTENSIONS`] that represent files a user could
/// reasonably be "working on" (documents, source code) — excludes media/archives
/// to keep the FD-scan fallback (macOS `lsof`, Linux `/proc/PID/fd`) tight.
/// `is_interesting_path` accepts anything under $HOME without a dot-prefix, so
/// FD scans over a process holding many tmp/db/log files in $HOME would otherwise
/// flood the doc list.
const FD_SCAN_DOC_EXTENSIONS: &[&str] = &[
    ".doc",
    ".docx",
    ".odt",
    ".rtf",
    ".txt",
    ".md",
    ".markdown",
    ".pdf",
    ".xls",
    ".xlsx",
    ".ods",
    ".csv",
    ".tsv",
    ".ppt",
    ".pptx",
    ".odp",
    ".key",
    ".pages",
    ".numbers",
    ".epub",
    ".wps",
    ".wpt",
    ".et",
    ".ett",
    ".dps",
    ".dpt",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".css",
    ".scss",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".rb",
    ".php",
    ".sh",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".xml",
];

pub fn has_fd_scan_extension(path: &str) -> bool {
    let lower = path.to_lowercase();
    FD_SCAN_DOC_EXTENSIONS
        .iter()
        .any(|ext| lower.ends_with(ext))
}

const BORING_PATH_FRAGMENTS: &[&str] = &[
    "/site-packages/",
    "/dist-packages/",
    "/.cache/",
    "/Library/Caches/",
    "AppData\\Local\\",
    "AppData\\Roaming\\",
    "/proc/",
    "/dev/",
    "/System/",
    "/usr/lib/",
    "/usr/share/fonts/",
    "node_modules",
];

pub fn is_interesting_path(path: &str) -> bool {
    let lower = path.to_lowercase();
    if path.is_empty()
        || BORING_PATH_FRAGMENTS
            .iter()
            .any(|frag| lower.contains(&frag.to_lowercase()))
    {
        return false;
    }
    let ext = Path::new(path)
        .extension()
        .and_then(|s| s.to_str())
        .map(|s| format!(".{}", s.to_lowercase()))
        .unwrap_or_default();
    if INTERESTING_EXTENSIONS.iter().any(|e| *e == ext) {
        return true;
    }
    if let Some(home) = dirs::home_dir().and_then(|p| p.to_str().map(ToOwned::to_owned)) {
        return path.starts_with(&home)
            && !path[home.len()..].contains("/.")
            && !path[home.len()..].contains("\\.");
    }
    false
}

pub fn document_from_existing_path(
    path: &str,
    source: &str,
    confidence: f32,
    category: DocumentCategory,
) -> Option<DocumentSource> {
    let path = normalize_candidate_path(path)?;
    if !is_interesting_path(&path) {
        return None;
    }
    let kind = classify_path(&path);
    if kind == "unknown" {
        return None;
    }
    Some(DocumentSource {
        path,
        kind,
        source: source.to_string(),
        confidence,
        category,
    })
}

/// 判断 `path` 是否落在 `dir` 目录树内（含 dir 自身）。Windows 下大小写不敏感。
pub fn path_under(path: &str, dir: &str) -> bool {
    if path.is_empty() || dir.is_empty() {
        return false;
    }
    let p = normalize_compare(path);
    let d = normalize_compare(dir);
    if d.is_empty() {
        return false;
    }
    if p == d {
        return true;
    }
    let needle = if d.ends_with('/') {
        d.clone()
    } else {
        format!("{}/", d)
    };
    p.starts_with(&needle)
}

fn normalize_compare(s: &str) -> String {
    let mut out = s.replace('\\', "/");
    while out.ends_with('/') {
        out.pop();
    }
    if cfg!(windows) {
        out.to_lowercase()
    } else {
        out
    }
}

pub fn normalize_candidate_path(raw: &str) -> Option<String> {
    let trimmed = raw
        .trim()
        .trim_matches('"')
        .trim_matches('\'')
        .trim_end_matches(['\0', '\r', '\n']);
    if trimmed.is_empty() {
        return None;
    }
    if let Some(path) = file_url_to_path(trimmed) {
        return Some(path);
    }
    let expanded = expand_user(trimmed);
    let path = Path::new(&expanded);
    if !path.is_absolute() {
        return None;
    }
    if path.exists() {
        return Some(path.to_string_lossy().to_string());
    }
    None
}

pub fn classify_path(path: &str) -> String {
    let p = Path::new(path);
    if p.is_dir() {
        "folder".to_string()
    } else if p.is_file() {
        "file".to_string()
    } else {
        "unknown".to_string()
    }
}

pub fn dedupe_documents(docs: Vec<DocumentSource>) -> Vec<DocumentSource> {
    let mut best: HashMap<String, DocumentSource> = HashMap::new();
    for doc in docs {
        match best.get(&doc.path) {
            Some(cur) if cur.confidence >= doc.confidence => {}
            _ => {
                best.insert(doc.path.clone(), doc);
            }
        }
    }
    let mut out = best.into_values().collect::<Vec<_>>();
    out.sort_by(|a, b| b.confidence.total_cmp(&a.confidence));
    out
}

pub fn file_url_to_path(url: &str) -> Option<String> {
    let rest = url.strip_prefix("file://")?;
    let decoded = percent_decode(rest);
    #[cfg(windows)]
    {
        let trimmed = decoded.trim_start_matches('/');
        return Some(trimmed.replace('/', "\\"));
    }
    #[cfg(not(windows))]
    Some(decoded)
}

pub fn extract_paths_from_title(title: &str) -> Vec<String> {
    static WIN_RE: OnceLock<Regex> = OnceLock::new();
    static POSIX_RE: OnceLock<Regex> = OnceLock::new();
    let win = WIN_RE.get_or_init(|| Regex::new(r#"[A-Za-z]:\\[^<>:"|?*\r\n]+"#).unwrap());
    let posix = POSIX_RE.get_or_init(|| Regex::new(r#"(?:~|/)[^\s"'<>]+"#).unwrap());
    win.find_iter(title)
        .chain(posix.find_iter(title))
        .map(|m| expand_user(m.as_str()))
        .collect()
}

pub fn likely_document_name_from_title(title: &str) -> Option<String> {
    let mut candidate = title.trim();
    if candidate.is_empty() {
        return None;
    }
    for sep in ['\u{2014}', '\u{2013}'] {
        if let Some((left, _)) = candidate.split_once(sep) {
            candidate = left.trim();
            break;
        }
    }
    const SEPARATORS: &[&str] = &[" - ", " — ", " – "];
    for sep in SEPARATORS {
        if let Some((left, _)) = candidate.split_once(sep) {
            candidate = left.trim();
            break;
        }
    }
    if candidate.is_empty() {
        return None;
    }
    let lower = candidate.to_lowercase();
    let has_known_ext = INTERESTING_EXTENSIONS
        .iter()
        .any(|ext| lower.ends_with(ext));
    if has_known_ext {
        Some(candidate.trim_matches('"').to_string())
    } else {
        None
    }
}

pub fn expand_user(path: &str) -> String {
    if let Some(rest) = path.strip_prefix("~/") {
        if let Some(home) = dirs::home_dir() {
            return home.join(rest).to_string_lossy().to_string();
        }
    }
    path.to_string()
}

pub fn looks_like_browser(executable: Option<&str>, app_name: Option<&str>) -> bool {
    const HINTS: &[&str] = &[
        "google chrome",
        "chrome.exe",
        "chrome",
        "microsoft edge",
        "msedge.exe",
        "firefox",
        "firefox.exe",
        "brave",
        "brave.exe",
        "arc",
        "safari",
    ];
    [executable, app_name]
        .into_iter()
        .flatten()
        .map(|s| s.to_lowercase())
        .any(|s| HINTS.iter().any(|h| s.contains(h)))
}

pub fn redact_cmdline(cmdline: &[String]) -> (Vec<String>, bool) {
    let flag_eq = sensitive_flag_patterns();
    let value_patterns = value_patterns();
    let names = sensitive_flag_names();
    let mut out = Vec::with_capacity(cmdline.len());
    let mut was = false;
    let mut i = 0;
    while i < cmdline.len() {
        let token = cmdline[i].as_str();
        if let Some((name, value)) = flag_eq.iter().find_map(|re| {
            re.captures(token).map(|c| {
                (
                    c.get(1).map(|m| m.as_str()).unwrap_or_default().to_string(),
                    c.get(2).map(|m| m.as_str()).unwrap_or_default().to_string(),
                )
            })
        }) {
            out.push(format!("{}={}", name, redact_value(&value)));
            was = true;
            i += 1;
            continue;
        }
        if names.contains(&token.to_lowercase().as_str()) && i + 1 < cmdline.len() {
            out.push(token.to_string());
            out.push(redact_value(&cmdline[i + 1]));
            was = true;
            i += 2;
            continue;
        }
        if value_patterns.iter().any(|re| re.is_match(token)) {
            out.push(redact_value(token));
            was = true;
            i += 1;
            continue;
        }
        out.push(token.to_string());
        i += 1;
    }
    (out, was)
}

fn redact_value(v: &str) -> String {
    if v.len() < 8 {
        v.to_string()
    } else if v.len() > 12 {
        format!("{}***{}", &v[..3], &v[v.len() - 2..])
    } else {
        "***".to_string()
    }
}

fn sensitive_flag_patterns() -> &'static [Regex] {
    static RES: OnceLock<Vec<Regex>> = OnceLock::new();
    RES.get_or_init(|| {
        vec![
            Regex::new(r"(?i)^(--?password|--?passwd|--?pass)=(.*)$").unwrap(),
            Regex::new(
                r"(?i)^(--?token|--?api-?key|--?apikey|--?secret|--?auth|--?authorization)=(.*)$",
            )
            .unwrap(),
            Regex::new(r"(?i)^(--?bearer)=(.*)$").unwrap(),
        ]
    })
}

fn sensitive_flag_names() -> &'static [&'static str] {
    &[
        "--password",
        "-p",
        "--passwd",
        "--pass",
        "--token",
        "--api-key",
        "--apikey",
        "--secret",
        "--auth",
        "--authorization",
        "--bearer",
        "--access-key",
        "--access-key-id",
        "--secret-key",
        "--secret-access-key",
        "--client-secret",
        "--private-key",
    ]
}

fn value_patterns() -> &'static [Regex] {
    static RES: OnceLock<Vec<Regex>> = OnceLock::new();
    RES.get_or_init(|| {
        vec![
            Regex::new(r"^AKIA[0-9A-Z]{16}$").unwrap(),
            Regex::new(r"^sk-[A-Za-z0-9_\-]{20,}$").unwrap(),
            Regex::new(r"^ghp_[A-Za-z0-9]{30,}$").unwrap(),
            Regex::new(r"^gho_[A-Za-z0-9]{30,}$").unwrap(),
            Regex::new(r"^xox[bpas]-[A-Za-z0-9\-]{20,}$").unwrap(),
            Regex::new(r"^[A-Fa-f0-9]{40,}$").unwrap(),
            Regex::new(r"^[A-Za-z0-9+/]{48,}={0,2}$").unwrap(),
        ]
    })
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h), Some(l)) = (hex(bytes[i + 1]), hex(bytes[i + 2])) {
                out.push(h * 16 + l);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).to_string()
}

fn hex(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

pub fn normalize_path_lossy(path: PathBuf) -> String {
    path.to_string_lossy().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn document_from_existing_path_preserves_unicode() {
        let path = std::env::current_dir()
            .unwrap()
            .join("active_tracker_知识库演进.md");
        std::fs::write(&path, "# test").unwrap();
        let doc = document_from_existing_path(
            &path.to_string_lossy(),
            "test",
            1.0,
            DocumentCategory::User,
        )
        .unwrap();
        assert!(doc.path.contains("知识库演进.md"));
        assert_eq!(doc.kind, "file");
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn likely_document_name_strips_app_suffix() {
        assert_eq!(
            likely_document_name_from_title("知识库演进.md - Typora").as_deref(),
            Some("知识库演进.md")
        );
    }
}
