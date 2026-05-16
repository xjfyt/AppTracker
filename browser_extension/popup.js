async function refresh() {
  const s = await chrome.storage.local.get(["token", "paused"]);
  document.getElementById("token").value = s.token || "";
  document.getElementById("paused").checked = !!s.paused;

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
      text.textContent = "Token missing";
    } else if (resp.connected) {
      dot.className = "dot ok";
      text.textContent = "Connected";
    } else {
      dot.className = "dot err";
      text.textContent = "Disconnected";
    }
  });
}

document.getElementById("save").addEventListener("click", async () => {
  const t = document.getElementById("token").value.trim();
  await chrome.storage.local.set({ token: t });
  refresh();
});

document.getElementById("paused").addEventListener("change", async (e) => {
  await chrome.storage.local.set({ paused: e.target.checked });
  refresh();
});

refresh();
setInterval(refresh, 1500);
