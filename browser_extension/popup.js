const DEFAULT_API = "http://127.0.0.1:5007";

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
      text.textContent = "Connected";
    } else {
      dot.className = "dot err";
      text.textContent = "Disconnected — is AppTracker running?";
    }
  });
}

async function syncToken() {
  const api = (document.getElementById("api").value.trim() || DEFAULT_API).replace(/\/$/, "");
  try {
    const res = await fetch(`${api}/api/v1/bridge_token`);
    if (!res.ok) throw new Error(`status ${res.status}`);
    const data = await res.json();
    if (!data || !data.token) throw new Error("no token in response");
    await chrome.storage.local.set({ token: data.token, apiBase: api });
    document.getElementById("token").value = data.token;
    refresh();
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
