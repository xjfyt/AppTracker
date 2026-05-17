use crate::models::{now_ts, BrowserTab, TrackerEvent};
use crate::state::TrackerState;
use anyhow::{anyhow, Context};
use async_stream::stream;
use axum::body::Body;
use axum::extract::ws::{Message, WebSocket};
use axum::extract::{State, WebSocketUpgrade};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use futures_util::StreamExt;
use serde::Deserialize;
use std::convert::Infallible;
use std::net::{IpAddr, SocketAddr};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::sync::broadcast;
use tokio::task::JoinHandle;
use tower_http::cors::CorsLayer;

const PORT_FALLBACK_RANGE: u16 = 5;

#[derive(Debug)]
pub struct ServerHandle {
    pub addr: SocketAddr,
    pub bridge_token: Arc<String>,
    pub bridge_token_path: PathBuf,
    pub task: JoinHandle<()>,
}

#[derive(Clone)]
pub(crate) struct ApiState {
    pub tracker: TrackerState,
    pub bridge_token: Arc<String>,
}

pub async fn spawn_api(
    state: TrackerState,
    host: &str,
    port: u16,
    bridge_token: Arc<String>,
    bridge_token_path: PathBuf,
) -> anyhow::Result<ServerHandle> {
    let addr = bind_with_fallback(host, port).await?;
    let api_state = ApiState {
        tracker: state,
        bridge_token: bridge_token.clone(),
    };
    let app = router(api_state);
    let listener = TcpListener::bind(addr)
        .await
        .with_context(|| format!("bind API listener on {addr}"))?;
    let actual_addr = listener.local_addr()?;
    let task = tokio::spawn(async move {
        if let Err(exc) = axum::serve(listener, app.into_make_service()).await {
            tracing::error!(error = %exc, "API server stopped with error");
        }
    });
    Ok(ServerHandle {
        addr: actual_addr,
        bridge_token,
        bridge_token_path,
        task,
    })
}

fn router(state: ApiState) -> Router {
    Router::new()
        .route("/api/v1/health", get(health))
        .route("/api/v1/snapshot", get(snapshot))
        .route("/api/v1/screenshot", get(screenshot))
        .route("/api/v1/events", get(events_sse))
        .route("/api/v1/ws", get(events_ws))
        .route("/api/v1/browser", get(browser_ws))
        .route("/api/v1/bridge_token", get(bridge_token_handler))
        .route("/api/v1/pause", get(pause_status).post(set_pause))
        .route("/api/v1/capture", get(capture_status).post(set_capture))
        .route(
            "/api/v1/show_process_paths",
            get(show_process_paths_status).post(set_show_process_paths),
        )
        .layer(CorsLayer::permissive())
        .with_state(state)
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"ok": true, "service": "apptracker"}))
}

async fn snapshot(State(state): State<ApiState>) -> Json<crate::models::Snapshot> {
    Json(state.tracker.snapshot().await)
}

async fn screenshot(State(state): State<ApiState>) -> Response {
    match state.tracker.latest_screenshot().await {
        Some(png) => {
            let mut headers = HeaderMap::new();
            headers.insert(header::CONTENT_TYPE, HeaderValue::from_static("image/png"));
            (headers, Body::from(png)).into_response()
        }
        None => (StatusCode::NOT_FOUND, "no screenshot yet").into_response(),
    }
}

async fn events_sse(
    State(state): State<ApiState>,
) -> Sse<impl futures_util::Stream<Item = Result<Event, Infallible>>> {
    let mut rx = state.tracker.subscribe();
    let events = stream! {
        loop {
            match rx.recv().await {
                Ok(event) => {
                    let mut sse = Event::default().event(event.event_type.clone());
                    match serde_json::to_string(&event) {
                        Ok(json) => {
                            sse = sse.data(json);
                            yield Ok(sse);
                        }
                        Err(exc) => {
                            tracing::debug!(error = %exc, "failed to serialize SSE event");
                        }
                    }
                }
                Err(broadcast::error::RecvError::Lagged(skipped)) => {
                    tracing::warn!(skipped, "SSE client lagged behind");
                }
                Err(broadcast::error::RecvError::Closed) => break,
            }
        }
    };
    Sse::new(events).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(25))
            .text("keepalive"),
    )
}

