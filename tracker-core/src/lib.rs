#[cfg(feature = "activity")]
pub mod activity;
pub mod agent;
pub mod api;
pub mod bridge;
#[cfg(feature = "capture")]
pub mod capture;
pub mod diagnostics;
pub mod integrations;
pub mod models;
pub mod platform;
pub mod state;
pub mod tools;

#[cfg(not(feature = "activity"))]
pub mod activity {
    use crate::state::TrackerState;

    pub fn spawn_activity_monitor(_state: TrackerState, _window_seconds: u64) {}
}

#[cfg(not(feature = "capture"))]
pub mod capture {
    use crate::state::TrackerState;

    pub fn spawn_screen_capture(_state: TrackerState) {}
}

pub use agent::{start_agent, AgentConfig, AgentHandle};
pub use state::TrackerState;
