// popup.js
const btnStart = document.getElementById("btn-start");
const btnStop  = document.getElementById("btn-stop");
const dot      = document.getElementById("dot");
const statusTxt = document.getElementById("status-text");
const langSel  = document.getElementById("lang-select");

function setLive(live) {
  btnStart.style.display = live ? "none" : "block";
  btnStop.style.display  = live ? "block" : "none";
  dot.className = live ? "dot live" : "dot";
  statusTxt.textContent = live ? "Recording…" : "Idle";
}

// Restore state when popup opens
chrome.runtime.sendMessage({ type: "GET_STATUS" }, (res) => {
  if (res?.isCapturing) setLive(true);
});

btnStart.addEventListener("click", () => {
  const language = langSel.value;
  chrome.runtime.sendMessage({ type: "START_CAPTURE", language }, (res) => {
    if (res?.status === "started" || res?.status === "already_running") setLive(true);
  });
});

btnStop.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "STOP_CAPTURE" }, () => setLive(false));
});

// Listen for live updates (transcript snippets) from background
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "TRANSCRIPT_UPDATE") {
    // Just keep the popup minimal — full view is in Streamlit
    statusTxt.textContent = `Last: "${msg.payload.text?.slice(0, 40)}…"`;
  }
});
