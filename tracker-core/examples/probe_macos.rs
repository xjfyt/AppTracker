//! Probe macOS document enrichment for a specific pid.
//!
//! Usage: cargo run --example probe_macos -- <pid> <bundle> "<title>"

use tracker_core::models::{ProcessInfo, WindowInfo};
use tracker_core::platform::enrich_platform_window_documents;

#[tokio::main]
async fn main() {
    let mut args = std::env::args().skip(1);
    let pid: u32 = args.next().expect("pid required").parse().expect("pid u32");
    let bundle = args.next().unwrap_or_default();
    let title = args.next().unwrap_or_default();

    let mut info = WindowInfo {
        app_bundle_id: if bundle.is_empty() { None } else { Some(bundle) },
        window_title: title,
        process: Some(ProcessInfo {
            pid,
            ..Default::default()
        }),
        ..Default::default()
    };
    info.platform = "darwin".to_string();

    let enriched = enrich_platform_window_documents(info).await;
    println!("docs: {}", enriched.document_paths.len());
    for d in &enriched.document_paths {
        println!("  {:.2} [{}] {}", d.confidence, d.source, d.path);
    }
    if !enriched.errors.is_empty() {
        println!("errors: {:?}", enriched.errors);
    }
}
