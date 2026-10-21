"""
Main Entry Point: Hệ Thống Giám Sát Hành Vi Video Thời Gian Thực & Kiểm Soát Đa Luồng.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.

Khởi chạy Trung tâm Giám sát Điều hành AI Cyber Surveillance Hub (FastAPI + Live Camera 30 FPS + CapCut Timeline Video Analytics).
- Mặc định: Khởi động Web Server tại http://127.0.0.1:8000 và tự động mở trình duyệt.
- Cờ --mode hud: Khởi chạy cửa sổ OpenCV desktop độc lập nếu muốn.
"""

import os
import sys
import argparse
import webbrowser
import threading
import time

# Cấu hình cache ổ D nếu khả dụng (tương thích đa máy)
if os.path.exists("D:/huggingface_cache") or (os.name == "nt" and os.path.exists("D:/")):
    os.environ["HF_HOME"] = "D:/huggingface_cache"
    os.environ["TRANSFORMERS_CACHE"] = "D:/huggingface_cache/hub"


# Đảm bảo UTF-8 console output trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import urllib.request
import urllib.error
import warnings
import logging
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

from dotenv import load_dotenv
load_dotenv()


def open_browser_when_ready(url: str, timeout: float = 30.0, check_interval: float = 0.1) -> bool:
    """
    Thăm dò chủ động (Readiness Probe) tới endpoint /health.
    Chỉ mở trình duyệt khi máy chủ đã phản hồi HTTP 200 OK.
    Đảm bảo 100% không bao giờ gặp lỗi ERR_CONNECTION_REFUSED.
    """
    url = url.rstrip("/")
    health_url = f"{url}/health"
    start_time = time.time()
    print(f"[*] Đang đợi máy chủ sẵn sàng tại {health_url}...")

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(
                health_url,
                headers={"User-Agent": "FastAPIReadinessProbe/1.0"}
            )
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                if resp.status == 200:
                    elapsed = time.time() - start_time
                    print(f"[+] Máy chủ đã sẵn sàng phản hồi HTTP 200 sau {elapsed:.2f}s!")
                    print(f"[*] Tự động kết nối trình duyệt tới {url}...")
                    webbrowser.open(url)
                    return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            time.sleep(check_interval)
        except Exception:
            time.sleep(check_interval)

    print(f"[!] Quá thời gian chờ ({timeout}s). Vui lòng mở thủ công: {url}")
    return False


def free_port_if_occupied(port: int, host: str = "127.0.0.1"):
    """Tự động kiểm tra và giải phóng cổng nếu có tiến trình máy chủ cũ còn kẹt (tránh lỗi WinError 10048)."""
    import socket
    import subprocess

    try:
        if os.name == "nt":
            out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True, stderr=subprocess.DEVNULL)
            killed_any = False
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        print(f"[*] Phát hiện tiến trình cũ (PID {pid}) đang chiếm cổng {port}. Đang tự động giải phóng...")
                        subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        killed_any = True
            if killed_any:
                for _ in range(30):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        try:
                            s.bind((host, port))
                            break
                        except OSError:
                            time.sleep(0.15)
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex((host, port)) == 0:
                    subprocess.run(f"fuser -k {port}/tcp", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(0.6)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Cyber Surveillance Hub - He thong Giam sat Video Da Luong AI"
    )
    parser.add_argument(
        "--source",
        default="0",
        help="Nguồn video: 0 (webcam mặc định) hoặc đường dẫn file video (.mp4, .avi)"
    )
    parser.add_argument(
        "--mode",
        choices=["web", "hud"],
        default="web",
        help="Chế độ chạy: 'web' (Giao diện Web Cyber Dashboard hợp nhất, mặc định) hoặc 'hud' (Cửa sổ OpenCV Desktop)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host chạy Web Server (mặc định: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port chạy Web Server (mặc định: 8000)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Không tự động mở trình duyệt web khi khởi động"
    )

    args = parser.parse_args()

    video_source = int(args.source) if args.source.isdigit() else args.source

    if args.mode == "hud":
        print("[*] Đang khởi động Cửa sổ OpenCV Desktop Cyber Command Center...")
        from tests.test_command_center import CyberCommandCenterApp
        app = CyberCommandCenterApp(video_source=video_source)
        app.start()
    else:
        client_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
        url = f"http://{client_host}:{args.port}"
        print("=" * 70)
        print("   HỆ THỐNG GIÁM SÁT VIDEO ĐA LUỒNG — HỌC PHẦN HỆ ĐIỀU HÀNH")
        print("=" * 70)
        print(f"[*] Khởi động Web Server tại: {url}")
        print(f"[*] Hợp nhất 2 Chế độ:")
        print(f"    1. Live Camera Surveillance (MJPEG 30 FPS + Skeleton 17 điểm)")
        print(f"    2. Video Import (Local File & Web URL qua yt-dlp) + CapCut Timeline Trimmer")
        print(f"[*] Token Guard: Giới hạn ngân sách Gemini < 1,500 Tokens / video")
        print("=" * 70)

        # Tự động giải phóng cổng 8000 nếu có tiến trình máy chủ cũ còn kẹt
        free_port_if_occupied(args.port, client_host)

        if not args.no_browser:
            threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()

        import uvicorn
        from core.web_server import app, LIVE_CAMERA
        LIVE_CAMERA.video_source = video_source
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
