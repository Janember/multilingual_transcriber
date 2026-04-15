// background.js – MV3 service worker
// Uses a ready-handshake so OFFSCREEN_START is only sent
// after offscreen.js confirms it has loaded.

const OFFSCREEN_URL = chrome.runtime.getURL("offscreen.html");
let isCapturing  = false;
let pendingStart = null;   // holds { streamId, language } until offscreen is ready

// ── Offscreen helpers ─────────────────────────────────────

async function ensureOffscreenDocument() {
  try {
    await chrome.offscreen.createDocument({
      url: OFFSCREEN_URL,
      reasons: ["USER_MEDIA"],
      justification: "Capture Google Meet tab audio for transcription",
    });
  } catch (err) {
    if (!err.message?.includes("Only a single")) throw err;
  }
}

async function closeOffscreenDocument() {
  try { await chrome.offscreen.closeDocument(); } catch (_) {}
}

// ── Start / stop ──────────────────────────────────────────

async function startCapture(tabId, language) {
  try {
    const streamId = await chrome.tabCapture.getMediaStreamId({
      targetTabId: tabId,
    });

    // Store what we want to send, then open the offscreen page.
    // offscreen.js will send OFFSCREEN_READY when loaded → we send START then.
    pendingStart = { streamId, language };
    await ensureOffscreenDocument();

    // Fallback: if OFFSCREEN_READY never arrives (already open), send after 600ms
    setTimeout(() => {
      if (pendingStart) {
        chrome.runtime.sendMessage({ type: "OFFSCREEN_START", ...pendingStart })
          .catch(() => {});
        pendingStart = null;
      }
    }, 600);

    isCapturing = true;
    console.log("[MeetScribe] Capture started – language:", language);
  } catch (err) {
    console.error("[MeetScribe] startCapture failed:", err);
    isCapturing = false;
  }
}

async function stopCapture() {
  pendingStart = null;
  try {
    await chrome.runtime.sendMessage({ type: "OFFSCREEN_STOP" });
  } catch (_) {}
  await new Promise((r) => setTimeout(r, 200));
  await closeOffscreenDocument();
  isCapturing = false;
  console.log("[MeetScribe] Capture stopped");
}

// ── Message handler ───────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {

  // Offscreen page finished loading → send the pending start command
  if (msg.type === "OFFSCREEN_READY" && pendingStart) {
    chrome.runtime.sendMessage({ type: "OFFSCREEN_START", ...pendingStart })
      .catch(() => {});
    pendingStart = null;
    return;
  }

  if (msg.type === "START_CAPTURE") {
    if (!isCapturing) {
      chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
        startCapture(tab.id, msg.language || "auto");
        sendResponse({ status: "started" });
      });
      return true;
    } else {
      sendResponse({ status: "already_running" });
    }
  }

  if (msg.type === "STOP_CAPTURE") {
    stopCapture().then(() => sendResponse({ status: "stopped" }));
    return true;
  }

  if (msg.type === "GET_STATUS") {
    sendResponse({ isCapturing });
  }

  // Relay transcript updates from offscreen → popup
  if (msg.type === "TRANSCRIPT_UPDATE") {
    chrome.runtime.sendMessage(msg).catch(() => {});
  }
});