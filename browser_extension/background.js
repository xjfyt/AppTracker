// AppTracker bridge: streams active tab metadata to the local AppTracker app.
// Same code works on Chrome / Edge / Brave / Arc / Firefox MV3.

const DEFAULT_API_BASE = "http://127.0.0.1:5007";
const FALLBACK_PORT_START = 5007;
const FALLBACK_PORT_END = 5012;
let apiBase = DEFAULT_API_BASE;
let ws = null;
let token = null;
let reconnectDelay = 1000;
let pausedByUser = false;
let connectGeneration = 0;

function wsUrl() {
  return apiBase.replace(/^http/i, "ws").replace(/\/$/, "") + "/api/v1/browser";
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
  } catch (e) {
    for (let port = FALLBACK_PORT_START; port <= FALLBACK_PORT_END; port++) {
      bases.add(`http://127.0.0.1:${port}`);
    }
  }
  return Array.from(bases);
}

async function fetchWithTimeout(url, ms = 700) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { signal: controller.signal });
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
        if (base !== apiBase) {
          apiBase = base;
          await chrome.storage.local.set({ apiBase });
        }
        return base;
      }
    } catch (e) {}
  }
  return null;
}

async function fetchTokenFromHost() {
  for (const base of candidateApiBases()) {
    try {
      const res = await fetchWithTimeout(`${base}/api/v1/bridge_token`);
      if (!res.ok) continue;
      const data = await res.json();
      if (data && typeof data.token === "string" && data.token) {
        apiBase = base;
        await chrome.storage.local.set({ apiBase });
        return data.token;
      }
    } catch (e) {}
  }
  return null;
}

async function loadState() {
  const s = await chrome.storage.local.get(["token", "paused", "apiBase"]);
  token = s.token || null;
  pausedByUser = !!s.paused;
  apiBase = (s.apiBase || DEFAULT_API_BASE).replace(/\/$/, "");

  if (!token) {
    const fetched = await fetchTokenFromHost();
    if (fetched) {
      token = fetched;
      await chrome.storage.local.set({ token });
    }
  }
}

function detectBrowser() {
  try {
    const ua = navigator.userAgent;
    if (ua.includes("Edg/")) return "edge";
    if (ua.includes("Firefox/")) return "firefox";
    if (ua.includes("OPR/") || ua.includes("Opera/")) return "opera";
    if (typeof browser !== "undefined" && !chrome) return "firefox";
  } catch (e) {}
  return "chrome";
}

function setBadge(state) {
  const colors = { ok: "#22c55e", off: "#64748b", err: "#ef4444" };
  const text = { ok: "*", off: "", err: "!" };
  try {
    chrome.action.setBadgeBackgroundColor({ color: colors[state] || colors.off });
    chrome.action.setBadgeText({ text: text[state] || "" });
  } catch (e) {}
}

async function connect() {
  const generation = ++connectGeneration;
  if (pausedByUser) {
    setBadge("off");
    return;
  }
  await discoverApiBase();
  if (generation !== connectGeneration) return;
  if (!token) {
    setBadge("err");
    console.warn("[AppTracker] No token yet. Will retry — start AppTracker, the token auto-syncs.");
    fetchTokenFromHost().then(async (t) => {
      if (t) {
        token = t;
        await chrome.storage.local.set({ token: t });
        connect();
      }
    });
    scheduleReconnect();
    return;
  }
  if (ws) {
    try {
      ws.close();
    } catch (e) {}
    ws = null;
  }
  try {
    ws = new WebSocket(wsUrl());
  } catch (e) {
    setBadge("err");
    scheduleReconnect();
    return;
  }
  ws.onopen = () => {
    ws.send(JSON.stringify({ token }));
    setBadge("ok");
    reconnectDelay = 1000;
    pushActiveTab();
  };
  ws.onclose = () => {
    ws = null;
    setBadge("err");
    scheduleReconnect();
  };
  ws.onerror = () => setBadge("err");
}

function scheduleReconnect() {
  setTimeout(connect, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, 30000);
}

function send(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(payload));
    } catch (e) {}
  }
}

async function pushActiveTab() {
  if (pausedByUser) return;
  try {
    const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tabs.length) return;
    const t = tabs[0];
    send({
      type: "tab_update",
      browser: detectBrowser(),
      windowId: t.windowId,
      tabId: t.id,
      url: t.url || "",
      title: t.title || "",
      favIconUrl: t.favIconUrl || null,
      active: true,
    });
  } catch (e) {}
}

chrome.tabs.onActivated.addListener(pushActiveTab);
chrome.tabs.onUpdated.addListener((_id, change) => {
  if (!change) return;
  if (change.status === "complete" || change.url || change.title) pushActiveTab();
});
chrome.windows.onFocusChanged.addListener((wid) => {
  if (wid !== chrome.windows.WINDOW_ID_NONE) pushActiveTab();
});

chrome.alarms.create("keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN) connect();
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.token) token = changes.token.newValue || null;
  if (changes.paused) pausedByUser = !!changes.paused.newValue;
  if (changes.apiBase) apiBase = (changes.apiBase.newValue || DEFAULT_API_BASE).replace(/\/$/, "");
  try {
    if (ws) ws.close();
  } catch (e) {}
  connect();
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "status") {
    sendResponse({
      connected: ws && ws.readyState === WebSocket.OPEN,
      paused: pausedByUser,
      hasToken: !!token,
      apiBase,
    });
  }
  return true;
});

(async () => {
  await loadState();
  connect();
})();
