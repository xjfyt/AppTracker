use anyhow::anyhow;
use base64::prelude::*;
use rand::RngCore;
use std::path::PathBuf;
use tokio::fs;

/// 浏览器扩展鉴权 token。第一次启动写入 `~/.apptracker/token`；
/// 若历史装的是 `~/.active_tracker/token`，会一次性迁移过来，避免老用户重新粘贴。
pub async fn load_or_create_token() -> anyhow::Result<(PathBuf, String)> {
    let home = dirs::home_dir().ok_or_else(|| anyhow!("home directory not available"))?;
    let dir = home.join(".apptracker");
    fs::create_dir_all(&dir).await?;
    let path = dir.join("token");

    if let Ok(existing) = fs::read_to_string(&path).await {
        let token = existing.trim().to_string();
        if !token.is_empty() {
            return Ok((path, token));
        }
    }

    let legacy = home.join(".active_tracker").join("token");
    if let Ok(raw) = fs::read_to_string(&legacy).await {
        let token = raw.trim().to_string();
        if !token.is_empty() {
            fs::write(&path, &token).await?;
            secure_token_file(&path).await?;
            return Ok((path, token));
        }
    }

    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    let token = BASE64_URL_SAFE_NO_PAD.encode(bytes);
    fs::write(&path, &token).await?;
    secure_token_file(&path).await?;
    Ok((path, token))
}

#[cfg(unix)]
async fn secure_token_file(path: &PathBuf) -> anyhow::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    let mut perms = fs::metadata(path).await?.permissions();
    perms.set_mode(0o600);
    fs::set_permissions(path, perms).await?;
    Ok(())
}

#[cfg(not(unix))]
async fn secure_token_file(_path: &PathBuf) -> anyhow::Result<()> {
    Ok(())
}
