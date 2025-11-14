import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("LIBCAMERA_LOG_LEVELS", "*:ERROR")

import time
import threading
import io
from datetime import datetime
from PIL import Image, ImageEnhance

from config import FRAME_SIZE, JPEG_QUALITY, SNAP_DIR, CAMERA_COLOR_ORDER, CAMERA_DEBUG

AWB_MODES = {
    "auto",
    "daylight",
    "cloudy",
    "incandescent",
    "fluorescent",
    "tungsten",
    "sunlight",
    "custom",
}

def debug_print(*args, **kwargs):
    if CAMERA_DEBUG:
        print(*args, **kwargs)

class CameraBase:
    def __init__(self):
        self.width, self.height = FRAME_SIZE
        self.lock = threading.Lock()
        self.running = False
        self.last_frame = None  # JPEG bytes
        self._settings_lock = threading.Lock()
        self.camera_id = "default"
        self._adjustments = {
            "contrast": 1.0,
            "iso": 100.0,
            "exposure_us": 20000.0,
            "auto_exposure": True,
            "ev": 0.0,
            "saturation": 1.0,
            "sharpness": 1.0,
            "awb_mode": "auto",
            "hdr": False,
        }
        self.software_adjustments = True

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

    def get_adjustments(self):
        with self._settings_lock:
            return dict(self._adjustments)

    def update_adjustments(
        self,
        *,
        contrast=None,
        iso=None,
        exposure_us=None,
        auto_exposure=None,
        ev=None,
        saturation=None,
        sharpness=None,
        awb_mode=None,
        hdr=None,
    ):
        updated = False
        current = None
        with self._settings_lock:
            if contrast is not None:
                c = max(0.5, min(3.0, float(contrast)))
                self._adjustments["contrast"] = c
                updated = True
            if iso is not None:
                i = max(50.0, min(800.0, float(iso)))
                self._adjustments["iso"] = i
                updated = True
            if exposure_us is not None:
                exp = max(100.0, min(500000.0, float(exposure_us)))
                self._adjustments["exposure_us"] = exp
                updated = True
            if auto_exposure is not None:
                if isinstance(auto_exposure, str):
                    auto_flag = auto_exposure.lower() in {"1", "true", "yes", "on"}
                else:
                    auto_flag = bool(auto_exposure)
                self._adjustments["auto_exposure"] = auto_flag
                updated = True
            if ev is not None:
                e = max(-3.0, min(3.0, float(ev)))
                self._adjustments["ev"] = e
                updated = True
            if saturation is not None:
                sat = max(0.5, min(2.5, float(saturation)))
                self._adjustments["saturation"] = sat
                updated = True
            if sharpness is not None:
                shp = max(0.5, min(2.5, float(sharpness)))
                self._adjustments["sharpness"] = shp
                updated = True
            if awb_mode is not None:
                mode = str(awb_mode).strip().lower()
                if mode not in AWB_MODES:
                    mode = "auto"
                self._adjustments["awb_mode"] = mode or "auto"
                updated = True
            if hdr is not None:
                if isinstance(hdr, str):
                    hdr_flag = hdr.lower() in {"1", "true", "yes", "on"}
                else:
                    hdr_flag = bool(hdr)
                self._adjustments["hdr"] = hdr_flag
                updated = True
            if updated:
                current = dict(self._adjustments)
        if updated and current:
            self._apply_runtime_adjustments(current)
        return updated

    def _apply_runtime_adjustments(self, _settings):
        # Subclasses override when they can touch hardware controls
        pass

    def _apply_adjustments(self, img):
        if not getattr(self, "software_adjustments", True):
            return img
        adj = self.get_adjustments()
        contrast = adj.get("contrast", 1.0)
        if abs(contrast - 1.0) > 0.01:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        iso = adj.get("iso", 100.0)
        iso_factor = iso / 100.0
        if abs(iso_factor - 1.0) > 0.01:
            img = ImageEnhance.Brightness(img).enhance(iso_factor)
        ev = adj.get("ev", 0.0)
        if abs(ev) > 0.01:
            img = ImageEnhance.Brightness(img).enhance(pow(2.0, ev))
        saturation = adj.get("saturation", 1.0)
        if abs(saturation - 1.0) > 0.01:
            img = ImageEnhance.Color(img).enhance(saturation)
        sharpness = adj.get("sharpness", 1.0)
        if abs(sharpness - 1.0) > 0.01:
            img = ImageEnhance.Sharpness(img).enhance(sharpness)
        return img


