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
const exposureInput = document.getElementById("exposure");
const exposureVal = document.getElementById("exposureVal");
const exposureAuto = document.getElementById("exposureAuto");
const evInput = document.getElementById("ev");
const evVal = document.getElementById("evVal");
const saturationInput = document.getElementById("saturation");
const saturationVal = document.getElementById("saturationVal");
const sharpnessInput = document.getElementById("sharpness");
const sharpnessVal = document.getElementById("sharpnessVal");
const awbSelect = document.getElementById("awb");
const hdrToggle = document.getElementById("hdr");

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
  if (exposureInput && settings.exposure_us != null) {
    const value = Number(settings.exposure_us);
    exposureInput.value = value;
    updateExposureLabel(value);
  }
  if (exposureAuto && settings.auto_exposure != null) {
    const autoFlag = Boolean(settings.auto_exposure);
    exposureAuto.checked = autoFlag;
    syncManualControls(autoFlag);
  } else if (exposureAuto) {
    syncManualControls(exposureAuto.checked);
  }
  if (evInput && settings.ev != null) {
    const value = Number(settings.ev);
    evInput.value = value;
    if (evVal) evVal.textContent = value.toFixed(1);
  }
  if (saturationInput && settings.saturation != null) {
    const value = Number(settings.saturation);
    saturationInput.value = value;
    if (saturationVal) saturationVal.textContent = value.toFixed(2);
  }
  if (sharpnessInput && settings.sharpness != null) {
    const value = Number(settings.sharpness);
    sharpnessInput.value = value;
    if (sharpnessVal) sharpnessVal.textContent = value.toFixed(2);
  }
  if (awbSelect && settings.awb_mode) {
    const mode = String(settings.awb_mode);
    const hasOption = Array.from(awbSelect.options).some(opt => opt.value === mode);
    awbSelect.value = hasOption ? mode : "auto";
  }
  if (hdrToggle && settings.hdr != null) {
    hdrToggle.checked = Boolean(settings.hdr);
  }
}

function updateExposureLabel(value) {
  if (!exposureVal) return;
  const ms = Number(value) / 1000.0;
  if (ms >= 1) {
    exposureVal.textContent = `${ms.toFixed(1)} ms`;
  } else {
    exposureVal.textContent = `${(ms * 1000).toFixed(0)} us`;
  }
}

function syncManualControls(autoFlag) {
  const manualDisabled = !!autoFlag;
  if (isoInput) isoInput.disabled = manualDisabled;
  if (exposureInput) exposureInput.disabled = manualDisabled;
  if (evInput) evInput.disabled = !autoFlag;
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
    if (!exposureAuto || !exposureAuto.checked) {
      queueSettings({iso: value});
    }
  });
}

if (evInput) {
  evInput.addEventListener("input", ev => {
    const value = Number(ev.target.value);
    if (evVal) {
      evVal.textContent = value.toFixed(1);
    }
    if (!exposureAuto || exposureAuto.checked) {
      queueSettings({ev: value});
    }
  });
}

if (exposureInput) {
  exposureInput.addEventListener("input", ev => {
    const value = Number(ev.target.value);
    updateExposureLabel(value);
    if (!exposureAuto || !exposureAuto.checked) {
      queueSettings({exposure_us: value});
    }
  });
}

if (exposureAuto) {
  exposureAuto.addEventListener("change", ev => {
    const autoFlag = ev.target.checked;
    syncManualControls(autoFlag);
    queueSettings({auto_exposure: autoFlag});
    if (!autoFlag) {
      if (exposureInput) queueSettings({exposure_us: Number(exposureInput.value)});
      if (isoInput) queueSettings({iso: Number(isoInput.value)});
    }
    if (autoFlag && evInput) {
      queueSettings({ev: Number(evInput.value)});
    }
  });
}

if (saturationInput) {
  saturationInput.addEventListener("input", ev => {
    const value = Number(ev.target.value);
    if (saturationVal) {
      saturationVal.textContent = value.toFixed(2);
    }
    queueSettings({saturation: value});
  });
}

if (sharpnessInput) {
  sharpnessInput.addEventListener("input", ev => {
    const value = Number(ev.target.value);
    if (sharpnessVal) {
      sharpnessVal.textContent = value.toFixed(2);
    }
    queueSettings({sharpness: value});
  });
}

if (awbSelect) {
  awbSelect.addEventListener("change", ev => {
    queueSettings({awb_mode: ev.target.value});
  });
}

if (hdrToggle) {
  hdrToggle.addEventListener("change", ev => {
    queueSettings({hdr: ev.target.checked});
  });
}

if (exposureInput) {
  updateExposureLabel(exposureInput.value);
}
if (exposureAuto) {
  syncManualControls(exposureAuto.checked);
}
if (evInput && evVal) {
  evVal.textContent = Number(evInput.value).toFixed(1);
}
if (saturationInput && saturationVal) {
  saturationVal.textContent = Number(saturationInput.value).toFixed(2);
}
if (sharpnessInput && sharpnessVal) {
  sharpnessVal.textContent = Number(sharpnessInput.value).toFixed(2);
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
