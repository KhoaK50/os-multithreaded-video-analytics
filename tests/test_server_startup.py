"""
Unit test for Web Server Startup (<1s), Health Readiness Probe, and Browser Launcher.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.
"""
import os
import sys
import time
import json
import socket
import unittest
import threading
import urllib.request
import urllib.error
from unittest.mock import patch

# Đảm bảo import được các module từ thư mục gốc
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Đảm bảo UTF-8 output trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from core.config import CONFIG
from core.video_annotator import VideoAnnotatorEngine
from core.web_server import app
from main import open_browser_when_ready


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestServerStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = get_free_port()
        cls.url = f"http://127.0.0.1:{cls.port}"
        cls.config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=cls.port,
            log_level="error"
        )
        cls.server = uvicorn.Server(cls.config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.t_start = time.time()
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.server_thread.join(timeout=3.0)

    def test_01_server_startup_latency(self):
        """Kiểm tra máy chủ mở cổng và phản hồi HTTP 200 trong vòng < 1.0 giây."""
        health_url = f"{self.url}/health"
        responded = False
        elapsed = 0.0

        for _ in range(40):  # Thử mỗi 50ms trong tối đa 2 giây
            try:
                req = urllib.request.Request(
                    health_url,
                    headers={"User-Agent": "FastAPIReadinessProbeTest/1.0"}
                )
                with urllib.request.urlopen(req, timeout=0.1) as resp:
                    if resp.status == 200:
                        elapsed = time.time() - self.t_start
                        responded = True
                        break
            except Exception:
                time.sleep(0.02)

        self.assertTrue(responded, f"Máy chủ không phản hồi tại {health_url}")
        self.assertLess(elapsed, 1.0, f"Thời gian khởi động ({elapsed:.3f}s) vượt quá chỉ tiêu 1.0 giây!")
        print(f"\n[TEST PASS] Cổng {self.port} mở và phản hồi HTTP 200 sau {elapsed:.3f}s (< 1.0s)")

    def test_02_health_endpoints_content(self):
        """Kiểm tra nội dung trả về của cả /health và /api/health."""
        for path in ["/health", "/api/health"]:
            url = f"{self.url}{path}"
            req = urllib.request.Request(url, headers={"User-Agent": "HealthTest/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))

                self.assertEqual(data.get("status"), "healthy")
                self.assertTrue(data.get("ready"))
                self.assertIn("server_time", data)
                self.assertIn("ai_status", data)
                self.assertIn(data.get("ai_status"), ["ready", "warming_up"])
                self.assertIn("device", data)
                self.assertIn("active_camera", data)
                print(f"[TEST PASS] Endpoint {path} trả về dữ liệu chuẩn: {data}")

    def test_03_open_browser_when_ready(self):
        """Kiểm tra hàm open_browser_when_ready chỉ mở trình duyệt khi nhận HTTP 200."""
        with patch("webbrowser.open") as mock_browser_open:
            result = open_browser_when_ready(self.url, timeout=5.0, check_interval=0.05)
            self.assertTrue(result)
            mock_browser_open.assert_called_once_with(self.url)
            print("[TEST PASS] open_browser_when_ready đã gọi webbrowser.open thành công sau khi xác nhận HTTP 200.")

    def test_04_annotator_engine_non_blocking_init(self):
        """Kiểm tra VideoAnnotatorEngine khởi tạo nhanh không chặn đồng bộ."""
        t0 = time.time()
        engine = VideoAnnotatorEngine(auto_warmup=False)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 0.5, f"Khởi tạo VideoAnnotatorEngine quá lâu: {elapsed:.3f}s")
        self.assertFalse(engine.is_ready)
        print(f"[TEST PASS] VideoAnnotatorEngine khởi tạo trong {elapsed:.4f}s (is_ready=False).")

    def test_05_config_device_lazy_property(self):
        """Kiểm tra CONFIG.DEVICE là lazy property trả về chuỗi hợp lệ."""
        dev = CONFIG.DEVICE
        self.assertIn(dev, ["cuda:0", "cuda", "cpu"])
        self.assertIsNotNone(CONFIG._cached_device)
        print(f"[TEST PASS] CONFIG.DEVICE đánh giá lazy thành công: {dev}")


if __name__ == "__main__":
    unittest.main()
