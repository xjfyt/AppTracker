use crate::activity::spawn_activity_monitor;
use crate::api::{spawn_api, ServerHandle};
use crate::bridge::load_or_create_token;
use crate::capture::spawn_screen_capture;
use crate::integrations::enrich_window;
use crate::models::{DocumentCategory, DocumentSource, WindowInfo};
use crate::platform::active_window;
use crate::state::TrackerState;
use crate::tools::{dedupe_documents, likely_document_name_from_title};
use std::collections::{HashMap, HashSet};
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::task::JoinHandle;

#[derive(Debug, Clone)]
pub struct AgentConfig {
    pub host: String,
    pub api_port: u16,
    pub no_activity: bool,
    pub no_capture: bool,
    pub capture_default_on: bool,
    pub poll_interval_ms: u64,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            api_port: 5007,
            no_activity: false,
            no_capture: false,
            capture_default_on: false,
            poll_interval_ms: 250,
        }
    }
}

pub struct AgentHandle {
    pub state: TrackerState,
    pub api: ServerHandle,
    pub window_task: JoinHandle<()>,
}

pub async fn start_agent(config: AgentConfig) -> anyhow::Result<AgentHandle> {
    let state = TrackerState::new();
    let (token_path, token) = load_or_create_token().await?;
    let api = spawn_api(
        state.clone(),
        &config.host,
        config.api_port,
        Arc::new(token),
        token_path,
    )
    .await?;

    if !config.no_activity {
        spawn_activity_monitor(state.clone(), 60);
    }
    if !config.no_capture {
        state.set_capture_enabled(config.capture_default_on);
        spawn_screen_capture(state.clone());
    }
    let window_task = spawn_window_monitor(state.clone(), config.poll_interval_ms);

    Ok(AgentHandle {
        state,
        api,
        window_task,
    })
}

fn spawn_window_monitor(state: TrackerState, poll_interval_ms: u64) -> JoinHandle<()> {
    tokio::spawn(supervised("window_monitor", move || {
        let state = state.clone();
        async move { run_window_monitor(state, poll_interval_ms).await }
    }))
}

async fn run_window_monitor(state: TrackerState, poll_interval_ms: u64) {
    let mut ticker = tokio::time::interval(Duration::from_millis(poll_interval_ms.max(100)));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut last_identity = String::new();
    let mut last_enrich_key = String::new();
    let mut last_enrich_at = Instant::now() - Duration::from_secs(10);
    let document_memory = Arc::new(Mutex::new(DocumentMemory::default()));
    let (enrich_tx, enrich_rx) = tokio::sync::watch::channel(None::<WindowInfo>);
    spawn_window_enrichment_worker(state.clone(), document_memory.clone(), enrich_rx);
    loop {
        ticker.tick().await;
        if state.is_paused() {
            continue;
        }
        match active_window().await {
            Ok(mut info) => {
                apply_document_memory(&document_memory, &mut info);
                let identity = fast_window_identity(&info);
                if identity != last_identity {
                    last_identity = identity;
                    // 把先前富化得到的 office / UIA / 文件管理器 / 终端 数据驮过来，
                    // 否则一旦 WPS/Notepad 标题闪动（脏标记、页码变化等）就会
                    // 被这条 basic-only 的更新覆盖掉。
                    if let Some(current) = state.current_window().await {
                        if same_window(&current, &info) {
                            carry_enrich_only_docs(&current, &mut info);
                        }
                    }
                    state.update_window(info.clone()).await;
                }

                let enrich_key = foreground_match_key(&info);
                if enrich_key != last_enrich_key
                    || last_enrich_at.elapsed() >= Duration::from_millis(900)
                {
                    last_enrich_key = enrich_key;
                    last_enrich_at = Instant::now();
                    let _ = enrich_tx.send(Some(info));
                }
            }
            Err(exc) => {
                tracing::debug!(error = %exc, "active window query failed");
            }
        }
    }
}

fn spawn_window_enrichment_worker(
    state: TrackerState,
    document_memory: Arc<Mutex<DocumentMemory>>,
    rx: tokio::sync::watch::Receiver<Option<WindowInfo>>,
) -> JoinHandle<()> {
    tokio::spawn(supervised("window_enrichment", move || {
        let state = state.clone();
        let document_memory = document_memory.clone();
        let rx = rx.clone();
        async move { run_window_enrichment_worker(state, document_memory, rx).await }
    }))
}

async fn run_window_enrichment_worker(
    state: TrackerState,
    document_memory: Arc<Mutex<DocumentMemory>>,
    mut rx: tokio::sync::watch::Receiver<Option<WindowInfo>>,
) {
    while rx.changed().await.is_ok() {
        let Some(info) = rx.borrow_and_update().clone() else {
            continue;
        };
        let expected_window_key = window_identity_key(&info);
        let mut enriched = enrich_window(info).await;
        apply_document_memory(&document_memory, &mut enriched);
        if should_publish_enriched(&state, &expected_window_key, &enriched).await {
            state.update_window(enriched).await;
        }
    }
}

