import os

# プレビュー用の解像度（幅, 高さ）
FRAME_SIZE = tuple(map(int, os.getenv("FRAME_SIZE", "1280,720").split(",")))
# JPEG品質（UI配信の画質/帯域バランス）
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))
# UI配信の最大FPS（負荷対策）
MAX_FPS = float(os.getenv("MAX_FPS", "15"))

# 保存ディレクトリ
SNAP_DIR = os.getenv("SNAP_DIR", "./snaps")
os.makedirs(SNAP_DIR, exist_ok=True)

# アップロード先REST API（空だとアップロード無効）
UPLOAD_URL = os.getenv("UPLOAD_URL", "")           # 例: https://example.com/upload
UPLOAD_API_KEY = os.getenv("UPLOAD_API_KEY", "")   # 例: ベアラートークンなど

# カメラからの生データの色順序 (AUTO / RGB / BGR) デフォルトはBGR
CAMERA_COLOR_ORDER = os.getenv("CAMERA_COLOR_ORDER", "BGR").strip().upper()
if CAMERA_COLOR_ORDER not in {"AUTO", "RGB", "BGR"}:
    CAMERA_COLOR_ORDER = "BGR"

def _env_flag(name, default="0"):
    value = os.getenv(name, default)
    return value.lower() in {"1", "true", "yes", "on"}

CAMERA_DEBUG = _env_flag("CAMERA_DEBUG")
