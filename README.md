以下は、このプロジェクト（Flask + SocketIO + OpenCV ベースの Raspberry Pi カメラシステム）の完全な **README.md** です。
このまま `raspi-cam-viewer/README.md` として保存すれば OK です。

---

```markdown
# 📷 Raspberry Pi Camera Viewer & Scheduler

Raspberry Pi カメラを使って **リアルタイムの画角確認・スナップ撮影・自動定時撮影・サーバ送信** を行う常駐アプリケーションです。  
Flask + Socket.IO + OpenCV / Picamera2 を使用し、Webブラウザからカメラ映像をリアルタイムに確認できます。

---

## 🧩 機能概要

| 機能 | 内容 |
|------|------|
| 🔴 **ライブプレビュー** | Flask + Socket.IO によりリアルタイム映像をブラウザに配信 |
| 📸 **スナップ撮影** | ボタンで静止画を撮影し、`snaps/` に保存 |
| ☁️ **アップロード** | 撮影画像を REST API 経由で自動アップロード |
| 🕒 **スケジュール撮影** | cron により毎日 7:00 / 17:00 に自動撮影 |
| ⚙️ **常駐運転** | systemd サービス化で再起動・電源投入時に自動起動 |
| 🧱 **ハードウェア対応** | Picamera2（純正カメラ）または OpenCV（USBカメラ）両対応 |

---

## 📁 ディレクトリ構成

```

raspi-cam-viewer/
├─ app.py                   # Flask + Socket.IO メインサーバ
├─ camera.py                # カメラ制御（Picamera2 / OpenCV 自動切替）
├─ config.py                # 設定ファイル（解像度・アップロード先など）
├─ requirements.txt         # Python 依存関係
├─ templates/
│   └─ index.html           # Web UI（プレビュー・スナップボタンなど）
└─ static/
└─ main.js              # フロントエンドロジック（Socket.IO通信）

````

---

## 🧰 セットアップ手順

### 1️⃣ Raspberry Pi 側のパッケージ

```bash
sudo apt update
sudo apt install -y \
  python3-pip python3-venv \
  python3-picamera2 python3-libcamera libcamera-apps \
  python3-opencv libatlas-base-dev curl
```

> 既にインストール済みの場合はそのままで OK。`libcamera-hello -t 2000` が動けばカメラ周りの準備完了です。

### 2️⃣ 仮想環境（システムパッケージ共有）と依存導入

```bash
cd ~/raspi-cam-viewer
# 以前の venv がある場合は削除
rm -rf .venv

# Picamera2 など apt のモジュールを共有するため --system-site-packages を付ける
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

`pip install -r requirements.txt` では Flask / Socket.IO / Pillow / requests などの最小限だけを入れ、OpenCV や Picamera2 は apt 版を利用します（`requirements.txt` から `opencv-python(-headless)` は削除済み）。

### 3️⃣ Picamera2 の読み込みテスト

```bash
python3 -c "from picamera2 import Picamera2"
```

何も表示されずに戻れば成功です。

---

## 🚀 実行とアクセス

### 起動

```bash
source .venv/bin/activate
python app.py
```

### ブラウザでアクセス

```
http://<ラズパイのIP>:5000
```

### UI 操作

* 🟢 **Start**：ライブプレビュー開始
* 🟥 **Stop**：停止
* 📸 **Snapshot**：1枚撮影（保存）
* ☁️ **Snap & Upload**：撮影＋サーバ送信
* 🔲 **Grid**：3×3の構図ガイド表示

保存先は `raspi-cam-viewer/snaps/` です。

---

## ⚙️ 常駐化 (systemd)

`/etc/systemd/system/raspi-cam.service`

```ini
[Unit]
Description=Raspberry Pi Camera Web UI
After=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/raspi-cam-viewer
Environment="FRAME_SIZE=1280,720"
Environment="JPEG_QUALITY=80"
Environment="MAX_FPS=15"
Environment="SNAP_DIR=/home/pi/raspi-cam-viewer/snaps"
Environment="UPLOAD_URL=https://example.com/upload"
Environment="UPLOAD_API_KEY=YOUR_API_KEY"
# カラー順序が逆に見える場合は AUTO/RGB/BGR から選択
# Environment="CAMERA_COLOR_ORDER=RGB"
# 詳細デバッグが必要な場合のみ 1 をセット
# Environment="CAMERA_DEBUG=1"
ExecStart=/home/pi/raspi-cam-viewer/.venv/bin/python /home/pi/raspi-cam-viewer/app.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

