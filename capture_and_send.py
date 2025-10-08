import os, requests
from camera import create_camera
from config import SNAP_DIR, UPLOAD_URL, UPLOAD_API_KEY

def main():
    cam = create_camera()
    cam.start()
    # ウォームアップ
    import time; time.sleep(1.0)
    path = cam.save_snapshot()
    cam.stop()
    print("saved:", path)

    if UPLOAD_URL:
        headers = {}
        if UPLOAD_API_KEY:
            headers["Authorization"] = f"Bearer {UPLOAD_API_KEY}"
        with open(path, "rb") as f:
            r = requests.post(UPLOAD_URL, headers=headers, files={"file": (os.path.basename(path), f, "image/jpeg")})
        print("upload:", r.status_code, r.text[:200])

if __name__ == "__main__":
    main()
