const img = document.getElementById("video");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");
const gridChk = document.getElementById("grid");
const fpsInput = document.getElementById("fps");
const stats = document.getElementById("stats");

const socket = io();

let running = false;
let lastTime = performance.now(), frames = 0, shownFps = 0;

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
