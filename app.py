import os
import time
import base64
import eventlet
eventlet.monkey_patch(thread=False)

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from datetime import datetime

from camera import create_camera
from config import MAX_FPS, SNAP_DIR, UPLOAD_URL, UPLOAD_API_KEY

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

camera = create_camera()
camera.start()

last_emit = 0.0

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/healthz")
def healthz():
    return "ok", 200

# WebSocket: クライアントからの要求でフレームをPush
@socketio.on("request_frame")
def handle_request_frame(_msg):
    global last_emit
    now = time.time()
    if (now - last_emit) < (1.0 / MAX_FPS):
        return
    frame = camera.get_jpeg()
    if frame:
        b64 = base64.b64encode(frame).decode("ascii")
        socketio.emit("frame", {"data": f"data:image/jpeg;base64,{b64}"})
        last_emit = now

@app.route("/api/capture", methods=["POST", "GET"])
def api_capture():
    # ファイル名: capture_YYYYMMDD_HHMMSS.jpg
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{ts}.jpg"
    path = os.path.join(SNAP_DIR, filename)
    saved = camera.save_snapshot(path)
    if not saved:
        return jsonify({"ok": False, "error": "no_frame"}), 503
    return jsonify({"ok": True, "path": saved, "filename": filename, "timestamp": ts})

@app.route("/api/upload_latest", methods=["POST"])
def api_upload_latest():
    latest = sorted([f for f in os.listdir(SNAP_DIR) if f.endswith(".jpg")])[-1:]
    if not latest:
        return jsonify({"ok": False, "error": "no_snapshot"}), 404
    return _upload_file(os.path.join(SNAP_DIR, latest[0]))

@app.route("/api/capture_and_upload", methods=["POST"])
def api_capture_and_upload():
    # 撮影 → 直ちにアップロード
    c = api_capture()
    if c.status_code and c.status_code != 200:  # Flask Response 互換
        return c
    js = c.get_json()
    path = js.get("path")
    return _upload_file(path, extra=js)

def _upload_file(path, extra=None):
    if not UPLOAD_URL:
        return jsonify({"ok": False, "error": "UPLOAD_URL not set"}), 400
    import requests
    headers = {}
    if UPLOAD_API_KEY:
        headers["Authorization"] = f"Bearer {UPLOAD_API_KEY}"  # 必要に応じて調整
    with open(path, "rb") as f:
        files = {"file": (os.path.basename(path), f, "image/jpeg")}
        data = {}
        if extra and "timestamp" in extra:
            data["timestamp"] = extra["timestamp"]
            data["filename"]  = extra["filename"]
        r = requests.post(UPLOAD_URL, headers=headers, files=files, data=data, timeout=20)
    return jsonify({"ok": r.ok, "status": r.status_code, "text": r.text[:200], "sent": os.path.basename(path)}), (200 if r.ok else 502)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
