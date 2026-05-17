use crate::models::{DocumentCategory, DocumentSource, ProcessInfo, WindowInfo};
use crate::tools::{
    classify_path, dedupe_documents, document_from_existing_path, extract_paths_from_title,
    is_interesting_path, likely_document_name_from_title, normalize_path_lossy,
};
use std::path::{Path, PathBuf};
use sysinfo::{Pid, ProcessRefreshKind, ProcessesToUpdate, System, UpdateKind};

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "windows")]
mod windows;

#[cfg(target_os = "linux")]
pub use self::linux::active_window;
#[cfg(target_os = "linux")]
pub use self::linux::enrich_platform_window_documents;
#[cfg(target_os = "macos")]
pub use self::macos::active_window;
#[cfg(target_os = "macos")]
pub use self::macos::enrich_platform_window_documents;
#[cfg(target_os = "windows")]
pub use self::windows::active_window;
#[cfg(target_os = "windows")]
pub use self::windows::enrich_platform_window_documents;

#[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
pub async fn enrich_platform_window_documents(info: WindowInfo) -> WindowInfo {
    info
}

#[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
pub async fn active_window() -> anyhow::Result<WindowInfo> {
    let mut info = WindowInfo::default();
    info.errors.push("unsupported platform".to_string());
    Ok(info)
}

pub fn process_info(pid: u32) -> Option<ProcessInfo> {
    let mut system = System::new();
    let pid = Pid::from_u32(pid);
    let pids = [pid];
    system.refresh_processes_specifics(
        ProcessesToUpdate::Some(&pids),
        true,
        ProcessRefreshKind::nothing()
            .with_exe(UpdateKind::Always)
            .with_cmd(UpdateKind::Always)
            .with_cwd(UpdateKind::Always)
            .with_memory(),
    );
    let proc_ = system.process(pid)?;
    let cmdline = proc_
        .cmd()
        .iter()
        .map(|s| s.to_string_lossy().to_string())
        .collect::<Vec<_>>();
    Some(ProcessInfo {
        pid: pid.as_u32(),
        name: proc_.name().to_string_lossy().to_string(),
        executable: proc_.exe().map(|p| normalize_path_lossy(p.to_path_buf())),
        cmdline,
        cwd: proc_.cwd().map(|p| normalize_path_lossy(p.to_path_buf())),
        username: None,
        create_time: Some(proc_.start_time() as f64),
        cpu_percent: Some(proc_.cpu_usage()),
        memory_rss: Some(proc_.memory()),
    })
}

pub fn collect_title_and_cwd_documents(info: &mut WindowInfo) {
    collect_cmdline_documents(info);
    if !info.window_title.is_empty() {
        for path in extract_paths_from_title(&info.window_title) {
            if !is_interesting_path(&path) {
                continue;
            }
            let kind = classify_path(&path);
            let confidence = if kind == "unknown" { 0.4 } else { 0.7 };
            info.document_paths.push(DocumentSource {
                path,
                kind,
                source: "title".to_string(),
                confidence,
                category: DocumentCategory::User,
            });
        }
        collect_title_name_documents(info);
    }
    if let Some(cwd) = info.process.as_ref().and_then(|p| p.cwd.clone()) {
        info.document_paths.push(DocumentSource {
            path: cwd,
            kind: "folder".to_string(),
            source: "cwd".to_string(),
            confidence: 0.3,
            category: DocumentCategory::Process,
        });
    }
    info.document_paths = dedupe_documents(std::mem::take(&mut info.document_paths));
}

fn collect_cmdline_documents(info: &mut WindowInfo) {
    let Some(proc_) = &info.process else {
        return;
    };
    for token in &proc_.cmdline {
        if let Some(doc) =
            document_from_existing_path(token, "cmdline", 0.85, DocumentCategory::User)
        {
            info.document_paths.push(doc);
            continue;
        }
        if let Some(cwd) = &proc_.cwd {
            let joined = PathBuf::from(cwd).join(token.trim_matches(['"', '\'']));
            if let Some(doc) = document_from_existing_path(
                &joined.to_string_lossy(),
                "cmdline",
                0.8,
                DocumentCategory::User,
            ) {
                info.document_paths.push(doc);
            }
        }
    }
}

fn collect_title_name_documents(info: &mut WindowInfo) {
    let Some(name) = likely_document_name_from_title(&info.window_title) else {
        return;
    };
    for dir in candidate_search_dirs(info) {
        let candidate = dir.join(&name);
        if let Some(doc) = document_from_existing_path(
            &candidate.to_string_lossy(),
            "title_filename",
            0.55,
            DocumentCategory::User,
        ) {
            info.document_paths.push(doc);
        }
    }
}

fn candidate_search_dirs(info: &WindowInfo) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Some(cwd) = info.process.as_ref().and_then(|p| p.cwd.as_ref()) {
        out.push(PathBuf::from(cwd));
    }
    if let Some(home) = dirs::home_dir() {
        out.extend([
            home.clone(),
            home.join("Desktop"),
            home.join("Documents"),
            home.join("Downloads"),
            home.join("OneDrive").join("Desktop"),
            home.join("OneDrive").join("Documents"),
        ]);
    }
    let mut seen = std::collections::HashSet::new();
    out.into_iter()
        .filter(|p| p.is_dir())
        .filter(|p| seen.insert(normalize_for_dedupe(p)))
        .collect()
}

fn normalize_for_dedupe(path: &Path) -> String {
    path.to_string_lossy().to_lowercase()
}
