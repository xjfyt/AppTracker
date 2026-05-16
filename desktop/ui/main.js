let apiBase = document.querySelector("#apiBase").value.replace(/\/$/, "");
let paused = false;
let ws = null;

const statusEl = document.querySelector("#status");
const pauseBtn = document.querySelector("#pauseBtn");
const screenshotEl = document.querySelector("#screenshot");

document.querySelector("#apiBase").addEventListener("change", (ev) => {
  apiBase = ev.target.value.replace(/\/$/, "");
  connect();
});

pauseBtn.addEventListener("click", async () => {
  paused = !paused;
  await fetch(`${apiBase}/api/v1/pause`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ paused })
  }).catch(() => {});
  renderPaused();
});

function renderPaused() {
  pauseBtn.textContent = paused ? "恢复" : "暂停";
  pauseBtn.classList.toggle("paused", paused);
}

async function loadSnapshot() {
  const res = await fetch(`${apiBase}/api/v1/snapshot`);
  const snap = await res.json();
  paused = !!snap.paused;
  renderPaused();
  renderSnapshot(snap);
}

function connect() {
  if (ws) {
    try { ws.close(); } catch {}
  }
  statusEl.textContent = "connecting";
  statusEl.classList.remove("ok");
  loadSnapshot().catch(() => {});
  const wsUrl = apiBase.replace(/^http/, "ws") + "/api/v1/ws";
  ws = new WebSocket(wsUrl);
  ws.onopen = () => {
    statusEl.textContent = "connected";
    statusEl.classList.add("ok");
    ws.send("snapshot");
  };
  ws.onclose = () => {
    statusEl.textContent = "disconnected";
    statusEl.classList.remove("ok");
    setTimeout(connect, 2000);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "snapshot") renderSnapshot(msg.data);
    if (msg.type === "window_changed") renderWindow(msg.data);
    if (msg.type === "activity_updated") renderActivity(msg.data);
    if (msg.type === "browser_tab_updated") renderBrowser(msg.data);
    if (msg.type === "screenshot_ready") refreshScreenshot();
    if (msg.type === "paused_changed") {
      paused = !!msg.data;
      renderPaused();
    }
  };
}

function renderSnapshot(snap) {
  if (snap.window) renderWindow(snap.window);
  if (snap.activity) renderActivity(snap.activity);
  if (snap.browser_tab) renderBrowser(snap.browser_tab);
  if (snap.has_screenshot) refreshScreenshot();
}

function renderWindow(win) {
  const process = win.process || {};
  const geometry = win.geometry
    ? `${win.geometry.x}, ${win.geometry.y}, ${win.geometry.width}x${win.geometry.height}`
    : "未知";
  renderGrid("#windowGrid", [
    ["应用", win.app_name || "未知"],
    ["标题", win.window_title || "无标题"],
    ["平台", win.platform || ""],
    ["窗口 ID", win.window_id || ""],
    ["类 / Bundle", win.window_class || win.app_bundle_id || ""],
    ["几何", geometry],
    ["PID", process.pid || ""],
    ["进程", process.name || ""],
    ["可执行文件", process.executable || ""],
    ["cwd", process.cwd || ""],
    ["错误", (win.errors || []).join("; ")]
  ]);
  renderDocuments(win.document_paths || []);
  renderTerminal(win.terminal_context);
  renderFiles(win.file_manager_state);
}

function renderGrid(selector, rows) {
  const el = document.querySelector(selector);
  el.innerHTML = rows.map(([k, v]) => `
    <div class="key">${escapeHtml(k)}</div>
    <div class="value">${escapeHtml(String(v || ""))}</div>
  `).join("");
}

function renderDocuments(docs) {
  const el = document.querySelector("#documents");
  if (!docs.length) {
    el.className = "list empty";
    el.textContent = "暂无路径";
    return;
  }
  el.className = "list";
  el.innerHTML = docs.map((d) => `
    <div class="item">
      <div class="mono">${escapeHtml(d.path)}</div>
      <div>${escapeHtml(d.kind)} · ${escapeHtml(d.source)} · ${Number(d.confidence).toFixed(2)}</div>
    </div>
  `).join("");
}

function renderActivity(stats) {
  document.querySelector("#activity").innerHTML = [
    ["keys", stats.keys_count],
    ["clicks", stats.clicks_count],
    ["scrolls", stats.scrolls_count],
    ["idle", `${Number(stats.idle_seconds).toFixed(1)}s`]
  ].map(([k, v]) => `<div class="metric"><strong>${escapeHtml(String(v))}</strong>${escapeHtml(k)}</div>`).join("");
}

function renderBrowser(tab) {
  const el = document.querySelector("#browser");
  if (!tab) {
    el.className = "list empty";
    el.textContent = "等待浏览器扩展连接";
    return;
  }
  el.className = "list";
  el.innerHTML = `
    <div class="item">
      <strong>${escapeHtml(tab.browser)}</strong>
      <div>${escapeHtml(tab.title || "")}</div>
      <div class="mono">${escapeHtml(tab.url || "")}</div>
    </div>
  `;
}

function renderTerminal(ctx) {
  const el = document.querySelector("#terminal");
  if (!ctx || (!ctx.shells?.length && !ctx.running?.length)) {
    el.className = "list empty";
    el.textContent = "未识别到终端上下文";
    return;
  }
  el.className = "list";
  const rows = [...(ctx.shells || []), ...(ctx.running || [])];
  el.innerHTML = rows.map((p) => `
    <div class="item">
      <strong>${escapeHtml(p.name)} (${p.pid})</strong>
      <div class="mono">${escapeHtml(p.cwd || "")}</div>
      <div class="mono">${escapeHtml((p.cmdline || []).join(" "))}</div>
    </div>
  `).join("");
}

function renderFiles(state) {
  const el = document.querySelector("#files");
  if (!state || !state.windows?.length) {
    el.className = "list empty";
    el.textContent = "未识别到文件管理器状态";
    return;
  }
  el.className = "list";
  el.innerHTML = state.windows.map((w) => `
    <div class="item">
      <strong>${w.is_active ? "当前" : "窗口"}</strong>
      <div class="mono">${escapeHtml(w.folder)}</div>
      ${(w.selected_items || []).map((s) => `<div class="mono">selected: ${escapeHtml(s)}</div>`).join("")}
    </div>
  `).join("");
}

function refreshScreenshot() {
  screenshotEl.src = `${apiBase}/api/v1/screenshot?t=${Date.now()}`;
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[ch]);
}

connect();

