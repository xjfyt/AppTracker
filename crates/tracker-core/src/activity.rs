use crate::models::{now_ts, ActivityStats};
use crate::state::TrackerState;
use rdev::{listen, EventType};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Debug)]
struct ActivityCounters {
    events: VecDeque<(Instant, &'static str)>,
    last_mouse_pos: Option<(f64, f64)>,
    mouse_distance: f64,
    last_input: Instant,
}

impl Default for ActivityCounters {
    fn default() -> Self {
        Self {
            events: VecDeque::new(),
            last_mouse_pos: None,
            mouse_distance: 0.0,
            last_input: Instant::now(),
        }
    }
}

pub fn spawn_activity_monitor(state: TrackerState, window_seconds: u64) {
    let counters = Arc::new(Mutex::new(ActivityCounters::default()));
    let listener_counters = counters.clone();
    std::thread::Builder::new()
        .name("activity-listener".to_string())
        .spawn(move || {
            let callback = move |event: rdev::Event| {
                if let Ok(mut counters) = listener_counters.lock() {
                    match event.event_type {
                        EventType::KeyPress(_) => {
                            counters.events.push_back((Instant::now(), "key"));
                            counters.last_input = Instant::now();
                        }
                        EventType::ButtonPress(_) => {
                            counters.events.push_back((Instant::now(), "click"));
                            counters.last_input = Instant::now();
                        }
                        EventType::Wheel { .. } => {
                            counters.events.push_back((Instant::now(), "scroll"));
                            counters.last_input = Instant::now();
                        }
                        EventType::MouseMove { x, y } => {
                            if let Some((px, py)) = counters.last_mouse_pos {
                                let dx = x - px;
                                let dy = y - py;
                                counters.mouse_distance += (dx * dx + dy * dy).sqrt();
                            }
                            counters.last_mouse_pos = Some((x, y));
                            counters.last_input = Instant::now();
                        }
                        _ => {}
                    }
                }
            };
            if let Err(exc) = listen(callback) {
                tracing::warn!(error = ?exc, "activity listener failed");
            }
        })
        .ok();

    tokio::spawn(async move {
        let mut ticker = tokio::time::interval(Duration::from_secs(1));
        loop {
            ticker.tick().await;
            let stats = {
                let mut counters = match counters.lock() {
                    Ok(c) => c,
                    Err(_) => continue,
                };
                let cutoff = Instant::now() - Duration::from_secs(window_seconds);
                while counters
                    .events
                    .front()
                    .map(|(at, _)| *at < cutoff)
                    .unwrap_or(false)
                {
                    counters.events.pop_front();
                }
                let keys = counters.events.iter().filter(|(_, k)| *k == "key").count() as u64;
                let clicks = counters
                    .events
                    .iter()
                    .filter(|(_, k)| *k == "click")
                    .count() as u64;
                let scrolls = counters
                    .events
                    .iter()
                    .filter(|(_, k)| *k == "scroll")
                    .count() as u64;
                ActivityStats {
                    timestamp: now_ts(),
                    window_seconds,
                    keys_count: keys,
                    clicks_count: clicks,
                    scrolls_count: scrolls,
                    mouse_distance_px: counters.mouse_distance,
                    idle_seconds: counters.last_input.elapsed().as_secs_f64(),
                }
            };
            if !state.is_paused() {
                state.update_activity(stats).await;
            }
        }
    });
}
