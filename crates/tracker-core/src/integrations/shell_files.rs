use std::collections::HashMap;
use std::path::PathBuf;

pub fn shell_integration_dir_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../shell_integration")
        .canonicalize()
        .unwrap_or_else(|_| PathBuf::from("shell_integration"))
}

pub fn shell_cwds_dir() -> Option<PathBuf> {
    dirs::home_dir().map(|home| home.join(".active_tracker").join("shells"))
}

pub fn read_shell_cwds() -> HashMap<u32, String> {
    let Some(dir) = shell_cwds_dir() else {
        return HashMap::new();
    };
    let Ok(entries) = std::fs::read_dir(dir) else {
        return HashMap::new();
    };
    let mut out = HashMap::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) != Some("cwd") {
            continue;
        }
        let Some(pid) = path
            .file_stem()
            .and_then(|s| s.to_str())
            .and_then(|s| s.parse::<u32>().ok())
        else {
            continue;
        };
        if !pid_exists(pid) {
            let _ = std::fs::remove_file(&path);
            continue;
        }
        if let Ok(text) = std::fs::read_to_string(&path) {
            let cwd = text.trim_start_matches('\u{feff}').trim().to_string();
            if !cwd.is_empty() {
                out.insert(pid, cwd);
            }
        }
    }
    out
}

fn pid_exists(pid: u32) -> bool {
    sysinfo::System::new_all()
        .process(sysinfo::Pid::from_u32(pid))
        .is_some()
}
