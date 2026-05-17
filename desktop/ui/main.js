const DEFAULT_API_BASE = "http://127.0.0.1:5007";
const FALLBACK_PORT_START = 5007;
const FALLBACK_PORT_END = 5012;

let apiBase = document.querySelector("#apiBase").value.replace(/\/$/, "");
let paused = false;
let captureEnabled = false;
let showProcessPaths = false;
let ws = null;
let reconnectTimer = null;
let connectGeneration = 0;
let lastScreenshotRefresh = 0;
let latestDocuments = [];
let latestWindow = null;
let latestBrowserTab = null;
let latestActivity = null;
let apiConnected = false;

const statusEl = document.querySelector("#status");
const pauseBtn = document.querySelector("#pauseBtn");
const captureToggle = document.querySelector("#captureToggle");
const captureBadge = document.querySelector("#captureBadge");
const screenshotEl = document.querySelector("#screenshot");
const screenshotHint = document.querySelector("#screenshotHint");
const appBadge = document.querySelector("#appBadge");
const showProcessToggle = document.querySelector("#showProcessPaths");
const bridgeKeyEl = document.querySelector("#bridgeKey");
const copyBridgeKeyBtn = document.querySelector("#copyBridgeKey");
const bridgeKeyHint = document.querySelector("#bridgeKeyHint");
const sideTabs = Array.from(document.querySelectorAll(".side-tab"));
const views = Array.from(document.querySelectorAll(".view"));
const diagCapabilities = document.querySelector("#diagCapabilities");
const diagErrors = document.querySelector("#diagErrors");
const lightbox = document.querySelector("#lightbox");
const lightboxImg = document.querySelector("#lightboxImg");
const lightboxClose = document.querySelector(".lightbox-close");

const htmlCache = new Map();

sideTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.view;
    sideTabs.forEach((item) => item.classList.toggle("active", item === tab));
    views.forEach((view) => view.classList.toggle("active", view.id === `view-${target}`));
    if (target === "diagnostics") renderDiagnostics();
  });
});

