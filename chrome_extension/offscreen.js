// offscreen.js – dual-stream capture
// 8-second chunks give Whisper enough context for accurate transcription
// especially for code-switched Filipino speech.

const WS_BASE       = "ws://localhost:8000/ws/audio";
const CHUNK_MS      = 8000;    // 8 seconds — better accuracy than 4s
const MIN_BYTES     = 1000;
const RMS_THRESHOLD = 0.005;

let ws          = null;
let tabStream   = null;
let micStream   = null;
let audioCtx    = null;
let mixedStream = null;
let analyser    = null;
let cycleTimer  = null;
let isRunning   = false;

chrome.runtime.sendMessage({ type: "OFFSCREEN_READY" }).catch(() => {});
console.log("[MeetScribe/offscreen] Page loaded, sent READY");

chrome.runtime.onMessage.addListener((msg) => {
  console.log("[MeetScribe/offscreen] Message:", msg.type);
  if (msg.type === "OFFSCREEN_START") startCapture(msg.streamId, msg.language || "auto");
  if (msg.type === "OFFSCREEN_STOP")  stopCapture();
});

async function startCapture(streamId, language) {
  console.log("[MeetScribe/offscreen] Starting – lang:", language);
  try {
    tabStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource:   "tab",
          chromeMediaSourceId: streamId,
        },
      },
      video: false,
    });
    console.log("[MeetScribe/offscreen] Tab stream OK");

    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: false,
      });
      console.log("[MeetScribe/offscreen] Mic stream OK");
    } catch (e) {
      console.warn("[MeetScribe/offscreen] Mic unavailable:", e.message);
      micStream = null;
    }

    audioCtx      = new AudioContext();
    const dest    = audioCtx.createMediaStreamDestination();
    analyser      = audioCtx.createAnalyser();
    analyser.fftSize = 2048;

    const tabSrc = audioCtx.createMediaStreamSource(tabStream);
    tabSrc.connect(dest);
    tabSrc.connect(analyser);

    if (micStream) {
      const micSrc = audioCtx.createMediaStreamSource(micStream);
      micSrc.connect(dest);
      micSrc.connect(analyser);
    }

    mixedStream = dest.stream;
    console.log("[MeetScribe/offscreen] Streams mixed");

    openWebSocket(language);
    await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error("WS timeout")), 5000);
      ws.addEventListener("open",  () => { clearTimeout(t); resolve(); }, { once: true });
      ws.addEventListener("error", (e) => { clearTimeout(t); reject(e);  }, { once: true });
    });

    isRunning = true;
    recordCycle();

  } catch (err) {
    console.error("[MeetScribe/offscreen] startCapture failed:", err);
  }
}

function stopCapture() {
  isRunning = false;
  clearTimeout(cycleTimer);
  tabStream?.getTracks().forEach((t) => t.stop());
  micStream?.getTracks().forEach((t) => t.stop());
  audioCtx?.close();
  ws?.close();
  tabStream = micStream = audioCtx = mixedStream = analyser = ws = null;
}

function getCurrentRMS() {
  if (!analyser) return 1.0;
  const data = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(data);
  const sum = data.reduce((acc, v) => acc + v * v, 0);
  return Math.sqrt(sum / data.length);
}

function recordCycle() {
  if (!isRunning || !mixedStream) return;

  const chunks = [];
  let peakRMS  = 0;
  let rmsTimer = null;
  let recorder;

  try {
    recorder = new MediaRecorder(mixedStream, {
      mimeType: "audio/webm;codecs=opus",
    });
  } catch (e) {
    console.error("[MeetScribe/offscreen] MediaRecorder create failed:", e);
    return;
  }

  rmsTimer = setInterval(() => {
    const rms = getCurrentRMS();
    if (rms > peakRMS) peakRMS = rms;
  }, 200);

  recorder.ondataavailable = (e) => {
    if (e.data?.size > 0) chunks.push(e.data);
  };

  recorder.onstop = async () => {
    clearInterval(rmsTimer);
    if (!isRunning) return;

    const blob = new Blob(chunks, { type: "audio/webm;codecs=opus" });
    console.log(`[MeetScribe/offscreen] Peak RMS: ${peakRMS.toFixed(4)} | size: ${blob.size}`);

    if (blob.size < MIN_BYTES) {
      console.log("[MeetScribe/offscreen] Skipped: too small");
    } else if (peakRMS < RMS_THRESHOLD) {
      console.log("[MeetScribe/offscreen] Skipped: silence");
    } else if (ws?.readyState === WebSocket.OPEN) {
      const buf = await blob.arrayBuffer();
      ws.send(buf);
      console.log("[MeetScribe/offscreen] Sent chunk:", blob.size, "bytes");
    }

    if (isRunning) recordCycle();
  };

  recorder.start();
  cycleTimer = setTimeout(() => {
    if (recorder.state !== "inactive") recorder.stop();
  }, CHUNK_MS);
}

function openWebSocket(language) {
  const url = `${WS_BASE}?lang=${language}`;
  console.log("[MeetScribe/offscreen] Opening WS:", url);
  ws = new WebSocket(url);
  ws.binaryType = "arraybuffer";
  ws.onopen    = () => console.log("[MeetScribe/offscreen] WS connected ✓");
  ws.onclose   = (e) => console.log("[MeetScribe/offscreen] WS closed:", e.code);
  ws.onerror   = (e) => console.error("[MeetScribe/offscreen] WS error:", e);
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("[MeetScribe/offscreen] Transcript:", data.text);
    chrome.runtime.sendMessage({ type: "TRANSCRIPT_UPDATE", payload: data });
  };
}