/// Restart `make_fut` if its task panics. Logs (and `crash.log` captures the
/// backtrace via [`crate::diagnostics::install_panic_hook`]). On clean exit
/// (the future returned normally), don't restart — the worker is done.
async fn supervised<F, Fut>(name: &'static str, mut make_fut: F)
where
    F: FnMut() -> Fut + Send + 'static,
    Fut: std::future::Future<Output = ()> + Send + 'static,
{
    let mut attempt = 0u32;
    loop {
        let handle = tokio::spawn(make_fut());
        match handle.await {
            Ok(()) => {
                tracing::warn!(worker = name, attempt, "worker exited cleanly");
                return;
            }
            Err(join_err) if join_err.is_panic() => {
                attempt += 1;
                tracing::error!(
                    worker = name,
                    attempt,
                    "worker panicked (see ~/.active_tracker/crash.log); restarting in 2s",
                );
                tokio::time::sleep(Duration::from_secs(2)).await;
            }
            Err(_) => {
                tracing::debug!(worker = name, "worker cancelled");
                return;
            }
        }
    }
}

async fn should_publish_enriched(
    state: &TrackerState,
    expected_window_key: &str,
    enriched: &WindowInfo,
) -> bool {
    let Some(current) = state.current_window().await else {
        return true;
    };
    // 只看「是不是同一个窗口」，不再卡 title——WPS/Office 在打字 / 翻页时标题
    // 会持续变化，原先 foreground_match_key 含 title 会让 PowerShell COM 探测
    // 的结果在落地前就被丢弃，导致检测时灵时不灵。
    if window_identity_key(&current) != expected_window_key {
        return false;
    }
    fast_window_identity(&current) != fast_window_identity(enriched)
}

fn apply_document_memory(memory: &Arc<Mutex<DocumentMemory>>, info: &mut WindowInfo) {
    if let Ok(mut memory) = memory.lock() {
        memory.apply(info);
    }
}

fn fast_window_identity(info: &WindowInfo) -> String {
    format!(
        "{}|{:?}|{:?}",
        info.identity_key(),
        info.file_manager_state,
        info.terminal_context
    )
}

fn foreground_match_key(info: &WindowInfo) -> String {
    let pid = info.process.as_ref().map(|p| p.pid).unwrap_or_default();
    format!(
        "{}|{}|{}",
        info.window_id.as_deref().unwrap_or_default(),
        pid,
        info.window_title
    )
}

/// 与 [`foreground_match_key`] 的区别：不带 `window_title`。
/// 用于「这条 enrich 结果是不是还属于同一个窗口」的判断，避免标题抖动
/// 时富化结果被错判为过期。
fn window_identity_key(info: &WindowInfo) -> String {
    let pid = info.process.as_ref().map(|p| p.pid).unwrap_or_default();
    format!(
        "{}|{}|{}",
        info.window_id.as_deref().unwrap_or_default(),
        pid,
        info.app_name
    )
}

fn same_window(a: &WindowInfo, b: &WindowInfo) -> bool {
    window_identity_key(a) == window_identity_key(b)
}

fn is_enrich_only_source(source: &str) -> bool {
    source == "file_manager"
        || source == "file_manager_selection"
        || source.starts_with("terminal:")
        || source.starts_with("office:")
        || source.starts_with("uia:")
        || source.starts_with("ax:")
        || source.starts_with("browser:")
        || source.starts_with("editor:")
        || source.starts_with("lsof")
        || source.starts_with("fd")
        || source.starts_with("libreoffice:")
        || source.starts_with("atspi:")
        || source.starts_with("dbus:")
}

fn carry_enrich_only_docs(current: &WindowInfo, info: &mut WindowInfo) {
    let mut carried = false;
    for doc in &current.document_paths {
        if is_enrich_only_source(&doc.source) {
            info.document_paths.push(doc.clone());
            carried = true;
        }
    }
    if info.file_manager_state.is_none() && current.file_manager_state.is_some() {
        info.file_manager_state = current.file_manager_state.clone();
    }
    if info.terminal_context.is_none() && current.terminal_context.is_some() {
        info.terminal_context = current.terminal_context.clone();
    }
    if carried {
        info.document_paths = dedupe_documents(std::mem::take(&mut info.document_paths));
    }
}

#[derive(Default)]
struct DocumentMemory {
    by_process: HashMap<String, HashMap<String, String>>,
    global: HashMap<String, String>,
    global_ambiguous: HashSet<String>,
}

impl DocumentMemory {
    fn apply(&mut self, info: &mut WindowInfo) {
        self.remember(info);
        self.resolve_title_filename(info);
        info.document_paths = dedupe_documents(std::mem::take(&mut info.document_paths));
    }

    fn remember(&mut self, info: &WindowInfo) {
        let Some(process_key) = process_memory_key(info) else {
            return;
        };
        let process_docs = self.by_process.entry(process_key).or_default();
        for doc in &info.document_paths {
            if doc.kind != "file" {
                continue;
            }
            let path = Path::new(&doc.path);
            if !path.is_absolute() || !path.exists() {
                continue;
            }
            let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
                continue;
            };
            let key = normalize_name(name);
            process_docs.insert(key.clone(), doc.path.clone());
            match self.global.get(&key) {
                Some(existing) if existing != &doc.path => {
                    self.global.remove(&key);
                    self.global_ambiguous.insert(key);
                }
                Some(_) => {}
                None if !self.global_ambiguous.contains(&key) => {
                    self.global.insert(key, doc.path.clone());
                }
                None => {}
            }
        }
    }

    fn resolve_title_filename(&self, info: &mut WindowInfo) {
        let Some(name) = likely_document_name_from_title(&info.window_title) else {
            return;
        };
        let key = normalize_name(&name);
        let process_hit = process_memory_key(info)
            .and_then(|process_key| self.by_process.get(&process_key))
            .and_then(|docs| docs.get(&key));
        let path = process_hit.or_else(|| self.global.get(&key));
        let Some(path) = path else {
            return;
        };
        info.document_paths.push(DocumentSource {
            path: path.clone(),
            kind: "file".to_string(),
            source: "title_memory".to_string(),
            confidence: 0.88,
            category: DocumentCategory::User,
        });
    }
}