document.querySelector("#apiBase").addEventListener("change", (ev) => {
  setApiBase(ev.target.value);
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

copyBridgeKeyBtn.addEventListener("click", async () => {
  const key = bridgeKeyEl.value.trim();
  if (!key) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(key);
    } else {
      bridgeKeyEl.select();
      document.execCommand("copy");
      bridgeKeyEl.blur();
    }
    bridgeKeyHint.textContent = "已复制，可粘贴到浏览器插件 Token 输入框。";
  } catch (_) {
    bridgeKeyHint.textContent = "复制失败，请手动选中 Key 后复制。";
  }
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

function setApiBase(value) {
  apiBase = (value || DEFAULT_API_BASE).replace(/\/$/, "");
  const input = document.querySelector("#apiBase");
  if (input.value.replace(/\/$/, "") !== apiBase) input.value = apiBase;
}

function candidateApiBases(preferred = apiBase) {
  const bases = new Set();
  const normalized = (preferred || DEFAULT_API_BASE).replace(/\/$/, "");
  bases.add(normalized);
  try {
    const url = new URL(normalized);
    if (["127.0.0.1", "localhost"].includes(url.hostname)) {
      for (let port = FALLBACK_PORT_START; port <= FALLBACK_PORT_END; port++) {
        url.port = String(port);
        bases.add(url.toString().replace(/\/$/, ""));
      }
    }
  } catch (_) {
    for (let port = FALLBACK_PORT_START; port <= FALLBACK_PORT_END; port++) {
      bases.add(`http://127.0.0.1:${port}`);
    }
  }
  return Array.from(bases);
}

async function fetchWithTimeout(url, options = {}, ms = 700) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function discoverApiBase() {
  for (const base of candidateApiBases()) {
    try {
      const res = await fetchWithTimeout(`${base}/api/v1/health`);
      if (!res.ok) continue;
      const data = await res.json();
      if (data && data.service === "apptracker") {
        setApiBase(base);
        apiConnected = true;
        renderDiagnostics();
        return base;
      }
    } catch (_) {}
  }
  apiConnected = false;
  renderDiagnostics();
  return null;
}

async function loadBridgeKey() {
  bridgeKeyEl.value = "";
  bridgeKeyHint.textContent = "正在读取浏览器插件 Key...";
  const res = await fetch(`${apiBase}/api/v1/bridge_token`);
  if (!res.ok) throw new Error(`status ${res.status}`);
  const data = await res.json();
  bridgeKeyEl.value = data.token || "";
  bridgeKeyHint.textContent = bridgeKeyEl.value
    ? "安装浏览器插件后，可把此 Key 粘贴到插件 Token 输入框。"
    : "未读取到 Key，请确认 AppTracker 核心已启动。";
}

async function connect() {
  const generation = ++connectGeneration;
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
  const discovered = await discoverApiBase();
  if (generation !== connectGeneration) return;
  if (!discovered) {
    statusEl.textContent = "disconnected";
    bridgeKeyEl.value = "";
    bridgeKeyHint.textContent = "Key 读取失败，请确认 API 地址正确。";
    reconnectTimer = setTimeout(connect, 1000);
    return;
  }
  loadSnapshot().catch(() => {
    apiConnected = false;
    renderDiagnostics();
  });
  loadBridgeKey().catch(() => {
    bridgeKeyEl.value = "";
    bridgeKeyHint.textContent = "Key 读取失败，请确认 API 地址正确。";
  });
  const wsUrl = apiBase.replace(/^http/, "ws") + "/api/v1/ws";
  const socket = new WebSocket(wsUrl);
  ws = socket;
  socket.onopen = () => {
    apiConnected = true;
    statusEl.textContent = "connected";
    statusEl.classList.add("ok");
    renderDiagnostics();
    socket.send("snapshot");
  };
  socket.onclose = () => {
    if (ws !== socket) return;
    statusEl.textContent = "disconnected";
    statusEl.classList.remove("ok");
    apiConnected = false;
    renderDiagnostics();
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
  if (snap.activity) latestActivity = snap.activity;
  if (typeof snap.capture_enabled === "boolean") applyCaptureState(snap.capture_enabled);
  if (typeof snap.show_process_paths === "boolean") applyShowProcessPaths(snap.show_process_paths);
  if (snap.window) renderWindow(snap.window);
  if (snap.activity) renderActivity(snap.activity);
  if (snap.browser_tab) renderBrowser(snap.browser_tab);
  if (snap.has_screenshot) refreshScreenshot();
  renderDiagnostics();
}

function renderWindow(win) {
  latestWindow = win;
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
  renderBrowser(latestBrowserTab);
  renderDiagnostics();
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
  latestActivity = stats;
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
  renderDiagnostics();
}

function renderBrowser(tab) {
  latestBrowserTab = tab || latestBrowserTab;
  const el = document.querySelector("#browser");
  const current = tab || latestBrowserTab;
  if (!current) {
    el.className = "card-list empty";
    htmlCache.delete(el);
    el.textContent = "等待浏览器扩展连接";
    return;
  }
  const age = browserTabAgeSeconds(current);
  const foregroundBrowser = looksLikeBrowserWindow(latestWindow);
  const isFresh = age === null || age < 15;
  const statusChip = foregroundBrowser
    ? `<span class="chip chip-success">当前浏览器窗口</span>`
    : `<span class="chip chip-muted">最后浏览器 Tab</span>`;
  el.className = "card-list";
  setHtml(el, `
    <div class="card">
      <div class="card-row">
        <span class="chip chip-primary">${escapeHtml(current.browser)}</span>
        ${statusChip}
        <span class="chip ${isFresh ? "chip-success" : "chip-warn"}">${escapeHtml(formatAge(age))}</span>
      </div>
      <div class="strong">${escapeHtml(current.title || "")}</div>
      <div class="mono">${escapeHtml(current.url || "")}</div>
    </div>
  `);
}

function browserTabAgeSeconds(tab) {
  const updatedAt = Number(tab?.updated_at);
  if (!Number.isFinite(updatedAt) || updatedAt <= 0) return null;
  return Math.max(0, Date.now() / 1000 - updatedAt);
}

function formatAge(age) {
  if (age === null) return "刚刚更新";
  if (age < 2) return "刚刚更新";
  if (age < 60) return `${Math.round(age)} 秒前`;
  return `${Math.round(age / 60)} 分钟前`;
}

function looksLikeBrowserWindow(win) {
  if (!win) return false;
  const process = win.process || {};
  const haystack = [
    win.app_name,
    win.window_class,
    win.app_bundle_id,
    process.name,
    process.executable,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return [
    "chrome",
    "msedge",
    "microsoft edge",
    "firefox",
    "safari",
    "brave",
    "arc",
    "opera",
  ].some((needle) => haystack.includes(needle));
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

function renderDiagnostics() {
  renderGrid("#diagConnection", [
    ["API 地址", apiBase],
    ["连接状态", apiConnected ? "已连接" : "未连接"],
    ["插件 Key", bridgeKeyEl.value ? `已读取（${bridgeKeyEl.value.length} 字符）` : "未读取"],
    ["暂停", paused ? "是" : "否"],
    ["截图", captureEnabled ? "已开启" : "未启用"],
    ["进程路径", showProcessPaths ? "显示" : "隐藏"],
  ]);

  const docCount = latestDocuments.length;
  const userDocCount = latestDocuments.filter((d) => categoryOf(d) !== "process").length;
  const browserAge = browserTabAgeSeconds(latestBrowserTab);
  const errors = latestWindow?.errors || [];
  const terminal = latestWindow?.terminal_context;
  const fileManager = latestWindow?.file_manager_state;
  const capabilities = [
    capabilityCard("API", apiConnected ? "ok" : "err", apiConnected ? "HTTP / WebSocket 已连接" : "正在尝试 5007-5012 端口"),
    capabilityCard(
      "浏览器插件",
      latestBrowserTab ? (browserAge !== null && browserAge > 60 ? "warn" : "ok") : "warn",
      latestBrowserTab ? `最近 Tab 更新：${formatAge(browserAge)}` : "尚未收到浏览器插件上报"
    ),
    capabilityCard(
      "前台窗口",
      latestWindow?.app_name ? "ok" : "warn",
      latestWindow?.app_name ? `${latestWindow.app_name} / ${latestWindow.platform}` : "尚未识别到前台窗口"
    ),
    capabilityCard(
      "文档路径",
      userDocCount > 0 ? "ok" : docCount > 0 ? "warn" : "warn",
      userDocCount > 0
        ? `识别到 ${userDocCount} 条用户路径`
        : docCount > 0
          ? `只有 ${docCount} 条进程上下文路径`
          : "当前窗口未识别到文档路径"
    ),
    capabilityCard(
      "文件管理器",
      fileManager?.windows?.length ? "ok" : "warn",
      fileManager?.windows?.length ? `${fileManager.source} / ${fileManager.windows.length} 个窗口` : "当前窗口不是文件管理器或未识别"
    ),
    capabilityCard(
      "终端",
      terminal?.shells?.length || terminal?.running?.length ? "ok" : "warn",
      terminal ? `${terminal.shells?.length || 0} 个 shell，${terminal.running?.length || 0} 个运行进程` : "当前窗口不是终端或未识别"
    ),
    capabilityCard(
      "活动统计",
      latestActivity ? "ok" : "warn",
      latestActivity ? `最近 ${latestActivity.window_seconds}s：按键 ${latestActivity.keys_count}，点击 ${latestActivity.clicks_count}` : "尚未收到键鼠活动统计"
    ),
    capabilityCard(
      "平台错误",
      errors.length ? "warn" : "ok",
      errors.length ? `${errors.length} 条错误或限制提示` : "当前窗口无平台错误"
    ),
  ];
  setHtml(diagCapabilities, capabilities.join(""));

  const tips = diagnosticTips(errors);
  if (!tips.length) {
    diagErrors.className = "card-list empty";
    htmlCache.delete(diagErrors);
    diagErrors.textContent = "暂无错误";
  } else {
    diagErrors.className = "card-list";
    setHtml(diagErrors, tips.map((tip) => `
      <div class="card">
        <div class="card-row">
          <span class="chip ${tip.level === "err" ? "chip-warn" : "chip-muted"}">${escapeHtml(tip.label)}</span>
        </div>
        <div>${escapeHtml(tip.text)}</div>
      </div>
    `).join(""));
  }
}

function capabilityCard(label, state, text) {
  const chip = state === "ok" ? "chip-success" : state === "err" ? "chip-warn" : "chip-muted";
  const status = state === "ok" ? "正常" : state === "err" ? "异常" : "待确认";
  return `
    <div class="card">
      <div class="card-row">
        <span class="strong">${escapeHtml(label)}</span>
        <span class="chip ${chip}">${status}</span>
      </div>
      <div class="muted">${escapeHtml(text)}</div>
    </div>
  `;
}

function diagnosticTips(errors) {
  const tips = [];
  if (!apiConnected) {
    tips.push({ level: "err", label: "连接", text: "未连接到 AppTracker API。UI 会自动扫描 5007-5012；如果仍失败，确认桌面端核心已启动。" });
  }
  for (const err of errors) {
    tips.push({ level: "err", label: "窗口", text: err });
    if (/Wayland/i.test(err)) {
      tips.push({ level: "warn", label: "Linux", text: "Wayland 会限制通用前台窗口和截图能力；X11 会话下覆盖更稳定。" });
    }
    if (/osascript|Automation|Accessibility/i.test(err)) {
      tips.push({ level: "warn", label: "macOS", text: "请检查 Accessibility / Automation 权限，AppleScript 被系统弹窗阻塞时会影响窗口与文档识别。" });
    }
  }
  if (!latestBrowserTab) {
    tips.push({ level: "warn", label: "浏览器", text: "未收到浏览器插件上报。可复制当前页的浏览器插件 Key，粘贴到插件 Token 后保存。" });
  }
  return tips;
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
setInterval(() => {
  renderBrowser(latestBrowserTab);
  renderDiagnostics();
}, 5000);
