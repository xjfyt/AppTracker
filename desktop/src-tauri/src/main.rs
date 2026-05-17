use tracker_core::{diagnostics, start_agent, AgentConfig};

fn main() {
    diagnostics::install_panic_hook();
    tracing_subscriber::fmt()
        .with_env_filter(
            std::env::var("RUST_LOG")
                .unwrap_or_else(|_| "tracker_core=info,apptracker=info".to_string()),
        )
        .try_init()
        .ok();

    tauri::Builder::default()
        .setup(|_app| {
            tauri::async_runtime::spawn(async move {
                match start_agent(AgentConfig::default()).await {
                    Ok(handle) => {
                        tracing::info!(
                            addr = %handle.api.addr,
                            bridge_token_path = %handle.api.bridge_token_path.display(),
                            "AppTracker started"
                        );
                        std::future::pending::<()>().await;
                    }
                    Err(exc) => {
                        tracing::error!(error = %exc, "failed to start AppTracker core");
                    }
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
