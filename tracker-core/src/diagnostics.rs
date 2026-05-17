use std::io::Write;
use std::panic::PanicHookInfo;
use std::path::PathBuf;
use std::sync::Once;
use std::time::{SystemTime, UNIX_EPOCH};

/// Install a process-global panic hook that appends to ~/.active_tracker/crash.log.
/// Safe to call multiple times — the install is once-only.
pub fn install_panic_hook() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let prev = std::panic::take_hook();
        std::panic::set_hook(Box::new(move |info| {
            write_crash(info);
            prev(info);
        }));
    });
}

fn write_crash(info: &PanicHookInfo) {
    let Some(path) = crash_log_path() else {
        return;
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let bt = std::backtrace::Backtrace::force_capture();
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or_default();
    let thread = std::thread::current()
        .name()
        .unwrap_or("unnamed")
        .to_string();
    let entry = format!("==== panic @ ts={ts} thread={thread} ====\n{info}\nbacktrace:\n{bt}\n\n");
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
    {
        let _ = f.write_all(entry.as_bytes());
        let _ = f.flush();
    }
    // Mirror to stderr too — useful when running under `npm run dev` where stderr
    // is in the terminal.
    eprintln!("[apptracker] panic written to {}", path.display());
}

pub fn crash_log_path() -> Option<PathBuf> {
    Some(dirs::home_dir()?.join(".active_tracker").join("crash.log"))
}
