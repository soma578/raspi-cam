const img = document.getElementById("video");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");
const gridChk = document.getElementById("grid");
const fpsInput = document.getElementById("fps");
const stats = document.getElementById("stats");
const contrastInput = document.getElementById("contrast");
const isoInput = document.getElementById("iso");
const contrastVal = document.getElementById("contrastVal");
const isoVal = document.getElementById("isoVal");

const socket = io();

let running = false;
let lastTime = performance.now(), frames = 0, shownFps = 0;
let pendingSettings = {};
let settingsTimer = null;

function requestFrame() {
  if (!running) return;
  socket.emit("request_frame", {});
  setTimeout(requestFrame, Math.max(5, 1000 / Number(fpsInput.value || 15)));
}

socket.on("frame", msg => {
  img.src = msg.data;
  drawOverlay();
  const now = performance.now();
  frames++;
  if (now - lastTime > 1000) {
    shownFps = frames; frames = 0; lastTime = now;
    stats.textContent = `FPS: ${shownFps}`;
  }
});

document.getElementById("start").onclick = () => { running = true; requestFrame(); };
document.getElementById("stop").onclick  = () => { running = false; };
document.getElementById("snap").onclick  = async () => {
  const r = await fetch("/api/capture", {method:"POST"});
  const js = await r.json();
  alert(js.ok ? `Saved: ${js.filename}` : `Failed: ${js.error||'unknown'}`);
};
document.getElementById("snapUp").onclick = async () => {
  const r = await fetch("/api/capture_and_upload", {method:"POST"});
  const js = await r.json();
  alert(js.ok ? `Uploaded: ${js.sent}` : `Failed: ${js.status||js.error}`);
};

function queueSettings(update) {
  pendingSettings = {...pendingSettings, ...update};
  if (settingsTimer) clearTimeout(settingsTimer);
  settingsTimer = setTimeout(async () => {
    const payload = pendingSettings;
    pendingSettings = {};
    settingsTimer = null;
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
    } catch (err) {
      console.error("Failed to update settings", err);
    }
  }, 120);
}

async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    const js = await r.json();
    if (js.ok && js.settings) {
      applySettings(js.settings);
    }
  } catch (err) {
    console.error("Failed to load settings", err);
  }
}

function applySettings(settings) {
  if (contrastInput && settings.contrast != null) {
    const value = Number(settings.contrast);
    contrastInput.value = value;
    if (contrastVal) {
      contrastVal.textContent = value.toFixed(2);
    }
  }
  if (isoInput && settings.iso != null) {
    const value = Number(settings.iso);
    isoInput.value = value;
    if (isoVal) {
      isoVal.textContent = Math.round(value);
    }
  }
}

if (contrastInput) {
  contrastInput.addEventListener("input", ev => {
    const value = Number(ev.target.value);
    if (contrastVal) {
      contrastVal.textContent = value.toFixed(2);
    }
    queueSettings({contrast: value});
  });
}

if (isoInput) {
  isoInput.addEventListener("input", ev => {
    const value = Number(ev.target.value);
    if (isoVal) {
      isoVal.textContent = Math.round(value);
    }
    queueSettings({iso: value});
  });
}

loadSettings();

function drawOverlay() {
  overlay.width = img.clientWidth;
  overlay.height = img.clientHeight;
  ctx.clearRect(0,0,overlay.width, overlay.height);
  if (!gridChk.checked) return;
  ctx.globalAlpha = 0.5;
  const cols = 3, rows = 3;
  for (let c=1; c<cols; c++){
    const x = Math.round(overlay.width * c/cols);
    ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,overlay.height); ctx.stroke();
  }
  for (let r=1; r<rows; r++){
    const y = Math.round(overlay.height * r/rows);
    ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(overlay.width,y); ctx.stroke();
  }
  ctx.globalAlpha = 1.0;
}
