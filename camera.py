import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["LIBCAMERA_LOG_LEVELS"] = "*:0"

import time
import threading
import io
from datetime import datetime
from PIL import Image

from config import FRAME_SIZE, JPEG_QUALITY, SNAP_DIR

class CameraBase:
    def __init__(self):
        self.width, self.height = FRAME_SIZE
        self.lock = threading.Lock()
        self.running = False
        self.last_frame = None  # JPEG bytes

    def start(self):
        self.running = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        print(f"[DEBUG] {self.__class__.__name__}: capture thread started")

    def stop(self):
        self.running = False

    def _loop(self):
        raise NotImplementedError

    def get_jpeg(self):
        with self.lock:
            return self.last_frame

    def save_snapshot(self, path=None):
        data = self.get_jpeg()
        if not data:
            print(f"[WARN] {self.__class__.__name__}: no frame available for snapshot")
            return None
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"{SNAP_DIR}/capture_{ts}.jpg"
        with open(path, "wb") as f:
            f.write(data)
        return path


class Picamera2Camera(CameraBase):
    def __init__(self):
        super().__init__()
        print("[DEBUG] Picamera2Camera: initializing...")

        from picamera2 import Picamera2
        from libcamera import Transform
        import time

        try:
            self.picam2 = Picamera2()
            print("[DEBUG] Picamera2Camera: instance created OK")
        except Exception as e:
            print("[ERROR] Picamera2 init failed:", e)
            raise

        try:
            self.config = self.picam2.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"},
                transform=Transform(hflip=0, vflip=0)
            )
            self.picam2.configure(self.config)
            self.output_format = self.picam2.camera_configuration()["main"]["format"]
            print(f"[DEBUG] Picamera2Camera: configured with preview mode (format: {self.output_format})")
        except Exception as e:
            print("[ERROR] Picamera2 configure failed:", e)
            raise

        try:
            self.picam2.start()
            print("[DEBUG] Picamera2Camera: started OK")
        except Exception as e:
            print("[ERROR] Picamera2 start failed:", e)
            raise

        time.sleep(1.0)
        print("[DEBUG] Picamera2Camera: warmup done")

    def _loop(self):
        import io, time
        from PIL import Image

        print("[DEBUG] Picamera2Camera: loop started")
        while self.running:
            try:
                frame = self.picam2.capture_array("main")
                if frame is None:
                    print("[WARN] capture_array returned None")
                    time.sleep(0.2)
                    continue
                print("[DEBUG] got frame:", frame.shape)
                fmt = getattr(self, "output_format", "RGB888")
                if fmt == "XBGR8888":
                    frame = frame[..., [3, 2, 1]]
                elif fmt == "XRGB8888":
                    frame = frame[..., [1, 2, 3]]
                elif fmt == "BGR888":
                    frame = frame[..., ::-1]
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = frame[..., :3]
                img = Image.fromarray(frame, mode="RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=JPEG_QUALITY)
                with self.lock:
                    self.last_frame = buf.getvalue()
                time.sleep(0.05)
            except Exception as e:
                print("[ERROR] Picamera2 loop exception:", e)
                time.sleep(0.2)

        print("[DEBUG] Picamera2Camera: loop stopped")


class OpenCVCamera(CameraBase):
    def __init__(self):
        super().__init__()
        import cv2
        self.cv2 = cv2
        self.cap = cv2.VideoCapture(0)
        self.cap.set(self.cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(self.cv2.CAP_PROP_FRAME_HEIGHT, self.height)

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            ok, jpg = self.cv2.imencode(".jpg", frame, [int(self.cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if ok:
                with self.lock:
                    self.last_frame = jpg.tobytes()
            time.sleep(0.001)

    def stop(self):
        super().stop()
        try:
            self.cap.release()
        except Exception:
            pass


def create_camera():
    # Picamera2優先、初期化に失敗したらOpenCVでフォールバック
    try:
        from picamera2 import Picamera2  # noqa: F401
    except Exception as e:
        print("[WARN] Picamera2 unavailable, fallback to OpenCV:", e)
        return OpenCVCamera()

    try:
        return Picamera2Camera()
    except Exception as e:
        print("[WARN] Picamera2 init failed, fallback to OpenCV:", e)
        return OpenCVCamera()
