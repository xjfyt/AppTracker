use crate::models::{ActivityStats, BrowserTab, Snapshot, TrackerEvent, WindowInfo};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use tokio::sync::{broadcast, RwLock};

#[derive(Debug, Default)]
struct InnerState {
    window: Option<WindowInfo>,
    activity: Option<ActivityStats>,
    browser_tab: Option<BrowserTab>,
    latest_screenshot_png: Option<Vec<u8>>,
}

#[derive(Clone)]
pub struct TrackerState {
    inner: Arc<RwLock<InnerState>>,
    tx: broadcast::Sender<TrackerEvent>,
    paused: Arc<AtomicBool>,
}

impl TrackerState {
    pub fn new() -> Self {
        let (tx, _) = broadcast::channel(256);
        Self {
            inner: Arc::new(RwLock::new(InnerState::default())),
            tx,
            paused: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn subscribe(&self) -> broadcast::Receiver<TrackerEvent> {
        self.tx.subscribe()
    }

    pub fn is_paused(&self) -> bool {
        self.paused.load(Ordering::Relaxed)
    }

    pub fn set_paused(&self, paused: bool) {
        self.paused.store(paused, Ordering::Relaxed);
        let _ = self.tx.send(TrackerEvent::new("paused_changed", &paused));
    }

    pub async fn snapshot(&self) -> Snapshot {
        let inner = self.inner.read().await;
        Snapshot {
            window: inner.window.clone(),
            activity: inner.activity.clone(),
            browser_tab: inner.browser_tab.clone(),
            has_screenshot: inner.latest_screenshot_png.is_some(),
            paused: self.is_paused(),
        }
    }

    pub async fn current_window(&self) -> Option<WindowInfo> {
        self.inner.read().await.window.clone()
    }

    pub async fn update_window(&self, info: WindowInfo) {
        self.inner.write().await.window = Some(info.clone());
        let _ = self.tx.send(TrackerEvent::new("window_changed", &info));
    }

    pub async fn update_activity(&self, stats: ActivityStats) {
        self.inner.write().await.activity = Some(stats.clone());
        let _ = self.tx.send(TrackerEvent::new("activity_updated", &stats));
    }

    pub async fn update_browser_tab(&self, tab: BrowserTab) {
        {
            let mut inner = self.inner.write().await;
            inner.browser_tab = Some(tab.clone());
            if let Some(window) = inner.window.as_mut() {
                window.browser_tab = Some(tab.clone());
            }
        }
        let _ = self.tx.send(TrackerEvent::new("browser_tab_updated", &tab));
    }

    pub async fn update_screenshot(&self, png: Vec<u8>) {
        self.inner.write().await.latest_screenshot_png = Some(png);
        let _ = self.tx.send(TrackerEvent::signal("screenshot_ready"));
    }

    pub async fn latest_screenshot(&self) -> Option<Vec<u8>> {
        self.inner.read().await.latest_screenshot_png.clone()
    }
}

impl Default for TrackerState {
    fn default() -> Self {
        Self::new()
    }
}
