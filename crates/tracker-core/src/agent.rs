use crate::activity::spawn_activity_monitor;
use crate::api::{spawn_api, ServerHandle};
use crate::bridge::{spawn_browser_bridge, BrowserBridgeHandle};
use crate::capture::spawn_screen_capture;
use crate::integrations::enrich_window;
use crate::models::{DocumentSource, WindowInfo};
use crate::platform::active_window;
use crate::state::TrackerState;
use crate::tools::{dedupe_documents, likely_document_name_from_title};
use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio::task::JoinHandle;

#[derive(Debug, Clone)]
pub struct AgentConfig {
    pub host: String,
    pub api_port: u16,
    pub browser_port: u16,
    pub no_activity: bool,
    pub no_capture: bool,
    pub capture_default_on: bool,
    pub no_browser_bridge: bool,
    pub poll_interval_ms: u64,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            api_port: 5007,
            browser_port: 5006,
            no_activity: false,
            no_capture: false,
            capture_default_on: false,
            no_browser_bridge: false,
            poll_interval_ms: 250,
        }
    }
}

pub struct AgentHandle {
    pub state: TrackerState,
    pub api: ServerHandle,
    pub browser_bridge: Option<BrowserBridgeHandle>,
    pub window_task: JoinHandle<()>,
}

pub async fn start_agent(config: AgentConfig) -> anyhow::Result<AgentHandle> {
    let state = TrackerState::new();
    let api = spawn_api(state.clone(), &config.host, config.api_port).await?;
    let browser_bridge = if config.no_browser_bridge {
        None
    } else {
        Some(spawn_browser_bridge(state.clone(), &config.host, config.browser_port).await?)
    };

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
        browser_bridge,
        window_task,
    })
}

fn spawn_window_monitor(state: TrackerState, poll_interval_ms: u64) -> JoinHandle<()> {
    tokio::spawn(async move {
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
    })
}

fn spawn_window_enrichment_worker(
    state: TrackerState,
    document_memory: Arc<Mutex<DocumentMemory>>,
    mut rx: tokio::sync::watch::Receiver<Option<WindowInfo>>,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        while rx.changed().await.is_ok() {
            let Some(info) = rx.borrow_and_update().clone() else {
                continue;
            };
            let expected_key = foreground_match_key(&info);
            let mut enriched = enrich_window(info).await;
            apply_document_memory(&document_memory, &mut enriched);
            if should_publish_enriched(&state, &expected_key, &enriched).await {
                state.update_window(enriched).await;
            }
        }
    })
}

async fn should_publish_enriched(
    state: &TrackerState,
    expected_key: &str,
    enriched: &WindowInfo,
) -> bool {
    let Some(current) = state.current_window().await else {
        return true;
    };
    if foreground_match_key(&current) != expected_key {
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

#[derive(Default)]
struct DocumentMemory {
    by_process: HashMap<String, HashMap<String, String>>,
    global: HashMap<String, String>,
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
            self.global.insert(key, doc.path.clone());
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
