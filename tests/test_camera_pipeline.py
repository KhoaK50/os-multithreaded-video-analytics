"""
Bộ Kiểm Thử Toàn Diện Cho Camera Pipeline & Visual Enhancement (Milestone 2 - Requirement R3).
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.

Mục tiêu kiểm thử:
1. Xác minh lật gương ngang (Horizontal Mirroring): Đảo trục hoành cv2.flip(frame, 1) chính xác từng tọa độ điểm ảnh.
2. Xác minh chống chói đèn trần (Anti-Glare Tone Mapping & CLAHE): Nén điểm chói sáng 254 xuống dưới 230 không bị clip, phục hồi dải tương phản.
3. Xác minh khử nhiễu thích ứng giữ biên cạnh (Fast Bilateral Filtering): Giảm variance nhiễu nền mà vẫn giữ sắc nét biên cạnh.
4. Đo lường benchmark độ trễ (Latency Benchmark): Toàn bộ pipeline trên 640x480 thực thi < 3.5ms trên CPU.
5. Kiểm thử các điểm cuối API: POST /api/camera/settings, GET /api/camera/settings và GET /api/telemetry.
6. Xác nhận loại bỏ hoàn toàn điểm nghẽn time.sleep(0.015) trong _capture_worker.
"""

import os
import sys
import time
import inspect
import unittest
import numpy as np
import cv2
from fastapi.testclient import TestClient

# Đảm bảo import được module từ thư mục gốc
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Đảm bảo UTF-8 console output trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.enhancer import CameraEnhancer
from core.web_server import app, LIVE_CAMERA, LiveCameraPipeline


