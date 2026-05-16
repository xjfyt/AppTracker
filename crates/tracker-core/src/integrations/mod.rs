pub mod file_manager;
pub mod shell_files;
pub mod terminal;

use crate::models::{DocumentSource, FileManagerState, TerminalContext, WindowInfo};
use crate::platform::enrich_platform_window_documents;
use crate::tools::{classify_path, dedupe_documents};

pub async fn enrich_window(mut info: WindowInfo) -> WindowInfo {
    info = enrich_platform_window_documents(info).await;
    let fm = file_manager::query(&info).await;
    let term = terminal::query(&info).await;
    info.file_manager_state = fm;
    info.terminal_context = term;
    merge_into_document_paths(&mut info);
    info
}

fn merge_into_document_paths(info: &mut WindowInfo) {
    let mut base = info
        .document_paths
        .drain(..)
        .filter(|d| {
            d.source != "file_manager"
                && d.source != "file_manager_selection"
                && !d.source.starts_with("terminal:")
        })
        .collect::<Vec<_>>();

    let mut extras = Vec::new();
    if let Some(FileManagerState { windows, .. }) = &info.file_manager_state {
        for window in windows {
            if !window.folder.is_empty() {
                extras.push(DocumentSource {
                    path: window.folder.clone(),
                    kind: "folder".to_string(),
                    source: "file_manager".to_string(),
                    confidence: if window.is_active { 0.95 } else { 0.7 },
                });
            }
            for selected in &window.selected_items {
                let mut kind = classify_path(selected);
                if kind == "unknown" {
                    kind = if std::path::Path::new(selected).is_dir() {
                        "folder".to_string()
                    } else {
                        "file".to_string()
                    };
                }
                extras.push(DocumentSource {
                    path: selected.clone(),
                    kind,
                    source: "file_manager_selection".to_string(),
                    confidence: if window.is_active { 0.95 } else { 0.7 },
                });
            }
        }
    }

    if let Some(TerminalContext { shells, .. }) = &info.terminal_context {
        let mut seen = std::collections::HashSet::new();
        for shell in shells {
            let Some(cwd) = &shell.cwd else {
                continue;
            };
            if !seen.insert(cwd.clone()) {
                continue;
            }
            extras.push(DocumentSource {
                path: cwd.clone(),
                kind: "folder".to_string(),
                source: format!("terminal:{}", shell.name),
                confidence: if shell.cwd_source == "shell_file" {
                    0.9
                } else {
                    0.8
                },
            });
        }
    }

    extras.append(&mut base);
    info.document_paths = dedupe_documents(extras);
}
