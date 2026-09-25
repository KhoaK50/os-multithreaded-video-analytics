"""
Unit test kiểm thử tự động toàn diện:
1. Sẵn sàng máy chủ (/health).
2. Live Camera Toggle & Trạng thái (/api/camera/toggle).
3. Bảng nhật ký hành vi thời gian thực (/api/camera/logs).
4. Chụp ảnh Snapshot cục bộ 100% bằng OpenCV buffer (/api/camera/snapshot).
5. Phục vụ ảnh Snapshot tĩnh qua HTTP (/api/snapshots/<name>).
6. Tinh chỉnh bộ lọc camera: Lật gương, Chống chói, Khử nhiễu (/api/camera/settings).
7. Đo lường thông số tải hệ điều hành thu gọn (/api/telemetry).
8. Khởi chạy HTTP socket server thực tế và kiểm tra phản hồi từ xa.
"""

import os
import sys
import time
import socket
import unittest
import threading
import urllib.request
import json
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
import uvicorn
from core.web_server import app, LIVE_CAMERA


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestLiveCameraBehaviorLogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        
        # Chạy máy chủ uvicorn thực tế trên cổng ngẫu nhiên trong luồng nền
        cls.port = get_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=cls.port,
            log_level="error"
        )
        cls.server = uvicorn.Server(cls.config)
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        # Đợi cổng mở
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"{cls.base_url}/health", timeout=0.2) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.server_thread.join(timeout=2.0)

    def test_01_readiness_probe(self):
        """Kiểm tra máy chủ sẵn sàng HTTP 200 OK ngay khi mở cổng."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertTrue(data.get("ready"))

    def test_02_compact_telemetry(self):
        """Kiểm tra dữ liệu đo lường thu gọn OS Telemetry."""
        resp = self.client.get("/api/telemetry")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("cpu_percent", data)
        self.assertIn("ram_percent", data)
        self.assertIn("fps", data)
        self.assertIn("biomechanics", data)
        self.assertIn("camera_settings", data)

    def test_03_camera_enhancer_settings(self):
        """Kiểm tra bật/tắt bộ lọc hình ảnh Lật gương, Chống chói và Khử nhiễu."""
        # GET
        resp = self.client.get("/api/camera/settings")
        self.assertEqual(resp.status_code, 200)
        settings = resp.json().get("settings", {})
        self.assertIn("mirror", settings)
        self.assertIn("anti_glare", settings)
        self.assertIn("denoise", settings)

        # POST
        payload = {"mirror": True, "anti_glare": False, "denoise": True}
        resp = self.client.post("/api/camera/settings", json=payload)
        self.assertEqual(resp.status_code, 200)
        updated = resp.json().get("settings", {})
        self.assertTrue(updated.get("mirror"))
        self.assertFalse(updated.get("anti_glare"))
        self.assertTrue(updated.get("denoise"))

    def test_04_behavior_event_log_and_snapshot(self):
        """Kiểm tra tạo log hành vi và trích xuất keyframe snapshot cục bộ (0 token API)."""
        # Giả lập 1 khung hình trong buffer camera
        dummy_frame = np.full((480, 640, 3), 128, dtype=np.uint8)
        with LIVE_CAMERA.frame_lock:
            LIVE_CAMERA.latest_raw_frame = dummy_frame

        # Chụp snapshot thủ công
        snap_resp = self.client.post("/api/camera/snapshot")
        self.assertEqual(snap_resp.status_code, 200)
        snap_data = snap_resp.json()
        self.assertEqual(snap_data.get("status"), "success")
        entry = snap_data.get("entry")
        self.assertIsNotNone(entry)
        self.assertTrue(entry.get("code").startswith("NORM-") or entry.get("code").startswith("WARN-"))
        self.assertIn("snapshot_url", entry)

        # Lấy danh sách nhật ký
        logs_resp = self.client.get("/api/camera/logs")
        self.assertEqual(logs_resp.status_code, 200)
        logs_data = logs_resp.json()
        self.assertGreaterEqual(logs_data.get("total", 0), 1)

        # Tải file ảnh snapshot qua HTTP tĩnh
        img_url = entry["snapshot_url"]
        img_resp = self.client.get(img_url)
        self.assertEqual(img_resp.status_code, 200)
        self.assertGreater(len(img_resp.content), 500)
        self.assertEqual(img_resp.headers.get("content-type"), "image/jpeg")

    def test_05_clear_behavior_logs(self):
        """Kiểm tra xóa danh sách nhật ký hành vi."""
        clear_resp = self.client.post("/api/camera/logs/clear")
        self.assertEqual(clear_resp.status_code, 200)
        self.assertEqual(clear_resp.json().get("total"), 0)

        logs_resp = self.client.get("/api/camera/logs")
        self.assertEqual(logs_resp.json().get("total"), 0)

    def test_06_real_http_socket_communication(self):
        """Kiểm tra kết nối thực tế qua giao thức HTTP TCP socket (trình duyệt thực)."""
        # 1. Test /health qua urllib
        with urllib.request.urlopen(f"{self.base_url}/health", timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["status"], "healthy")

        # 2. Test / qua urllib
        with urllib.request.urlopen(f"{self.base_url}/", timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            html = resp.read().decode("utf-8")
            self.assertIn("live-full-container", html)
            self.assertIn("behavior-table", html)
            self.assertIn("snapshot-modal", html)
            self.assertIn("timeline-table", html)

        # 3. Test /api/telemetry qua urllib
        with urllib.request.urlopen(f"{self.base_url}/api/telemetry", timeout=1.0) as resp:
            self.assertEqual(resp.status, 200)
            tel = json.loads(resp.read().decode("utf-8"))
            self.assertIn("cpu_percent", tel)
            self.assertIn("fps", tel)

    def test_07_predictive_behavior_entry(self):
        """Kiểm tra cấu trúc sự kiện hành vi bao gồm trường dự đoán 4 giây tiếp theo."""
        dummy_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
        entry = LIVE_CAMERA._record_behavior_log(
            frame=dummy_frame,
            posture="Đang làm việc với máy tính",
            angle=85.0,
            alert="Tư thế làm việc tập trung cao độ",
            is_danger=False,
            severity="safe",
            prediction_next_4s="Dự kiến: Tiếp tục gõ bàn phím và nhập liệu"
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["action"], "Đang làm việc với máy tính")
        self.assertIn("prediction_next_4s", entry)
        self.assertEqual(entry["prediction_next_4s"], "Dự kiến: Tiếp tục gõ bàn phím và nhập liệu")

        # Verify entry in logs API
        resp = self.client.get("/api/camera/logs")
        self.assertEqual(resp.status_code, 200)
        logs = resp.json().get("logs", [])
        self.assertTrue(any("prediction_next_4s" in item for item in logs))


if __name__ == "__main__":
    unittest.main()
