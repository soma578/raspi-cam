import os
import time
import base64
import threading

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from datetime import datetime

from camera import create_camera, list_available_cameras
from config import MAX_FPS, SNAP_DIR, UPLOAD_URL, UPLOAD_API_KEY

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
camera_lock = threading.Lock()
camera = create_camera()
camera.start()
active_camera_id = getattr(camera, "camera_id", "default")
last_emit = 0.0


def _current_camera():
    with camera_lock:
        return camera


def _active_camera_id():
    with camera_lock:
        return active_camera_id


def _switch_camera(target_id):
    global camera, active_camera_id
    new_cam = None
    try:
        new_cam = create_camera(target_id)
        new_cam.start()
    except Exception:
        if new_cam:
            try:
                new_cam.stop()
            except Exception:
                pass
        raise
    old_cam = None
    with camera_lock:
        old_cam = camera
        camera = new_cam
        active_camera_id = getattr(new_cam, "camera_id", target_id or "default")
    if old_cam:
        try:
            old_cam.stop()
        except Exception:
            pass
    return active_camera_id

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
    cam = _current_camera()
    if cam is None:
        return
    frame = cam.get_jpeg()
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
    cam = _current_camera()
    if cam is None:
        return jsonify({"ok": False, "error": "no_camera"}), 503
    saved = cam.save_snapshot(path)
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

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    cam = _current_camera()
    if cam is None:
        return jsonify({"ok": False, "error": "no_camera"}), 503
    if request.method == "GET":
        return jsonify({"ok": True, "settings": cam.get_adjustments()})
    payload = request.get_json(silent=True) or {}
    changed = cam.update_adjustments(
        contrast=payload.get("contrast"),
        iso=payload.get("iso"),
        exposure_us=payload.get("exposure_us"),
        auto_exposure=payload.get("auto_exposure"),
        ev=payload.get("ev"),
        saturation=payload.get("saturation"),
        sharpness=payload.get("sharpness"),
        awb_mode=payload.get("awb_mode"),
        hdr=payload.get("hdr"),
    )
    if not changed:
        return jsonify({"ok": False, "error": "no_valid_settings"}), 400
    return jsonify({"ok": True, "settings": cam.get_adjustments()})


@app.route("/api/cameras", methods=["GET", "POST"])
def api_cameras():
    if request.method == "GET":
        return jsonify(
            {
                "ok": True,
                "cameras": list_available_cameras(),
                "active": _active_camera_id(),
            }
        )
    payload = request.get_json(silent=True) or {}
    target = payload.get("id") or payload.get("camera_id")
    if not target:
        return jsonify({"ok": False, "error": "missing_id"}), 400
    try:
        active = _switch_camera(target)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "active": active})

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
