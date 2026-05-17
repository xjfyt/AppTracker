use tracker_core::integrations::enrich_window;
use tracker_core::models::{ProcessInfo, WindowInfo};

#[tokio::main]
async fn main() {
    let info = WindowInfo {
        app_bundle_id: Some("com.apple.finder".to_string()),
        app_name: "Finder".to_string(),
        platform: "darwin".to_string(),
        process: Some(ProcessInfo {
            pid: 718,
            name: "Finder".to_string(),
            ..Default::default()
        }),
        ..Default::default()
    };
    let enriched = enrich_window(info).await;
    println!("docs:");
    for d in &enriched.document_paths {
        println!("  {:.2} [{}] {}", d.confidence, d.source, d.path);
    }
    println!("file_manager_state: {:?}", enriched.file_manager_state);
}
