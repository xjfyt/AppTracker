use clap::Parser;
use tracker_core::{start_agent, AgentConfig};

#[derive(Debug, Parser)]
#[command(name = "apptracker-agent")]
#[command(about = "Headless AppTracker agent exposing REST/SSE/WebSocket APIs")]
struct Args {
    #[arg(long, default_value = "127.0.0.1")]
    api_host: String,
    #[arg(long, default_value_t = 5007)]
    api_port: u16,
    #[arg(long, default_value_t = 5006)]
    browser_port: u16,
    #[arg(long)]
    no_activity: bool,
    #[arg(long)]
    no_capture: bool,
    #[arg(long)]
    capture_default_on: bool,
    #[arg(long)]
    no_browser_bridge: bool,
    #[arg(long, default_value_t = 250)]
    poll_interval_ms: u64,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            std::env::var("RUST_LOG")
                .unwrap_or_else(|_| "tracker_core=info,tracker_agent=info".to_string()),
        )
        .init();

    let args = Args::parse();
    let handle = start_agent(AgentConfig {
        host: args.api_host,
        api_port: args.api_port,
        browser_port: args.browser_port,
        no_activity: args.no_activity,
        no_capture: args.no_capture,
        capture_default_on: args.capture_default_on,
        no_browser_bridge: args.no_browser_bridge,
        poll_interval_ms: args.poll_interval_ms,
    })
    .await?;

    println!("AppTracker API: http://{}", handle.api.addr);
    if let Some(bridge) = &handle.browser_bridge {
        println!(
            "Browser bridge: ws://{} (token: {})",
            bridge.addr,
            bridge.token_path.display()
        );
    }
    println!("Press Ctrl+C to exit.");
    tokio::signal::ctrl_c().await?;
    Ok(())
}
