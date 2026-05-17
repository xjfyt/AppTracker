const DEFAULT_API = "http://127.0.0.1:5007";
const FALLBACK_PORT_START = 5007;
const FALLBACK_PORT_END = 5012;

function candidateApiBases(preferred) {
  const bases = new Set();
  const normalized = (preferred || DEFAULT_API).replace(/\/$/, "");
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

async function refresh() {
  const s = await chrome.storage.local.get(["token", "paused", "apiBase"]);
  document.getElementById("token").value = s.token || "";
  document.getElementById("paused").checked = !!s.paused;
  document.getElementById("api").value = s.apiBase || DEFAULT_API;

  chrome.runtime.sendMessage({ type: "status" }, (resp) => {
    const dot = document.getElementById("dot");
    const text = document.getElementById("status-text");
    if (!resp) {
      dot.className = "dot err";
      text.textContent = "Background unavailable";
      return;
    }
    if (resp.paused) {
      dot.className = "dot";
      text.textContent = "Paused";
    } else if (!resp.hasToken) {
      dot.className = "dot err";
      text.textContent = "Token missing — click Sync";
    } else if (resp.connected) {
      dot.className = "dot ok";
      text.textContent = `Connected: ${resp.apiBase || ""}`;
    } else {
      dot.className = "dot err";
      text.textContent = "Disconnected — is AppTracker running?";
    }
  });
}

async function syncToken() {
  const api = (document.getElementById("api").value.trim() || DEFAULT_API).replace(/\/$/, "");
  try {
    for (const base of candidateApiBases(api)) {
      const res = await fetchWithTimeout(`${base}/api/v1/bridge_token`);
      if (!res.ok) continue;
      const data = await res.json();
      if (!data || !data.token) continue;
      await chrome.storage.local.set({ token: data.token, apiBase: base });
      document.getElementById("token").value = data.token;
      document.getElementById("api").value = base;
      refresh();
      return;
    }
    throw new Error("no AppTracker token endpoint found");
  } catch (e) {
    document.getElementById("status-text").textContent = `Sync failed: ${e.message}`;
    document.getElementById("dot").className = "dot err";
  }
}

document.getElementById("fetch").addEventListener("click", syncToken);

document.getElementById("save").addEventListener("click", async () => {
  const t = document.getElementById("token").value.trim();
  const api = (document.getElementById("api").value.trim() || DEFAULT_API).replace(/\/$/, "");
  await chrome.storage.local.set({ token: t, apiBase: api });
  refresh();
});

document.getElementById("paused").addEventListener("change", async (e) => {
  await chrome.storage.local.set({ paused: e.target.checked });
  refresh();
});

refresh();
setInterval(refresh, 1500);