起動と有効化：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now raspi-cam.service
```

状態確認：

```bash
sudo systemctl status raspi-cam
```

---

## ⏰ 自動撮影スケジュール (cron)

### 毎日 7:00 / 17:00 に撮影してアップロード

```bash
crontab -e
```

追加：

```bash
0 7,17 * * * curl -sf -X POST http://127.0.0.1:5000/api/capture_and_upload >> /var/log/raspi-cam-cron.log 2>&1
```

> ⚠️ Flask アプリが起動していないと撮影できません。
> 時間は `timedatectl set-timezone Asia/Tokyo` で日本時間に設定してください。

---

## 📡 サーバ送信仕様

| 項目     | 内容                                           |
| ------ | -------------------------------------------- |
| メソッド   | `POST`                                       |
| URL    | `UPLOAD_URL`（環境変数または config.py）              |
| 認証     | `Authorization: Bearer <UPLOAD_API_KEY>`（任意） |
| 送信内容   | multipart/form-data                          |
| フィールド  | `file` (画像), `timestamp`, `filename`         |
| ファイル名例 | `capture_20251009_070000.jpg`                |

サーバ側で `timestamp` と `filename` を受け取ることで、DB連携・時系列整理が可能です。

---

## 🎛 環境変数まとめ

| 変数名 | 役割 | 既定値 | 備考 |
| ------ | ---- | ------ | ---- |
| `FRAME_SIZE` | プレビュー解像度 (WIDTH,HEIGHT) | `1280,720` | Picamera2 / OpenCV 両対応 |
| `JPEG_QUALITY` | JPEG 品質 | `80` | 数値が低いほどファイルサイズは小さい |
| `MAX_FPS` | UI 配信の最大 FPS | `15` | Socket.IO 経由の負荷制御 |
| `SNAP_DIR` | スナップ保存先 | `./snaps` | 自動作成される |
| `UPLOAD_URL` | アップロード先 URL | 空文字 | 空ならアップロード無効 |
| `UPLOAD_API_KEY` | アップロード認証トークン | 空文字 | 認証不要なら未設定のままで OK |
| `CAMERA_COLOR_ORDER` | カメラの色順序 (AUTO/RGB/BGR) | `BGR` | 色が寒暖反転するなら `RGB` を指定 |
| `CAMERA_DEBUG` | Picamera2 デバッグログ | `0` | 調査時だけ `1` や `true` で有効化 |

---

## 📷 手動で1枚撮る

```bash
curl -X POST http://127.0.0.1:5000/api/capture_and_upload
```

ローカル保存だけなら：

```bash
curl -X POST http://127.0.0.1:5000/api/capture
```

---

## 🧱 トラブルシューティング

| 症状        | 対処                                            |
| --------- | --------------------------------------------- |
| カメラが真っ黒   | `libcamera-hello -t 2000` が動作するか確認            |
| UIが応答しない  | Flaskアプリが起動中か確認（`systemctl status raspi-cam`） |
| cronが動かない | `/var/log/raspi-cam-cron.log` を確認             |
| ファイル送信に失敗 | アップロードURLとAPIキーを再確認                           |

---

## 🧩 拡張案

* 撮影画像に日時文字をオーバーレイ表示
* 温度・湿度センサ連携（I²C/SPIデータ記録）
* AWS S3 / Google Cloud Storage 送信
* Flask UI に「次回撮影予定」「通信状態」表示

---

## 🧑‍💻 ライセンス

MIT License
(c) 2025 so m & contributors

---

## 🧭 開発メモ

| 項目        | バージョン                                 |
| --------- | ------------------------------------- |
| OS        | Raspberry Pi OS (Bookworm / Bullseye) |
| Python    | 3.9+                                  |
| Picamera2 | 0.3.17+                               |
| Flask     | 3.x                                   |
| Socket.IO | 5.x                                   |
| OpenCV    | 4.x                                   |

---
