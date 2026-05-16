use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

pub fn now_ts() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or_default()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WindowGeometry {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
    pub screen_index: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DocumentSource {
    pub path: String,
    pub kind: String,
    pub source: String,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
    pub executable: Option<String>,
    pub cmdline: Vec<String>,
    pub cwd: Option<String>,
    pub username: Option<String>,
    pub create_time: Option<f64>,
    pub cpu_percent: Option<f32>,
    pub memory_rss: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BrowserTab {
    pub browser: String,
    pub pid: Option<u32>,
    pub window_id: Option<i64>,
    pub tab_id: Option<i64>,
    pub url: String,
    pub title: String,
    pub favicon_url: Option<String>,
    pub is_active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FileManagerWindow {
    pub folder: String,
    pub selected_items: Vec<String>,
    pub hwnd_or_id: Option<String>,
    pub is_active: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FileManagerState {
    pub source: String,
    pub windows: Vec<FileManagerWindow>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TerminalProcess {
    pub pid: u32,
    pub name: String,
    pub cwd: Option<String>,
    pub cmdline: Vec<String>,
    pub cmdline_redacted: bool,
    pub create_time: Option<f64>,
    pub is_shell: bool,
    pub cwd_source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TerminalContext {
    pub source: String,
    pub shells: Vec<TerminalProcess>,
    pub running: Vec<TerminalProcess>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WindowInfo {
    pub timestamp: f64,
    pub platform: String,
    pub app_name: String,
    pub app_bundle_id: Option<String>,
    pub window_title: String,
    pub window_id: Option<String>,
    pub window_class: Option<String>,
    pub geometry: Option<WindowGeometry>,
    pub process: Option<ProcessInfo>,
    pub document_paths: Vec<DocumentSource>,
    pub browser_tab: Option<BrowserTab>,
    pub file_manager_state: Option<FileManagerState>,
    pub terminal_context: Option<TerminalContext>,
    pub extra: serde_json::Value,
    pub errors: Vec<String>,
}

impl Default for WindowInfo {
    fn default() -> Self {
        Self {
            timestamp: now_ts(),
            platform: std::env::consts::OS.to_string(),
            app_name: String::new(),
            app_bundle_id: None,
            window_title: String::new(),
            window_id: None,
            window_class: None,
            geometry: None,
            process: None,
            document_paths: Vec::new(),
            browser_tab: None,
            file_manager_state: None,
            terminal_context: None,
            extra: serde_json::json!({}),
            errors: Vec::new(),
        }
    }
}

impl WindowInfo {
    pub fn identity_key(&self) -> String {
        let geom = self
            .geometry
            .as_ref()
            .map(|g| format!("{},{},{},{}", g.x, g.y, g.width, g.height))
            .unwrap_or_default();
        let docs = self
            .document_paths
            .iter()
            .map(|d| d.path.as_str())
            .collect::<Vec<_>>()
            .join("|");
        format!(
            "{}\u{1f}{}\u{1f}{}\u{1f}{}\u{1f}{}",
            self.app_name,
            self.window_id.as_deref().unwrap_or_default(),
            self.window_title,
            geom,
            docs
        )
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ActivityStats {
    pub timestamp: f64,
    pub window_seconds: u64,
    pub keys_count: u64,
    pub clicks_count: u64,
    pub mouse_distance_px: f64,
    pub scrolls_count: u64,
    pub idle_seconds: f64,
}

impl Default for ActivityStats {
    fn default() -> Self {
        Self {
            timestamp: now_ts(),
            window_seconds: 60,
            keys_count: 0,
            clicks_count: 0,
            mouse_distance_px: 0.0,
            scrolls_count: 0,
            idle_seconds: 0.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Snapshot {
    pub window: Option<WindowInfo>,
    pub activity: Option<ActivityStats>,
    pub browser_tab: Option<BrowserTab>,
    pub has_screenshot: bool,
    pub paused: bool,
    pub capture_enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrackerEvent {
    #[serde(rename = "type")]
    pub event_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
}

impl TrackerEvent {
    pub fn new<T: Serialize>(event_type: &str, data: &T) -> Self {
        Self {
            event_type: event_type.to_string(),
            data: serde_json::to_value(data).ok(),
        }
    }

    pub fn signal(event_type: &str) -> Self {
        Self {
            event_type: event_type.to_string(),
            data: None,
        }
    }
}
