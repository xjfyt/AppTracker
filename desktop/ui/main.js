let apiBase = document.querySelector("#apiBase").value.replace(/\/$/, "");
let paused = false;
let captureEnabled = false;
let showProcessPaths = false;
let ws = null;
let reconnectTimer = null;
let lastScreenshotRefresh = 0;
let latestDocuments = [];

const statusEl = document.querySelector("#status");
const pauseBtn = document.querySelector("#pauseBtn");
const captureToggle = document.querySelector("#captureToggle");
const captureBadge = document.querySelector("#captureBadge");
const screenshotEl = document.querySelector("#screenshot");
const screenshotHint = document.querySelector("#screenshotHint");
const appBadge = document.querySelector("#appBadge");
const showProcessToggle = document.querySelector("#showProcessPaths");
const lightbox = document.querySelector("#lightbox");
const lightboxImg = document.querySelector("#lightboxImg");
const lightboxClose = document.querySelector(".lightbox-close");

const htmlCache = new Map();

document.querySelector("#apiBase").addEventListener("change", (ev) => {
  apiBase = ev.target.value.replace(/\/$/, "");
  connect();
});

pauseBtn.addEventListener("click", async () => {
  paused = !paused;
  await fetch(`${apiBase}/api/v1/pause`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ paused }),
  }).catch(() => {});
  renderPaused();
});

captureToggle.addEventListener("change", async (ev) => {
  const enabled = ev.target.checked;
  await fetch(`${apiBase}/api/v1/capture`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ enabled }),
  }).catch(() => {});
  applyCaptureState(enabled);
});

showProcessToggle.addEventListener("change", async (ev) => {
  const enabled = ev.target.checked;
  await fetch(`${apiBase}/api/v1/show_process_paths`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ enabled }),
  }).catch(() => {});
  applyShowProcessPaths(enabled);
  renderDocuments(latestDocuments);
});

screenshotEl.addEventListener("dblclick", () => {
  if (!screenshotEl.src || screenshotEl.classList.contains("hidden")) return;
  lightboxImg.src = screenshotEl.src;
  lightbox.hidden = false;
});

lightbox.addEventListener("click", (ev) => {
  if (ev.target === lightbox || ev.target === lightboxClose) {
    lightbox.hidden = true;
    lightboxImg.removeAttribute("src");
  }
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && !lightbox.hidden) {
    lightbox.hidden = true;
    lightboxImg.removeAttribute("src");
  }
});

function renderPaused() {
  pauseBtn.textContent = paused ? "恢复" : "暂停";
  pauseBtn.classList.toggle("paused", paused);
}

function applyShowProcessPaths(enabled) {
  showProcessPaths = !!enabled;
  showProcessToggle.checked = showProcessPaths;
}

function applyCaptureState(enabled) {
  captureEnabled = !!enabled;
  captureToggle.checked = captureEnabled;
  if (captureEnabled) {
    captureBadge.textContent = "已开启";
    captureBadge.className = "chip chip-success";
    screenshotHint.textContent = "等待第一帧截图…双击图像可放大查看";
  } else {
    captureBadge.textContent = "未启用";
    captureBadge.className = "chip chip-muted";
    screenshotHint.textContent = "开启截图后此处会显示最新窗口截图，双击可放大";
    screenshotEl.removeAttribute("src");
    screenshotEl.classList.add("hidden");
  }
}

async function loadSnapshot() {
  const res = await fetch(`${apiBase}/api/v1/snapshot`);
  const snap = await res.json();
  paused = !!snap.paused;
  renderPaused();
  applyCaptureState(!!snap.capture_enabled);
  applyShowProcessPaths(!!snap.show_process_paths);
  renderSnapshot(snap);
}

