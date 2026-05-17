//! Linux DBus / AT-SPI integration.
//!
//! Why AT-SPI (and not, say, `org.freedesktop.FileManager1`):
//! `FileManager1` only exposes *commands* like `ShowFolders` to open file
//! managers — it has no methods to *query* the current state. Asking "what
//! folder is Nautilus showing right now?" requires accessibility introspection,
//! which on Linux means AT-SPI 2.
//!
//! AT-SPI is itself a separate DBus bus reached by asking the session bus for
//! its address via `org.a11y.Bus`. Each application registers itself on the
//! a11y bus as a top-level `Accessible` whose `Id` exposes the pid. Walking
//! children gives us frames, text inputs, document panes, etc.
//!
//! Scope: minimal, defensive. If the a11y bus isn't running, or the target
//! app doesn't publish accessibility info (common for Electron apps + many
//! Qt apps without `QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`), we return None and
//! callers fall back to /proc/PID/fd + title parsing.

#![cfg(target_os = "linux")]

use crate::models::{
    DocumentCategory, DocumentSource, FileManagerState, FileManagerWindow, WindowInfo,
};
use std::time::Duration;
use zbus::names::OwnedBusName;
use zbus::zvariant::OwnedObjectPath;
use zbus::{proxy, Connection};

const A11Y_REGISTRY_NAME: &str = "org.a11y.atspi.Registry";
const A11Y_REGISTRY_PATH: &str = "/org/a11y/atspi/accessible/root";
const WALK_NODE_CAP: usize = 400;
const PER_CALL_TIMEOUT: Duration = Duration::from_millis(200);

#[proxy(
    interface = "org.a11y.Bus",
    default_service = "org.a11y.Bus",
    default_path = "/org/a11y/bus"
)]
trait A11yBus {
    fn get_address(&self) -> zbus::Result<String>;
}

#[proxy(interface = "org.a11y.atspi.Accessible")]
trait Accessible {
    fn get_children(&self) -> zbus::Result<Vec<(OwnedBusName, OwnedObjectPath)>>;
}

#[proxy(
    interface = "org.a11y.atspi.Application",
    default_path = "/org/a11y/atspi/accessible/root"
)]
trait Application {
    #[zbus(property)]
    fn id(&self) -> zbus::Result<i32>;
}

#[proxy(interface = "org.a11y.atspi.Text")]
trait AtspiText {
    fn get_text(&self, start: i32, end: i32) -> zbus::Result<String>;
    fn get_character_count(&self) -> zbus::Result<i32>;
}

#[proxy(interface = "org.a11y.atspi.Document")]
trait Document {
    fn get_attribute_value(&self, name: &str) -> zbus::Result<String>;
}

async fn a11y_connection() -> Option<Connection> {
    let session = Connection::session().await.ok()?;
    let bus = A11yBusProxy::new(&session).await.ok()?;
    let addr = tokio::time::timeout(Duration::from_millis(700), bus.get_address())
        .await
        .ok()?
        .ok()?;
    if addr.is_empty() {
        return None;
    }
    zbus::connection::Builder::address(addr.as_str())
        .ok()?
        .build()
        .await
        .ok()
}

async fn accessible<'c>(
    conn: &'c Connection,
    service: OwnedBusName,
    path: OwnedObjectPath,
) -> Option<AccessibleProxy<'c>> {
    AccessibleProxy::builder(conn)
        .destination(service)
        .ok()?
        .path(path)
        .ok()?
        .build()
        .await
        .ok()
}

async fn text_iface<'c>(
    conn: &'c Connection,
    service: OwnedBusName,
    path: OwnedObjectPath,
) -> Option<AtspiTextProxy<'c>> {
    AtspiTextProxy::builder(conn)
        .destination(service)
        .ok()?
        .path(path)
        .ok()?
        .build()
        .await
        .ok()
}

async fn application<'c>(
    conn: &'c Connection,
    service: OwnedBusName,
    path: OwnedObjectPath,
) -> Option<ApplicationProxy<'c>> {
    ApplicationProxy::builder(conn)
        .destination(service)
        .ok()?
        .path(path)
        .ok()?
        .build()
        .await
        .ok()
}

async fn find_application_by_pid(
    conn: &Connection,
    pid: u32,
) -> Option<(OwnedBusName, OwnedObjectPath)> {
    let registry_name = OwnedBusName::try_from(A11Y_REGISTRY_NAME).ok()?;
    let registry_path = OwnedObjectPath::try_from(A11Y_REGISTRY_PATH).ok()?;
    let registry = accessible(conn, registry_name, registry_path).await?;
    let apps = tokio::time::timeout(Duration::from_millis(800), registry.get_children())
        .await
        .ok()?
        .ok()?;
    for (service, path) in apps {
        let app = application(conn, service.clone(), path.clone()).await?;
        if let Ok(id) = app.id().await {
            if id as u32 == pid {
                return Some((service, path));
            }
        }
    }
    None
}