async fn events_ws(ws: WebSocketUpgrade, State(state): State<ApiState>) -> impl IntoResponse {
    ws.on_upgrade(move |socket| ws_client(socket, state.tracker.clone()))
}

async fn ws_client(mut socket: WebSocket, state: TrackerState) {
    let mut rx = state.subscribe();
    loop {
        tokio::select! {
            event = rx.recv() => {
                match event {
                    Ok(event) => {
                        if send_json(&mut socket, &event).await.is_err() {
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(broadcast::error::RecvError::Closed) => break,
                }
            }
            incoming = socket.next() => {
                match incoming {
                    Some(Ok(Message::Text(text))) => {
                        if text == "snapshot" {
                            let snap = state.snapshot().await;
                            let event = TrackerEvent::new("snapshot", &snap);
                            if send_json(&mut socket, &event).await.is_err() {
                                break;
                            }
                        } else if text == "pause" {
                            state.set_paused(true);
                        } else if text == "resume" {
                            state.set_paused(false);
                        } else {
                            let event = TrackerEvent {
                                event_type: "ack".to_string(),
                                data: Some(serde_json::json!({"echo": text.to_string()})),
                            };
                            if send_json(&mut socket, &event).await.is_err() {
                                break;
                            }
                        }
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    Some(Ok(_)) => {}
                    Some(Err(_)) => break,
                }
            }
        }
    }
}

async fn browser_ws(ws: WebSocketUpgrade, State(state): State<ApiState>) -> impl IntoResponse {
    ws.on_upgrade(move |socket| browser_client(socket, state))
}

async fn browser_client(mut socket: WebSocket, state: ApiState) {
    use futures_util::SinkExt;

    let Some(Ok(Message::Text(raw))) = socket.next().await else {
        return;
    };
    let Ok(auth) = serde_json::from_str::<AuthMessage>(&raw) else {
        let _ = socket.close().await;
        return;
    };
    if auth.token.trim() != state.bridge_token.as_str() {
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

async fn bridge_token_handler(State(state): State<ApiState>) -> Json<serde_json::Value> {
    Json(serde_json::json!({ "token": state.bridge_token.as_str() }))
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
            updated_at: now_ts(),
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

async fn send_json(socket: &mut WebSocket, event: &TrackerEvent) -> anyhow::Result<()> {
    let json = serde_json::to_string(event)?;
    socket
        .send(Message::Text(json.into()))
        .await
        .map_err(|exc| anyhow!(exc))
}

async fn pause_status(State(state): State<ApiState>) -> Json<serde_json::Value> {
    Json(serde_json::json!({"paused": state.tracker.is_paused()}))
}

#[derive(Debug, Deserialize)]
struct PauseBody {
    paused: bool,
}

async fn set_pause(
    State(state): State<ApiState>,
    Json(body): Json<PauseBody>,
) -> Json<serde_json::Value> {
    state.tracker.set_paused(body.paused);
    Json(serde_json::json!({"paused": body.paused}))
}

async fn capture_status(State(state): State<ApiState>) -> Json<serde_json::Value> {
    Json(serde_json::json!({"enabled": state.tracker.is_capture_enabled()}))
}

#[derive(Debug, Deserialize)]
struct CaptureBody {
    enabled: bool,
}

async fn set_capture(
    State(state): State<ApiState>,
    Json(body): Json<CaptureBody>,
) -> Json<serde_json::Value> {
    state.tracker.set_capture_enabled(body.enabled);
    if !body.enabled {
        state.tracker.clear_screenshot().await;
    }
    Json(serde_json::json!({"enabled": body.enabled}))
}

async fn show_process_paths_status(State(state): State<ApiState>) -> Json<serde_json::Value> {
    Json(serde_json::json!({"enabled": state.tracker.show_process_paths()}))
}

#[derive(Debug, Deserialize)]
struct ShowProcessPathsBody {
    enabled: bool,
}

async fn set_show_process_paths(
    State(state): State<ApiState>,
    Json(body): Json<ShowProcessPathsBody>,
) -> Json<serde_json::Value> {
    state.tracker.set_show_process_paths(body.enabled);
    Json(serde_json::json!({"enabled": body.enabled}))
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