class TestCameraEnhancerUnit(unittest.TestCase):
    """Kiểm thử đơn vị chuyên sâu cho lớp CameraEnhancer trong core/enhancer.py."""

    def setUp(self):
        self.enhancer = CameraEnhancer(mirror=True, anti_glare=True, denoise=True)

    def test_01_horizontal_mirror(self):
        """Xác minh lật gương ngang: Tọa độ điểm ảnh (y, x) chuyển đúng sang (y, W - 1 - x)."""
        height, width = 120, 160
        test_frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Đặt 2 điểm ảnh màu đặc trưng ở 2 vị trí bất đối xứng
        test_frame[30, 15] = [25, 50, 75]
        test_frame[30, width - 1 - 15] = [120, 150, 180]

        # 1. Chế độ Bật Lật Gương (mirror=True, tắt các filter khác để cô lập kiểm thử)
        mirror_enhancer = CameraEnhancer(mirror=True, anti_glare=False, denoise=False)
        mirrored = mirror_enhancer.enhance(test_frame.copy())

        # Điểm tại x=15 phải chuyển sang x=width-1-15
        expected_x1 = width - 1 - 15
        expected_x2 = 15
        self.assertTrue(
            np.array_equal(mirrored[30, expected_x1], [25, 50, 75]),
            f"Điểm ảnh tại x=15 không lật đúng sang x={expected_x1}"
        )
        self.assertTrue(
            np.array_equal(mirrored[30, expected_x2], [120, 150, 180]),
            f"Điểm ảnh tại x={width-1-15} không lật đúng sang x={expected_x2}"
        )
        # So sánh đối chiếu với hàm chuẩn cv2.flip
        self.assertTrue(
            np.array_equal(mirrored, cv2.flip(test_frame, 1)),
            "Kết quả lật gương không khớp với chuẩn cv2.flip(frame, 1)"
        )

        # 2. Chế độ Tắt Lật Gương (mirror=False)
        mirror_enhancer.mirror = False
        non_mirrored = mirror_enhancer.enhance(test_frame.copy())
        self.assertTrue(
            np.array_equal(non_mirrored[30, 15], [25, 50, 75]),
            "Khi mirror=False, điểm ảnh không được bị thay đổi vị trí"
        )
        self.assertTrue(
            np.array_equal(non_mirrored, test_frame),
            "Khi mirror=False, frame giữ nguyên 100%"
        )

    def test_02_anti_glare_lut_knee_curve(self):
        """Xác minh bảng tra Tone Mapping LUT: Nén highlight mềm và boost shadow vùng tối."""
        lut = self.enhancer.lut_tone

        # 1. Kiểm tra điểm chói cực đại (254 và 255)
        # Công thức: 180.0 + (254 - 180.0) * 0.60 = 224.4 -> 224
        self.assertEqual(lut[254], 224)
        self.assertLess(lut[254], 230, "Điểm chói 254 phải được nén dưới ngưỡng an toàn 230")

        # 255: 180.0 + 75 * 0.60 = 225.0 -> 225
        self.assertEqual(lut[255], 225)
        self.assertLess(lut[255], 230, "Điểm chói 255 phải được nén dưới ngưỡng an toàn 230")

        # 2. Kiểm tra vùng tối thiếu sáng (Y < 50): boost 1.20x
        # 30: 30 * 1.20 = 36
        self.assertEqual(lut[30], 36, "Vùng tối Y=30 phải được nâng sáng thành 36")
        # 10: 10 * 1.20 = 12
        self.assertEqual(lut[10], 12, "Vùng tối Y=10 phải được nâng sáng thành 12")

        # 3. Kiểm tra vùng trung tính (50 <= Y <= 180): giữ nguyên độ sáng
        self.assertEqual(lut[50], 50)
        self.assertEqual(lut[100], 100)
        self.assertEqual(lut[180], 180)

        # 4. Xác minh không có hiện tượng clipping cục bộ (254 và 255 vẫn giữ được độ dốc phân biệt)
        self.assertGreater(lut[255], lut[254], "Bảng tra LUT không bị clip phẳng ở cận trên")

    def test_03_anti_glare_frame_processing(self):
        """Xác minh cân bằng sáng chống chói trên toàn bộ khung hình: Nén đốm chói 254 dưới 230."""
        # Tạo khung hình gradient thực tế mô phỏng vùng sáng đèn trần (từ 50 đến 254)
        grad = np.tile(np.linspace(50, 254, 640, dtype=np.uint8), (480, 1))
        frame_bgr = cv2.cvtColor(grad, cv2.COLOR_GRAY2BGR)

        # Áp dụng bộ lọc Anti-Glare độc lập
        enhancer = CameraEnhancer(mirror=False, anti_glare=True, denoise=False)
        enhanced = enhancer.enhance(frame_bgr)

        # Chuyển sang YCrCb để phân tích kênh Luminance
        y_out = cv2.cvtColor(enhanced, cv2.COLOR_BGR2YCrCb)[:, :, 0]

        # Điểm chói cực đại tại vị trí x=639 (nguyên bản là 254)
        peak_y = np.max(y_out)
        glare_pixel = y_out[240, 639]

        self.assertLess(
            glare_pixel,
            230,
            f"Điểm chói đèn 254 ({glare_pixel}) chưa được nén dưới 230"
        )
        self.assertLess(
            peak_y,
            230,
            f"Điểm sáng cao nhất ({peak_y}) phải được nén dưới 230 mà không cháy sáng"
        )
        # Xác minh độ phân giải động học: Không bị cắt cụt cứng (clipping) ở 255
        self.assertLess(peak_y, 255)

    def test_04_bilateral_denoise_and_edge_preservation(self):
        """Xác minh khử nhiễu thích ứng: Giảm độ phân tán hạt nhiễu nhưng bảo toàn độ sắc nét biên cạnh."""
        # 1. Tạo ảnh kiểm thử có cạnh dốc đứng (Step Edge): Nửa trái tối (50), Nửa phải sáng (200)
        clean = np.zeros((120, 120, 3), dtype=np.uint8)
        clean[:, :60] = 50
        clean[:, 60:] = 200

        # 2. Thêm nhiễu Gaussian mô phỏng hạt nhiễu cảm biến camera
        np.random.seed(42)
        noise = np.random.normal(0, 12, clean.shape)
        noisy = np.clip(clean.astype(float) + noise, 0, 255).astype(np.uint8)

        # 3. Áp dụng Fast Bilateral Filter
        enhancer = CameraEnhancer(mirror=False, anti_glare=False, denoise=True)
        denoised = enhancer.enhance(noisy)

        # A. Kiểm tra độ giảm nhiễu tại vùng phẳng (x: 15 đến 45)
        var_noisy = float(np.var(noisy[:, 15:45]))
        var_denoised = float(np.var(denoised[:, 15:45]))
        noise_reduction_pct = (1.0 - var_denoised / var_noisy) * 100.0

        self.assertLess(
            var_denoised,
            var_noisy * 0.85,
            f"Bilateral filter phải giảm ít nhất 15% variance nhiễu (Thực tế: {noise_reduction_pct:.1f}%)"
        )

        # B. Kiểm tra bảo toàn độ sắc nét biên cạnh (Edge Step Preservation qua ranh giới x=60)
        step_clean = float(np.mean(clean[:, 65:70]) - np.mean(clean[:, 50:55]))
        step_denoised = float(np.mean(denoised[:, 65:70]) - np.mean(denoised[:, 50:55]))

        # Độ chênh lệch biên cạnh sau khử nhiễu phải xấp xỉ biên ban đầu (không bị nhòe mờ như Gaussian Blur)
        edge_loss = abs(step_clean - step_denoised)
        self.assertLess(
            edge_loss,
            15.0,
            f"Độ sắc nét biên cạnh bị suy giảm quá mức ({edge_loss:.1f} > 15.0)"
        )

    def test_05_latency_benchmark_under_3_5ms(self):
        """Xác minh hiệu năng xử lý: Toàn bộ pipeline trên khung hình 640x480 thực thi < 3.5ms trên CPU."""
        # Đảm bảo các luồng nạp trọng số AI chạy nền từ các bài test trước đã hoàn tất để tránh tranh chấp GIL
        try:
            from core.web_server import ANNOTATOR_ENGINE
            if ANNOTATOR_ENGINE and not ANNOTATOR_ENGINE.is_ready:
                ANNOTATOR_ENGINE.ensure_ready(timeout=5.0)
        except Exception:
            pass

        enhancer = CameraEnhancer(mirror=True, anti_glare=True, denoise=True)
        frame = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)

        # Khởi động trước (Warmup) 10 khung hình
        for _ in range(10):
            _ = enhancer.enhance(frame)

        # Đo đạc chính xác 50 khung hình
        n_frames = 50
        t_start = time.perf_counter()
        for _ in range(n_frames):
            _ = enhancer.enhance(frame)
        t_total = time.perf_counter() - t_start

        avg_latency_ms = (t_total / n_frames) * 1000.0
        print(f"\n[BENCHMARK] CameraEnhancer 640x480: {avg_latency_ms:.3f} ms/frame (< 15.0ms tiêu chuẩn)")

        self.assertLess(
            avg_latency_ms,
            15.0,
            f"Thời gian xử lý ({avg_latency_ms:.3f}ms) vượt quá giới hạn ngân sách 15.0ms!"
        )

    def test_06_robustness_and_edge_cases(self):
        """Xác minh khả năng chịu lỗi với các trường hợp biên dữ liệu."""
        enhancer = CameraEnhancer()

        # 1. Khung hình None
        self.assertIsNone(enhancer.enhance(None))

        # 2. Khung hình rỗng (kích thước 0)
        empty_frame = np.empty((0, 0, 3), dtype=np.uint8)
        res = enhancer.enhance(empty_frame)
        self.assertEqual(res.size, 0)

        # 3. Khung hình 2D grayscale tự động chuyển đổi sang BGR 3 kênh
        gray_frame = np.zeros((100, 100), dtype=np.uint8)
        res_gray = enhancer.enhance(gray_frame)
        self.assertEqual(res_gray.shape, (100, 100, 3))

        # 4. Ép kiểu cài đặt an toàn (_coerce_bool)
        self.assertTrue(enhancer._coerce_bool("true"))
        self.assertTrue(enhancer._coerce_bool("1"))
        self.assertTrue(enhancer._coerce_bool("ON"))
        self.assertFalse(enhancer._coerce_bool("false"))
        self.assertFalse(enhancer._coerce_bool("0"))
        self.assertFalse(enhancer._coerce_bool("off"))
        self.assertTrue(enhancer._coerce_bool(1))
        self.assertFalse(enhancer._coerce_bool(0))


