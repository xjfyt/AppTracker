//! Probe the full active-window + enrich flow on whatever app is currently frontmost.
//!
//! Usage: cargo run --example probe_active

use tracker_core::integrations::enrich_window;
use tracker_core::platform::active_window;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let info = active_window().await?;
    let enriched = enrich_window(info).await;
    println!(
        "front: {} (bundle={:?}, pid={:?})",
        enriched.app_name,
        enriched.app_bundle_id,
        enriched.process.as_ref().map(|p| p.pid),
    );
    println!("title: {:?}", enriched.window_title);
    println!("docs:  {}", enriched.document_paths.len());
    for d in &enriched.document_paths {
        println!("  {:.2} [{}] {}", d.confidence, d.source, d.path);
    }
    if let Some(fm) = &enriched.file_manager_state {
        println!("file_manager ({}):", fm.source);
        for w in &fm.windows {
            println!("  active={} folder={}", w.is_active, w.folder);
        }
    }
    if !enriched.errors.is_empty() {
        println!("errors: {:?}", enriched.errors);
    }
    Ok(())
}