fn looks_like_path(s: &str) -> bool {
    if s.is_empty() || s.len() > 1024 {
        return false;
    }
    if s.starts_with("~/") {
        return true;
    }
    if !s.starts_with('/') {
        return false;
    }
    // /usr, /tmp, /etc, etc. are noise — only accept paths that actually
    // resolve, or look like a user-meaningful root.
    std::path::Path::new(s).exists()
        || s.starts_with("/home/")
        || s.starts_with("/mnt/")
        || s.starts_with("/media/")
}

async fn collect_path_texts(
    conn: &Connection,
    service: OwnedBusName,
    root: OwnedObjectPath,
) -> Vec<String> {
    let mut out = Vec::new();
    let mut stack: Vec<OwnedObjectPath> = vec![root];
    let mut visited = 0usize;
    while let Some(node_path) = stack.pop() {
        if visited >= WALK_NODE_CAP {
            tracing::debug!(service = %service.as_str(), "atspi: walk cap reached");
            break;
        }
        visited += 1;
        // Text content
        if let Some(text) = text_iface(conn, service.clone(), node_path.clone()).await {
            if let Ok(Ok(len)) =
                tokio::time::timeout(PER_CALL_TIMEOUT, text.get_character_count()).await
            {
                if len > 0 && len < 4096 {
                    if let Ok(Ok(s)) =
                        tokio::time::timeout(PER_CALL_TIMEOUT, text.get_text(0, len)).await
                    {
                        let trimmed = s.trim();
                        if looks_like_path(trimmed) {
                            out.push(crate::tools::expand_user(trimmed));
                        }
                    }
                }
            }
        }
        // Children
        if let Some(acc) = accessible(conn, service.clone(), node_path.clone()).await {
            if let Ok(Ok(children)) =
                tokio::time::timeout(PER_CALL_TIMEOUT, acc.get_children()).await
            {
                for (_svc, child_path) in children {
                    stack.push(child_path);
                }
            }
        }
    }
    out
}

pub async fn file_manager_state(info: &WindowInfo) -> Option<FileManagerState> {
    let pid = info.process.as_ref()?.pid;
    let conn = a11y_connection().await?;
    let (service, root) = find_application_by_pid(&conn, pid).await?;
    let texts = collect_path_texts(&conn, service, root).await;
    let mut folder: Option<String> = None;
    let mut selected: Vec<String> = Vec::new();
    for t in texts {
        let path = std::path::Path::new(&t);
        if path.is_dir() && folder.is_none() {
            folder = Some(t.clone());
        } else if path.is_file() {
            selected.push(t);
        }
    }
    let folder = folder?;
    Some(FileManagerState {
        source: "atspi_walk".to_string(),
        windows: vec![FileManagerWindow {
            folder,
            selected_items: selected,
            hwnd_or_id: info.window_id.clone(),
            is_active: true,
        }],
    })
}

/// Try AT-SPI's `Document` interface on the focused frame. LibreOffice and a
/// few others expose `DocURL`. Returns at most one entry.
pub async fn document_url_for(info: &WindowInfo) -> Vec<DocumentSource> {
    let Some(pid) = info.process.as_ref().map(|p| p.pid) else {
        return Vec::new();
    };
    let Some(conn) = a11y_connection().await else {
        return Vec::new();
    };
    let Some((service, root)) = find_application_by_pid(&conn, pid).await else {
        return Vec::new();
    };
    let proxy = match DocumentProxy::builder(&conn)
        .destination(service)
        .and_then(|b| b.path(root))
    {
        Ok(b) => b.build().await.ok(),
        Err(_) => None,
    };
    let Some(proxy) = proxy else {
        return Vec::new();
    };
    let url = tokio::time::timeout(PER_CALL_TIMEOUT, proxy.get_attribute_value("DocURL"))
        .await
        .ok()
        .and_then(|r| r.ok())
        .unwrap_or_default();
    if url.is_empty() {
        return Vec::new();
    }
    let mut out = Vec::new();
    if let Some(doc) = crate::tools::document_from_existing_path(
        &url,
        "atspi:document",
        0.95,
        DocumentCategory::User,
    ) {
        out.push(doc);
    }
    out
}