class Picamera2Camera(CameraBase):
    def __init__(self, camera_index=None):
        super().__init__()
        debug_print("[DEBUG] Picamera2Camera: initializing...")
        self.camera_index = camera_index
        effective_index = camera_index if camera_index is not None else 0
        self.camera_id = f"picam2:{effective_index}"

        from picamera2 import Picamera2
        from libcamera import Transform
        try:
            from libcamera import controls as lib_controls
        except Exception:
            lib_controls = None
        import time

        if hasattr(Picamera2, "set_logging"):
            level = getattr(Picamera2, "ERROR", None)
            if level is not None:
                try:
                    Picamera2.set_logging(level)
                except Exception as e:
                    debug_print("[DEBUG] Picamera2Camera: set_logging failed:", e)

        try:
            if camera_index is None:
                self.picam2 = Picamera2()
            else:
                self.picam2 = Picamera2(camera_num=int(camera_index))
            self.libcamera_controls = lib_controls
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
        self.software_adjustments = False
        self._apply_runtime_adjustments(self.get_adjustments())
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
                img = self._apply_adjustments(img)
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

    def _resolve_awb_mode(self, mode):
        lc = getattr(self, "libcamera_controls", None)
        enum = getattr(lc, "AwbModeEnum", None) if lc else None
        if enum is None:
            return None
        mapping = {
            "auto": "Auto",
            "incandescent": "Incandescent",
            "tungsten": "Tungsten",
            "fluorescent": "Fluorescent",
            "daylight": "Daylight",
            "cloudy": "Cloudy",
            "sunlight": "Daylight",
            "custom": "Custom",
        }
        key = (mode or "auto").strip().lower()
        attr = mapping.get(key, "Auto")
        return getattr(enum, attr, None)

    def _resolve_hdr_mode(self, enabled):
        lc = getattr(self, "libcamera_controls", None)
        if lc is None:
            return None
        hdr_enum = None
        draft = getattr(lc, "draft", None)
        if draft is not None:
            hdr_enum = getattr(draft, "HdrModeEnum", None)
        if hdr_enum is None:
            hdr_enum = getattr(lc, "HdrModeEnum", None)
        if hdr_enum is None:
            return None
        if enabled:
            return getattr(hdr_enum, "MultiExposure", None) or getattr(hdr_enum, "Hdr", None)
        return getattr(hdr_enum, "SingleExposure", None) or getattr(hdr_enum, "None", None)

    def _apply_runtime_adjustments(self, settings):
        if not hasattr(self, "picam2"):
            return
        controls = {}
        contrast = settings.get("contrast")
        if contrast is not None:
            controls["Contrast"] = max(0.5, min(2.0, float(contrast)))
        saturation = settings.get("saturation")
        if saturation is not None:
            controls["Saturation"] = max(0.0, min(4.0, float(saturation)))
        sharpness = settings.get("sharpness")
        if sharpness is not None:
            controls["Sharpness"] = max(0.0, min(4.0, float(sharpness)))
        auto_mode = settings.get("auto_exposure", True)
        if auto_mode:
            controls["AeEnable"] = 1
            ev = settings.get("ev", 0.0)
            controls["ExposureValue"] = max(-3.0, min(3.0, float(ev or 0.0)))
        else:
            controls["AeEnable"] = 0
            exposure = settings.get("exposure_us") or 1000.0
            exposure = max(100.0, min(500000.0, float(exposure)))
            controls["ExposureTime"] = int(exposure)
            iso = settings.get("iso", 100.0)
            gain = max(1.0, min(8.0, float(iso) / 100.0))
            controls["AnalogueGain"] = gain
        awb_mode = settings.get("awb_mode")
        awb_value = self._resolve_awb_mode(awb_mode)
        if awb_value is not None:
            controls["AwbMode"] = awb_value
            controls["AwbEnable"] = 1
        hdr_flag = settings.get("hdr", False)
        hdr_value = self._resolve_hdr_mode(hdr_flag)
        if hdr_value is not None:
            controls["HdrMode"] = hdr_value
        if not controls:
            return
        try:
            self.picam2.set_controls(controls)
            self.software_adjustments = False
            debug_print(f"[DEBUG] Picamera2Camera: controls updated {controls}")
        except Exception as e:
            print("[WARN] Picamera2Camera: failed to set controls:", e)
            # Fallback to software adjustments if hardware fails
            self.software_adjustments = True