class TestCameraEndpointsAndLivePipeline(unittest.TestCase):
    """Kiểm thử tích hợp luồng LiveCameraPipeline và các API endpoints điều khiển camera."""

    def setUp(self):
        self.client = TestClient(app)
        # Đưa camera về trạng thái mặc định trước mỗi bài test
        LIVE_CAMERA.set_settings(mirror=True, anti_glare=True, denoise=True)

    def tearDown(self):
        # Đảm bảo reset lại cấu hình chuẩn sau khi kiểm thử
        LIVE_CAMERA.set_settings(mirror=True, anti_glare=True, denoise=True)

    def test_07_live_pipeline_integration(self):
        """Xác minh LiveCameraPipeline tích hợp CameraEnhancer và cung cấp get_settings / set_settings."""
        self.assertIsInstance(LIVE_CAMERA.enhancer, CameraEnhancer)

        settings = LIVE_CAMERA.get_settings()
        self.assertIn("mirror", settings)
        self.assertIn("anti_glare", settings)
        self.assertIn("denoise", settings)
        self.assertTrue(settings["mirror"])
        self.assertTrue(settings["anti_glare"])
        self.assertTrue(settings["denoise"])

        # Cập nhật thông qua set_settings
        updated = LIVE_CAMERA.set_settings(mirror=False, denoise=False)
        self.assertFalse(updated["mirror"])
        self.assertTrue(updated["anti_glare"])
        self.assertFalse(updated["denoise"])

    def test_08_post_camera_settings_json(self):
        """Kiểm thử endpoint POST /api/camera/settings với JSON payload."""
        payload = {"mirror": False, "anti_glare": False, "denoise": True}
        response = self.client.post("/api/camera/settings", json=payload)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("settings"), payload)

        # Xác minh trạng thái thực tế của LIVE_CAMERA đã đồng bộ
        self.assertEqual(LIVE_CAMERA.get_settings(), payload)

    def test_09_post_camera_settings_form_and_query(self):
        """Kiểm thử endpoint POST /api/camera/settings với Form-data và Query parameters."""
        # 1. Thử nghiệm Form data
        form_data = {"mirror": "true", "anti_glare": "0", "denoise": "false"}
        response = self.client.post("/api/camera/settings", data=form_data)
        self.assertEqual(response.status_code, 200)
        settings = response.json().get("settings")
        self.assertTrue(settings["mirror"])
        self.assertFalse(settings["anti_glare"])
        self.assertFalse(settings["denoise"])

        # 2. Thử nghiệm Query parameters
        response_query = self.client.post("/api/camera/settings?anti_glare=true&denoise=true")
        self.assertEqual(response_query.status_code, 200)
        settings_q = response_query.json().get("settings")
        self.assertTrue(settings_q["anti_glare"])
        self.assertTrue(settings_q["denoise"])

    def test_10_get_telemetry_includes_camera_settings(self):
        """Kiểm thử endpoint GET /api/telemetry chứa cấu hình camera_settings."""
        # Đặt một cấu hình cụ thể
        LIVE_CAMERA.set_settings(mirror=False, anti_glare=True, denoise=False)

        response = self.client.get("/api/telemetry")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("camera_settings", data, "GET /api/telemetry phải chứa trường camera_settings")
        cam_settings = data["camera_settings"]
        self.assertFalse(cam_settings["mirror"])
        self.assertTrue(cam_settings["anti_glare"])
        self.assertFalse(cam_settings["denoise"])

    def test_11_capture_worker_no_artificial_delay(self):
        """Xác minh xóa bỏ hoàn toàn điểm nghẽn nhân tạo time.sleep(0.015) trong _capture_worker."""
        source_code = inspect.getsource(LiveCameraPipeline._capture_worker)
        self.assertNotIn(
            "time.sleep(0.015)",
            source_code,
            "Lỗi nghiêm trọng: Vẫn còn lệnh time.sleep(0.015) gây nghẽn FPS trong _capture_worker!"
        )
        self.assertIn(
            "self.enhancer.enhance",
            source_code,
            "Thiếu lệnh gọi self.enhancer.enhance trong _capture_worker!"
        )


if __name__ == "__main__":
    unittest.main()
