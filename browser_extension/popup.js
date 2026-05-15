async function refresh() {
  const s = await chrome.storage.local.get(["token", "paused"]);
  document.getElementById("token").value = s.token || "";
  document.getElementById("paused").checked = !!s.paused;

  chrome.runtime.sendMessage({ type: "status" }, (resp) => {
    const dot = document.getElementById("dot");
    const text = document.getElementById("status-text");
    if (!resp) {
      dot.className = "dot err";
      text.textContent = "后台未响应";
      return;
    }
    if (resp.paused) {
      dot.className = "dot";
      text.textContent = "已暂停";
    } else if (!resp.hasToken) {
      dot.className = "dot err";
      text.textContent = "未配置 token";
    } else if (resp.connected) {
      dot.className = "dot ok";
      text.textContent = "已连接";
    } else {
      dot.className = "dot err";
      text.textContent = "未连接";
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
