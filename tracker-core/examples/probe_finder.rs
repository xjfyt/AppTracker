use tracker_core::integrations::file_manager;
use tracker_core::models::{ProcessInfo, WindowInfo};

#[tokio::main]
async fn main() {
    let info = WindowInfo {
        app_bundle_id: Some("com.apple.finder".to_string()),
        app_name: "Finder".to_string(),
        process: Some(ProcessInfo {
            pid: 718,
            name: "Finder".to_string(),
            ..Default::default()
        }),
        ..Default::default()
    };
    let r = file_manager::query(&info).await;
    println!("{:#?}", r);
}