function connect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.onclose = null;
    try { ws.close(); } catch {}
    ws = null;
  }
  statusEl.textContent = "connecting";
  statusEl.classList.remove("ok");
  loadSnapshot().catch(() => {});
  const wsUrl = apiBase.replace(/^http/, "ws") + "/api/v1/ws";
  const socket = new WebSocket(wsUrl);
  ws = socket;
  socket.onopen = () => {
    statusEl.textContent = "connected";
    statusEl.classList.add("ok");
    socket.send("snapshot");
  };
  socket.onclose = () => {
    if (ws !== socket) return;
    statusEl.textContent = "disconnected";
    statusEl.classList.remove("ok");
    reconnectTimer = setTimeout(connect, 1000);
  };
  socket.onmessage = (ev) => {
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
    if (msg.type === "capture_changed") {
      applyCaptureState(!!msg.data);
    }
    if (msg.type === "show_process_paths_changed") {
      applyShowProcessPaths(!!msg.data);
      renderDocuments(latestDocuments);
    }
  };
}

function renderSnapshot(snap) {
  if (typeof snap.capture_enabled === "boolean") applyCaptureState(snap.capture_enabled);
  if (typeof snap.show_process_paths === "boolean") applyShowProcessPaths(snap.show_process_paths);
  if (snap.window) renderWindow(snap.window);
  if (snap.activity) renderActivity(snap.activity);
  if (snap.browser_tab) renderBrowser(snap.browser_tab);
  if (snap.has_screenshot) refreshScreenshot();
}

function renderWindow(win) {
  const process = win.process || {};
  appBadge.textContent = win.app_name || "无";
  appBadge.className = win.app_name ? "chip chip-primary" : "chip chip-muted";

  const geometry = win.geometry
    ? `${win.geometry.x}, ${win.geometry.y} · ${win.geometry.width}×${win.geometry.height}`
    : "未知";

  const rows = [
    ["应用", win.app_name],
    ["标题", win.window_title || "无标题"],
    ["平台", win.platform],
    ["窗口 ID", win.window_id],
    ["类 / Bundle", win.window_class || win.app_bundle_id],
    ["几何", geometry],
    ["PID", process.pid],
    ["进程", process.name],
    ["可执行文件", process.executable],
    ["cwd", process.cwd],
    ["错误", (win.errors || []).join("; ")],
  ];

  renderGrid("#windowGrid", rows);
  renderDocuments(win.document_paths || []);
  renderTerminal(win.terminal_context);
  renderFiles(win.file_manager_state);
}

