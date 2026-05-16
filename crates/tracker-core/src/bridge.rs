use crate::models::BrowserTab;
use crate::state::TrackerState;
use anyhow::{anyhow, Context};
use axum::extract::ws::{Message, WebSocket};
use axum::extract::{State, WebSocketUpgrade};
use axum::response::IntoResponse;
use axum::routing::get;
use axum::Router;
use base64::prelude::*;
use futures_util::{SinkExt, StreamExt};
use rand::RngCore;
use serde::Deserialize;
use std::net::{IpAddr, SocketAddr};
use std::path::PathBuf;
use tokio::fs;
use tokio::net::TcpListener;
use tokio::task::JoinHandle;

const PORT_FALLBACK_RANGE: u16 = 5;

#[derive(Debug)]
pub struct BrowserBridgeHandle {
    pub addr: SocketAddr,
    pub token_path: PathBuf,
    pub task: JoinHandle<()>,
}

#[derive(Clone)]
struct BridgeState {
    tracker: TrackerState,
    token: String,
}

pub async fn spawn_browser_bridge(
    tracker: TrackerState,
    host: &str,
    port: u16,
) -> anyhow::Result<BrowserBridgeHandle> {
    let (token_path, token) = load_or_create_token().await?;
    let addr = bind_with_fallback(host, port).await?;
    let listener = TcpListener::bind(addr).await?;
    let actual_addr = listener.local_addr()?;
    let bridge_state = BridgeState { tracker, token };
    let app = Router::new()
        .route("/", get(ws_handler))
        .with_state(bridge_state);
    let task = tokio::spawn(async move {
        if let Err(exc) = axum::serve(listener, app.into_make_service()).await {
            tracing::error!(error = %exc, "browser bridge stopped with error");
        }
    });
    Ok(BrowserBridgeHandle {
        addr: actual_addr,
        token_path,
        task,
    })
}

async fn ws_handler(ws: WebSocketUpgrade, State(state): State<BridgeState>) -> impl IntoResponse {
    ws.on_upgrade(move |socket| bridge_client(socket, state))
}

async fn bridge_client(mut socket: WebSocket, state: BridgeState) {
    let Some(Ok(Message::Text(raw))) = socket.next().await else {
        return;
    };
    let Ok(auth) = serde_json::from_str::<AuthMessage>(&raw) else {
        let _ = socket.close().await;
        return;
    };
    if auth.token != state.token {
        let _ = socket.close().await;
        return;
    }

    while let Some(msg) = socket.next().await {
        match msg {
            Ok(Message::Text(raw)) => {
                if state.tracker.is_paused() {
                    continue;
                }
                if let Ok(update) = serde_json::from_str::<TabUpdate>(&raw) {
                    if update.message_type == "tab_update" {
                        state.tracker.update_browser_tab(update.into_tab()).await;
                    }
                }
            }
            Ok(Message::Close(_)) | Err(_) => break,
            _ => {}
        }
    }
}

#[derive(Debug, Deserialize)]
struct AuthMessage {
    token: String,
}

#[derive(Debug, Deserialize)]
struct TabUpdate {
    #[serde(rename = "type")]
    message_type: String,
    browser: Option<String>,
    pid: Option<u32>,
    #[serde(rename = "windowId")]
    window_id: Option<i64>,
    #[serde(rename = "tabId")]
    tab_id: Option<i64>,
    url: Option<String>,
    title: Option<String>,
    #[serde(rename = "favIconUrl")]
    favicon_url: Option<String>,
    active: Option<bool>,
}

impl TabUpdate {
    fn into_tab(self) -> BrowserTab {
        BrowserTab {
            browser: self.browser.unwrap_or_else(|| "chrome".to_string()),
            pid: self.pid,
            window_id: self.window_id,
            tab_id: self.tab_id,
            url: self.url.unwrap_or_default(),
            title: self.title.unwrap_or_default(),
            favicon_url: self.favicon_url,
            is_active: self.active.unwrap_or(true),
        }
    }
}

async fn load_or_create_token() -> anyhow::Result<(PathBuf, String)> {
    let dir = dirs::home_dir()
        .ok_or_else(|| anyhow!("home directory not available"))?
        .join(".active_tracker");
    fs::create_dir_all(&dir).await?;
    let path = dir.join("token");
    if path.exists() {
        let token = fs::read_to_string(&path).await?.trim().to_string();
        if !token.is_empty() {
            return Ok((path, token));
        }
    }
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    let token = BASE64_URL_SAFE_NO_PAD.encode(bytes);
    fs::write(&path, &token).await?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(&path).await?.permissions();
        perms.set_mode(0o600);
        fs::set_permissions(&path, perms).await?;
    }
    Ok((path, token))
}

async fn bind_with_fallback(host: &str, port: u16) -> anyhow::Result<SocketAddr> {
    let ip: IpAddr = host
        .parse()
        .with_context(|| format!("invalid bind host: {host}"))?;
    for candidate in port..=port.saturating_add(PORT_FALLBACK_RANGE) {
        let addr = SocketAddr::new(ip, candidate);
        if TcpListener::bind(addr).await.is_ok() {
            return Ok(addr);
        }
    }
    Err(anyhow!(
        "no free port from {port} to {}",
        port.saturating_add(PORT_FALLBACK_RANGE)
    ))
}