fn process_memory_key(info: &WindowInfo) -> Option<String> {
    let proc_ = info.process.as_ref()?;
    Some(format!(
        "{}:{}",
        proc_.pid,
        proc_.executable.as_deref().unwrap_or(&proc_.name)
    ))
}

fn normalize_name(name: &str) -> String {
    name.trim().to_lowercase()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::ProcessInfo;

    fn test_file_path(dir: &Path, name: &str) -> String {
        let path = dir.join(name);
        std::fs::write(&path, "test").unwrap();
        path.to_string_lossy().to_string()
    }

    fn window_with_doc(pid: u32, exe: &str, path: String) -> WindowInfo {
        WindowInfo {
            process: Some(ProcessInfo {
                pid,
                name: exe.to_string(),
                executable: Some(exe.to_string()),
                ..Default::default()
            }),
            document_paths: vec![DocumentSource {
                path,
                kind: "file".to_string(),
                source: "test".to_string(),
                confidence: 1.0,
                category: DocumentCategory::User,
            }],
            ..Default::default()
        }
    }

    #[test]
    fn document_memory_does_not_resolve_ambiguous_global_name() {
        let root = std::env::temp_dir().join(format!(
            "apptracker-memory-{}",
            crate::models::now_ts().to_bits()
        ));
        let dir_a = root.join("a");
        let dir_b = root.join("b");
        std::fs::create_dir_all(&dir_a).unwrap();
        std::fs::create_dir_all(&dir_b).unwrap();
        let path_a = test_file_path(&dir_a, "same.md");
        let path_b = test_file_path(&dir_b, "same.md");

        let mut memory = DocumentMemory::default();
        let mut first = window_with_doc(1, "/tmp/editor-a", path_a);
        memory.apply(&mut first);
        let mut second = window_with_doc(2, "/tmp/editor-b", path_b);
        memory.apply(&mut second);

        let mut lookup = WindowInfo {
            window_title: "same.md - Editor".to_string(),
            process: Some(ProcessInfo {
                pid: 3,
                name: "editor-c".to_string(),
                executable: Some("/tmp/editor-c".to_string()),
                ..Default::default()
            }),
            ..Default::default()
        };
        memory.apply(&mut lookup);

        assert!(lookup
            .document_paths
            .iter()
            .all(|doc| doc.source != "title_memory"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn document_memory_still_resolves_process_local_name() {
        let root = std::env::temp_dir().join(format!(
            "apptracker-memory-local-{}",
            crate::models::now_ts().to_bits()
        ));
        std::fs::create_dir_all(&root).unwrap();
        let path = test_file_path(&root, "local.md");

        let mut memory = DocumentMemory::default();
        let mut known = window_with_doc(9, "/tmp/editor", path.clone());
        memory.apply(&mut known);
        let mut lookup = WindowInfo {
            window_title: "local.md - Editor".to_string(),
            process: Some(ProcessInfo {
                pid: 9,
                name: "editor".to_string(),
                executable: Some("/tmp/editor".to_string()),
                ..Default::default()
            }),
            ..Default::default()
        };
        memory.apply(&mut lookup);

        assert!(lookup
            .document_paths
            .iter()
            .any(|doc| doc.source == "title_memory" && doc.path == path));
        let _ = std::fs::remove_dir_all(root);
    }
}
