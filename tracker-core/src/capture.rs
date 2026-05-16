use crate::models::WindowInfo;
use crate::state::TrackerState;
use image::codecs::png::PngEncoder;
use image::{ColorType, ImageEncoder};
use screenshots::Screen;
use std::io::Cursor;
use std::time::Duration;

const MAX_THUMB_SIZE: u32 = 480;

pub fn spawn_screen_capture(state: TrackerState) {
    tokio::spawn(async move {
        let mut ticker = tokio::time::interval(Duration::from_secs(2));
        loop {
            ticker.tick().await;
            if state.is_paused() || !state.is_capture_enabled() {
                continue;
            }
            let Some(window) = state.current_window().await else {
                continue;
            };
            match tokio::task::spawn_blocking(move || capture_png(&window)).await {
                Ok(Ok(png)) => state.update_screenshot(png).await,
                Ok(Err(exc)) => tracing::debug!(error = %exc, "screenshot capture failed"),
                Err(exc) => tracing::debug!(error = %exc, "screenshot task join failed"),
            }
        }
    });
}

fn capture_png(info: &WindowInfo) -> anyhow::Result<Vec<u8>> {
    let img = if let Some(g) = &info.geometry {
        let width = g.width.max(1).min(4096) as u32;
        let height = g.height.max(1).min(4096) as u32;
        let screen = Screen::from_point(g.x, g.y)?;
        screen.capture_area(g.x, g.y, width, height)?
    } else {
        let screens = Screen::all()?;
        let screen = screens
            .first()
            .ok_or_else(|| anyhow::anyhow!("no screens available"))?;
        screen.capture()?
    };

    let mut dyn_img = image::DynamicImage::ImageRgba8(img);
    let (w, h) = (dyn_img.width(), dyn_img.height());
    if w > MAX_THUMB_SIZE || h > MAX_THUMB_SIZE {
        dyn_img = dyn_img.thumbnail(MAX_THUMB_SIZE, MAX_THUMB_SIZE);
    }
    let rgba = dyn_img.to_rgba8();
    let mut out = Cursor::new(Vec::new());
    PngEncoder::new(&mut out).write_image(
        rgba.as_raw(),
        rgba.width(),
        rgba.height(),
        ColorType::Rgba8.into(),
    )?;
    Ok(out.into_inner())
}