class OpenCVCamera(CameraBase):
    def __init__(self, device_index=0):
        super().__init__()
        import cv2
        self.cv2 = cv2
        self.device_index = device_index
        self.camera_id = f"opencv:{device_index}"
        self.cap = cv2.VideoCapture(device_index)
        if not self.cap.isOpened():
            try:
                self.cap.release()
            except Exception:
                pass
            raise RuntimeError(f"OpenCV camera index {device_index} unavailable")
        self.cap.set(self.cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(self.cv2.CAP_PROP_FRAME_HEIGHT, self.height)

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            frame_rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            img = self._apply_adjustments(img)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY)
            with self.lock:
                self.last_frame = buf.getvalue()
            time.sleep(0.01)

    def stop(self):
        super().stop()
        try:
            self.cap.release()
        except Exception:
            pass


def _parse_camera_id(camera_id):
    if not camera_id:
        return None, None
    camera_id = str(camera_id)
    parts = camera_id.split(":", 1)
    if len(parts) == 1:
        return parts[0].lower(), None
    return parts[0].lower(), parts[1]


def _list_picamera2_devices():
    devices = []
    try:
        from picamera2 import Picamera2
        infos = Picamera2.global_camera_info()
    except Exception:
        return devices
    if not infos:
        return devices
    for idx, info in enumerate(infos):
        label = None
        serial = None
        if isinstance(info, dict):
            label = info.get("Model") or info.get("Name") or info.get("CameraId")
            serial = info.get("CameraId")
        devices.append(
            {
                "id": f"picam2:{idx}",
                "type": "picamera2",
                "name": label or f"Pi Camera {idx}",
                "details": {"camera_id": serial},
            }
        )
    return devices


def _list_opencv_devices(max_devices=6):
    devices = []
    try:
        import cv2
    except Exception:
        cv2 = None
    for idx in range(max_devices):
        path_hint = f"/dev/video{idx}"
        opened = False
        cap = None
        if cv2 is not None:
            cap = cv2.VideoCapture(idx)
            if cap is not None and cap.isOpened():
                opened = True
        exists = os.path.exists(path_hint)
        if opened or exists:
            name = path_hint if exists else f"Video {idx}"
            devices.append(
                {
                    "id": f"opencv:{idx}",
                    "type": "opencv",
                    "name": name,
                    "details": {"index": idx, "path": path_hint if exists else None},
                }
            )
        if cap is not None:
            cap.release()
    return devices


def list_available_cameras(max_video_devices=6):
    cameras = []
    cameras.extend(_list_picamera2_devices())
    cameras.extend(_list_opencv_devices(max_video_devices))
    if not cameras:
        cameras.append({"id": "picam2:0", "type": "picamera2", "name": "Default Pi Camera", "details": {}})
    return cameras


def create_camera(camera_id=None):
    cam_type, value = _parse_camera_id(camera_id)
    if cam_type == "picam2":
        idx = None
        if value not in {None, "", "auto"}:
            try:
                idx = int(value)
            except ValueError:
                idx = None
        return Picamera2Camera(camera_index=idx)
    if cam_type == "opencv":
        idx = 0
        if value not in {None, ""}:
            try:
                idx = int(value)
            except ValueError:
                idx = 0
        return OpenCVCamera(device_index=idx)

    # Picamera2優先、初期化に失敗したらOpenCVでフォールバック
    try:
        from picamera2 import Picamera2  # noqa: F401
    except Exception as e:
        print("[WARN] Picamera2 unavailable, fallback to OpenCV:", e)
        cam = OpenCVCamera()
        cam.camera_id = getattr(cam, "camera_id", "opencv:0")
        return cam

    try:
        cam = Picamera2Camera()
        cam.camera_id = getattr(cam, "camera_id", "picam2:0")
        return cam
    except Exception as e:
        print("[WARN] Picamera2 init failed, fallback to OpenCV:", e)
        cam = OpenCVCamera()
        cam.camera_id = getattr(cam, "camera_id", "opencv:0")
        return cam