function renderGrid(selector, rows) {
  const html = rows
    .filter(([_, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `
      <div class="key">${escapeHtml(k)}</div>
      <div class="value-text">${escapeHtml(String(v))}</div>
    `)
    .join("");
  setHtml(selector, html);
}

function renderDocuments(docs) {
  latestDocuments = docs || [];
  const el = document.querySelector("#documents");
  const visible = latestDocuments.filter((d) => showProcessPaths || categoryOf(d) !== "process");
  const hiddenProcessCount = latestDocuments.length - visible.length;

  if (!visible.length) {
    el.className = "card-list empty";
    htmlCache.delete(el);
    el.textContent = hiddenProcessCount
      ? `暂无用户文档（已隐藏 ${hiddenProcessCount} 条进程上下文路径）`
      : "暂无路径";
    return;
  }
  el.className = "card-list";
  const cards = visible.map((d) => {
    const cat = categoryOf(d);
    return `
      <div class="card">
        <div class="mono">${escapeHtml(d.path)}</div>
        <div class="card-row">
          <span class="chip ${cat === "process" ? "chip-muted" : "chip-success"}">${cat === "process" ? "进程上下文" : "用户"}</span>
          <span class="chip chip-kind">${escapeHtml(d.kind)}</span>
          <span class="chip chip-source">${escapeHtml(d.source)}</span>
          <span class="chip ${confidenceChipClass(d.confidence)}">置信度 ${formatPercent(d.confidence)}</span>
        </div>
      </div>
    `;
  }).join("");
  const footer = hiddenProcessCount && !showProcessPaths
    ? `<div class="muted" style="margin-top: 4px;">已隐藏 ${hiddenProcessCount} 条进程上下文路径（cwd/启动目录）。开启右上方开关可查看。</div>`
    : "";
  setHtml(el, cards + footer);
}

function categoryOf(doc) {
  if (doc && typeof doc.category === "string") return doc.category;
  return "user";
}

function renderActivity(stats) {
  const items = [
    ["按键", stats.keys_count],
    ["点击", stats.clicks_count],
    ["滚动", stats.scrolls_count],
    ["空闲", `${Number(stats.idle_seconds || 0).toFixed(1)}s`],
  ];
  setHtml("#activity", items.map(([label, v]) => `
    <div class="metric">
      <strong>${escapeHtml(String(v))}</strong>
      <div class="metric-label">${escapeHtml(label)}</div>
    </div>
  `).join(""));
}

function renderBrowser(tab) {
  const el = document.querySelector("#browser");
  if (!tab) {
    el.className = "card-list empty";
    htmlCache.delete(el);
    el.textContent = "等待浏览器扩展连接";
    return;
  }
  el.className = "card-list";
  setHtml(el, `
    <div class="card">
      <div class="card-row">
        <span class="chip chip-primary">${escapeHtml(tab.browser)}</span>
        ${tab.is_active ? `<span class="chip chip-success">当前</span>` : ""}
      </div>
      <div class="strong">${escapeHtml(tab.title || "")}</div>
      <div class="mono">${escapeHtml(tab.url || "")}</div>
    </div>
  `);
}

function renderTerminal(ctx) {
  const el = document.querySelector("#terminal");
  if (!ctx || (!ctx.shells?.length && !ctx.running?.length)) {
    el.className = "card-list empty";
    htmlCache.delete(el);
    el.textContent = "未识别到终端上下文";
    return;
  }
  el.className = "card-list";
  const items = [
    ...(ctx.shells || []).map((p) => ({ proc: p, kind: "shell" })),
    ...(ctx.running || []).map((p) => ({ proc: p, kind: "running" })),
  ];
  setHtml(el, items.map(({ proc, kind }) => `
    <div class="card">
      <div class="card-row">
        <span class="chip ${kind === "shell" ? "chip-primary" : "chip-kind"}">${kind}</span>
        <span class="strong">${escapeHtml(proc.name)}</span>
        <span class="meta">PID ${proc.pid}</span>
      </div>
      ${proc.cwd ? `<div class="mono">${escapeHtml(proc.cwd)}</div>` : ""}
      ${proc.cmdline?.length ? `<div class="mono meta">${escapeHtml(proc.cmdline.join(" "))}</div>` : ""}
    </div>
  `).join(""));
}

function renderFiles(state) {
  const el = document.querySelector("#files");
  if (!state || !state.windows?.length) {
    el.className = "card-list empty";
    htmlCache.delete(el);
    el.textContent = "未识别到文件管理器状态";
    return;
  }
  el.className = "card-list";
  setHtml(el, state.windows.map((w) => `
    <div class="card">
      <div class="card-row">
        <span class="chip ${w.is_active ? "chip-success" : "chip-muted"}">${w.is_active ? "当前窗口" : "后台窗口"}</span>
      </div>
      <div class="mono">${escapeHtml(w.folder)}</div>
      ${(w.selected_items || []).map((s) => `<div class="card-row"><span class="chip chip-source">选中</span><span class="mono">${escapeHtml(s)}</span></div>`).join("")}
    </div>
  `).join(""));
}

function refreshScreenshot() {
  if (!captureEnabled) return;
  const now = Date.now();
  if (now - lastScreenshotRefresh < 500) return;
  lastScreenshotRefresh = now;
  screenshotEl.src = `${apiBase}/api/v1/screenshot?t=${Date.now()}`;
  screenshotEl.classList.remove("hidden");
  screenshotHint.textContent = "双击图像可放大查看";
}

function setHtml(target, html) {
  const el = typeof target === "string" ? document.querySelector(target) : target;
  if (!el) return;
  if (htmlCache.get(el) === html) return;
  htmlCache.set(el, html);
  el.innerHTML = html;
}

function formatPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

function confidenceChipClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "chip-muted";
  if (n >= 0.8) return "chip-success";
  if (n >= 0.5) return "chip-warn";
  return "chip-muted";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[ch]);
}

connect();
