// Active Tracker bridge: streams active tab metadata to the local Rust agent.
// Same code works on Chrome / Edge / Brave / Arc / Firefox MV3.

const WS_URL = "ws://127.0.0.1:5006";
let ws = null;
let token = null;
let reconnectDelay = 1000;
let pausedByUser = false;

async function loadState() {
  const s = await chrome.storage.local.get(["token", "paused"]);
  token = s.token || null;
  pausedByUser = !!s.paused;
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

function connect() {
  if (pausedByUser) {
    setBadge("off");
    return;
  }
  if (!token) {
    setBadge("err");
    console.warn("[ActiveTracker] No token configured. Open popup to set.");
    return;
  }
  try {
    ws = new WebSocket(WS_URL);
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
    });
  }
  return true;
});

(async () => {
  await loadState();
  connect();
})();
