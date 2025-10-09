import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("LIBCAMERA_LOG_LEVELS", "*:ERROR")

import time
import threading
import io
from datetime import datetime
from PIL import Image

from config import FRAME_SIZE, JPEG_QUALITY, SNAP_DIR, CAMERA_COLOR_ORDER, CAMERA_DEBUG


def debug_print(*args, **kwargs):
    if CAMERA_DEBUG:
        print(*args, **kwargs)

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
        debug_print(f"[DEBUG] {self.__class__.__name__}: capture thread started")

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
        debug_print("[DEBUG] Picamera2Camera: initializing...")

        from picamera2 import Picamera2
        from libcamera import Transform
        import time

        if hasattr(Picamera2, "set_logging"):
            level = getattr(Picamera2, "ERROR", None)
            if level is not None:
                try:
                    Picamera2.set_logging(level)
                except Exception as e:
                    debug_print("[DEBUG] Picamera2Camera: set_logging failed:", e)

        try:
            self.picam2 = Picamera2()
            debug_print("[DEBUG] Picamera2Camera: instance created OK")
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
            debug_print(f"[DEBUG] Picamera2Camera: configured with preview mode (format: {self.output_format})")
        except Exception as e:
            print("[ERROR] Picamera2 configure failed:", e)
            raise

        self.native_color_order = self._native_order_from_format(self.output_format)
        env_order = CAMERA_COLOR_ORDER
        if env_order == "AUTO":
            self.assumed_color_order = self.native_color_order or "RGB"
        else:
            self.assumed_color_order = env_order
        debug_print(
            "[DEBUG] Picamera2Camera: color order native="
            f"{self.native_color_order or 'unknown'} assumed={self.assumed_color_order}"
            f" (env={CAMERA_COLOR_ORDER})"
        )

        try:
            self.picam2.start()
            debug_print("[DEBUG] Picamera2Camera: started OK")
        except Exception as e:
            print("[ERROR] Picamera2 start failed:", e)
            raise

        time.sleep(1.0)
        debug_print("[DEBUG] Picamera2Camera: warmup done")

    def _loop(self):
        import io, time
        from PIL import Image

        debug_print("[DEBUG] Picamera2Camera: loop started")
        while self.running:
            try:
                frame = self.picam2.capture_array("main")
                if frame is None:
                    print("[WARN] capture_array returned None")
                    time.sleep(0.2)
                    continue
                debug_print("[DEBUG] got frame:", frame.shape)
                frame = self._frame_to_rgb(frame)
                img = Image.fromarray(frame, mode="RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=JPEG_QUALITY)
                with self.lock:
                    self.last_frame = buf.getvalue()
                time.sleep(0.05)
            except Exception as e:
                print("[ERROR] Picamera2 loop exception:", e)
                time.sleep(0.2)

        debug_print("[DEBUG] Picamera2Camera: loop stopped")

    def _native_order_from_format(self, fmt):
        fmt = (fmt or "").upper()
        if fmt in {"BGR888", "XBGR8888"}:
            return "BGR"
        if fmt in {"RGB888", "XRGB8888"}:
            return "RGB"
        return "RGB"

    def _frame_to_rgb(self, frame):
        fmt = getattr(self, "output_format", "RGB888")
        fmt = (fmt or "").upper()
        order = None
        if fmt == "XBGR8888":
            frame = frame[..., [1, 2, 3]]
            order = "BGR"
        elif fmt == "XRGB8888":
            frame = frame[..., [1, 2, 3]]
            order = "RGB"
        else:
            if frame.ndim == 3 and frame.shape[2] > 3:
                frame = frame[..., :3]
            if fmt == "BGR888":
                order = "BGR"
            elif fmt == "RGB888":
                order = "RGB"
            else:
                order = self.native_color_order or "RGB"

        if order is None:
            order = self.native_color_order or "RGB"

        assumed = getattr(self, "assumed_color_order", "RGB")
        if assumed == "AUTO":
            assumed = order
        if assumed == "BGR":
            frame = frame[..., ::-1]

        return frame.copy()


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
