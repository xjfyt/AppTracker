use crate::activity::spawn_activity_monitor;
use crate::api::{spawn_api, ServerHandle};
use crate::bridge::{spawn_browser_bridge, BrowserBridgeHandle};
use crate::capture::spawn_screen_capture;
use crate::integrations::enrich_window;
use crate::platform::active_window;
use crate::state::TrackerState;
use std::time::Duration;
use tokio::task::JoinHandle;

#[derive(Debug, Clone)]
pub struct AgentConfig {
    pub host: String,
    pub api_port: u16,
    pub browser_port: u16,
    pub no_activity: bool,
    pub no_capture: bool,
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
            no_browser_bridge: false,
            poll_interval_ms: 500,
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
        let mut last_identity = String::new();
        loop {
            ticker.tick().await;
            if state.is_paused() {
                continue;
            }
            match active_window().await {
                Ok(info) => {
                    let enriched = enrich_window(info).await;
                    let identity = format!(
                        "{}|{:?}|{:?}",
                        enriched.identity_key(),
                        enriched.file_manager_state,
                        enriched.terminal_context
                    );
                    if identity != last_identity {
                        last_identity = identity;
                        state.update_window(enriched).await;
                    }
                }
                Err(exc) => {
                    tracing::debug!(error = %exc, "active window query failed");
                }
            }
        }
    })
}
