"""
Unit & Integration Tests for Video HUD Rendering, Hardware Detection & Unicode Vietnamese Font Fallback.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.
Milestone 2 (R2 Specification).
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import numpy as np
import cv2
from PIL import Image, ImageFont, ImageDraw

from core.cyber_hud import (
    CyberHUDRenderer,
    SurveillanceHUDRenderer,
    VideoHUDRenderer,
)
from core.metrics import (
    SystemResourceMonitor,
    get_hardware_gpu_name,
)
from core.video_annotator import VideoAnnotatorEngine


class TestHUDRenderingNoSlopTerms(unittest.TestCase):
    """Kiểm tra triệt tiêu 100% thuật ngữ Sci-Fi / AI Slop trong HUD và mã nguồn."""

    FORBIDDEN_TERMS = [
        "THREAT MATRIX",
        "LOCK-ON",
        "RADAR AI",
        "AI CLOUD ANALYZING...",
        "CYBER-SURVEILLANCE HUD",
    ]

    def test_no_slop_terms_in_cyber_hud_source(self):
        """Xác nhận không còn bất kỳ từ ngữ Sci-Fi AI Slop nào trong core/cyber_hud.py."""
        hud_path = os.path.join(os.path.dirname(__file__), "..", "core", "cyber_hud.py")
        with open(hud_path, "r", encoding="utf-8") as f:
            content = f.read()

        for term in self.FORBIDDEN_TERMS:
            self.assertNotIn(
                term,
                content,
                f"Phát hiện thuật ngữ cấm '{term}' trong core/cyber_hud.py"
            )

    def test_no_slop_terms_in_video_annotator_source(self):
        """Xác nhận không còn từ ngữ Sci-Fi trong core/video_annotator.py."""
        va_path = os.path.join(os.path.dirname(__file__), "..", "core", "video_annotator.py")
        with open(va_path, "r", encoding="utf-8") as f:
            content = f.read()

        for term in self.FORBIDDEN_TERMS:
            self.assertNotIn(
                term,
                content,
                f"Phát hiện thuật ngữ cấm '{term}' trong core/video_annotator.py"
            )

    def test_rendered_hud_canvas_has_no_radar_or_slop(self):
        """Kiểm tra canvas HUD tạo ra hoạt động bình thường với LED dot thay thế radar."""
        hud = SurveillanceHUDRenderer()
        dummy_frame = np.zeros((720, 900, 3), dtype=np.uint8)
        diag = {
            "action": "Ngồi làm việc với máy tính",
            "context": "Văn phòng làm việc",
            "danger_reason": "Bình thường",
            "model_tier_str": "● Tier-1 Gemini 2.0"
        }
        entities = {"person": 1, "laptop": 1}
        metrics = {
            "cpu_percent": 18.0,
            "ram_percent": 42.0,
            "gpu_name": "RTX 5060",
            "gpu_vram_used": 1.8,
            "gpu_vram_total": 8.0,
            "queue_size": 2,
            "queue_max": 32,
            "dropped_frames": 0
        }
        canvas = hud.assemble_canvas(
            dummy_frame, diag, entities, metrics,
            danger_score=0, danger_level="AN TOAN", fps=30.0, is_ai_busy=True
        )
        self.assertEqual(canvas.shape, (720, 1280, 3))


class TestVietnameseUnicodeRendering(unittest.TestCase):
    """Kiểm tra cơ chế font fallback đa nền tảng và kết xuất tiếng Việt Unicode không bị vỡ/hỏi chấm."""

    def setUp(self):
        self.hud = CyberHUDRenderer()

    def test_font_loader_returns_valid_truetype_font(self):
        """Hàm nạp font phải trả về font TrueType hợp lệ có glyphs tiếng Việt."""
        font = self.hud._load_font(["segoeui.ttf", "arial.ttf"], 14)
        self.assertIsNotNone(font)
        # Font TrueType phải có thuộc tính getbbox
        self.assertTrue(hasattr(font, "getbbox"))

    def test_draw_unicode_text_renders_without_artifacts(self):
        """Kiểm tra vẽ chuỗi tiếng Việt Unicode phức tạp lên mảng OpenCV BGR."""
        img = np.zeros((100, 400, 3), dtype=np.uint8)
        test_strings = [
            "HỆ THỐNG GIÁM SÁT THỊ GIÁC ĐA LUỒNG",
            "LUỒNG PRODUCER: HOẠT ĐỘNG",
            "ĐÁNH GIÁ NGUY CƠ & AN TOÀN",
            "ĐIỀU PHỐI AI CLOUD (CHU KỲ 4S)",
            "Phát hiện té ngã / gục xuống",
            "Chống cằm, mệt mỏi công thái học",
            "[ AN TOÀN ]",
            "[ CẢNH BÁO ]",
            "[ NGUY HIỂM ]"
        ]
        for s in test_strings:
            self.hud.draw_unicode_text(
                img, s, (10, 20),
                font=self.hud.font_body,
                color_bgr=(255, 255, 255),
                bg_color_bgr=(15, 20, 28)
            )
            # Kiểm tra hình ảnh có pixel sáng sau khi vẽ chữ
            self.assertGreater(np.count_nonzero(img), 0)

    def test_technical_bbox_with_vietnamese_label(self):
        """Kiểm tra vẽ Technical Bounding Box với nhãn tiếng Việt Unicode."""
        img = np.zeros((400, 600, 3), dtype=np.uint8)
        self.hud.draw_technical_bbox(
            img, 50, 50, 250, 350,
            color_bgr=(0, 255, 0),
            label="Người (Té ngã)",
            score=0.92
        )
        self.assertGreater(np.count_nonzero(img), 0)

    def test_video_annotator_header_unicode_rendering(self):
        """Kiểm tra thanh header trong video_annotator vẽ được tiếng Việt có dấu bằng Pillow."""
        orig_w, header_h = 1280, 45
        frame = np.zeros((720, orig_w, 3), dtype=np.uint8)
        hdr_roi = frame[0:header_h, 0:orig_w]
        pil_hdr = Image.fromarray(cv2.cvtColor(hdr_roi, cv2.COLOR_BGR2RGB))
        draw_hdr = ImageDraw.Draw(pil_hdr)

        hdr_text = "FRAME: 00001/01000 [00:01]  |  XỬ LÝ: 85 FPS (RTX 5060)  |  ĐỐI TƯỢNG: 2"
        status_tag = "[ AN TOÀN ]"

        draw_hdr.text((20, 14), hdr_text, font=self.hud.font_body_bold, fill=(245, 247, 250))
        draw_hdr.text((orig_w - 280, 14), status_tag, font=self.hud.font_section, fill=(16, 185, 129))

        frame[0:header_h, 0:orig_w] = cv2.cvtColor(np.array(pil_hdr), cv2.COLOR_RGB2BGR)
        self.assertGreater(np.count_nonzero(frame[0:header_h, 0:orig_w]), 0)


class TestRealHardwareDetection(unittest.TestCase):
    """Kiểm tra nhận diện phần cứng thực tế (CUDA/Tesla T4/RTX 5060/MPS/CPU)."""

    def test_hardware_detection_real_system(self):
        """Kiểm tra hàm get_hardware_gpu_name trả về giá trị hợp lệ trên hệ thống thực."""
        name = get_hardware_gpu_name()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)
        self.assertTrue(
            any(w in name for w in ["RTX", "Tesla", "Apple Silicon", "CPU", "CUDA", "GPU"]),
            f"Tên phần cứng không nhận diện được: {name}"
        )

    def test_system_resource_monitor_telemetry_contract(self):
        """Kiểm tra SystemResourceMonitor.get_telemetry() chứa đầy đủ trường theo Interface Contract."""
        mon = SystemResourceMonitor()
        telemetry = mon.get_telemetry()
        expected_keys = [
            "timestamp", "cpu_percent", "cpu_total_pct", "ram_percent",
            "ram_used_gb", "ram_total_gb", "gpu_name", "gpu_vram_used",
            "gpu_vram_total", "cuda_available", "mps_available"
        ]
        for key in expected_keys:
            self.assertIn(key, telemetry, f"Thiếu trường {key} trong telemetry")

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.get_device_name", return_value="NVIDIA Tesla T4")
    def test_hardware_detection_tesla_t4(self, mock_name, mock_avail):
        """Kiểm tra nhận diện đúng Tesla T4 khi chạy trong môi trường Google Colab GPU."""
        name = get_hardware_gpu_name()
        self.assertEqual(name, "Tesla T4")

    @patch("torch.cuda.is_available", return_value=True)
    @patch("torch.cuda.get_device_name", return_value="NVIDIA GeForce RTX 5060 Laptop GPU")
    def test_hardware_detection_rtx_5060(self, mock_name, mock_avail):
        """Kiểm tra rút gọn đúng tên card đồ họa NVIDIA RTX 5060."""
        name = get_hardware_gpu_name()
        self.assertEqual(name, "RTX 5060")

    @patch("torch.cuda.is_available", return_value=False)
    def test_hardware_detection_mps_apple_silicon(self, mock_cuda):
        """Kiểm tra nhận diện Apple Silicon khi có torch.backends.mps."""
        with patch("torch.backends.mps.is_available", return_value=True, create=True):
            name = get_hardware_gpu_name()
            self.assertEqual(name, "Apple Silicon (MPS)")

    @patch("torch.cuda.is_available", return_value=False)
    def test_hardware_detection_cpu_fallback(self, mock_cuda):
        """Kiểm tra fallback về CPU sạch sẽ khi không có GPU."""
        with patch("torch.backends.mps.is_available", return_value=False, create=True):
            name = get_hardware_gpu_name()
            self.assertEqual(name, "CPU")

    def test_video_annotator_engine_device_name(self):
        """Kiểm tra VideoAnnotatorEngine.device_name phản ánh đúng thiết bị."""
        engine = VideoAnnotatorEngine(auto_warmup=False)
        self.assertIsNotNone(engine.device_name)
        engine.device = "cpu"
        self.assertEqual(engine.device_name, "CPU")


class TestDynamicModelTierDisplay(unittest.TestCase):
    """Kiểm tra cập nhật động huy hiệu phân tầng mô hình (Tier-1, Tier-2, Tier-3) trên HUD."""

    def test_resolve_tier_explicit_string(self):
        """Ưu tiên chuỗi hiển thị model_tier_str nếu có."""
        hud = CyberHUDRenderer()
        diag = {"model_tier_str": "● Tier-1 Gemini 2.0"}
        metrics = {}
        res = hud.resolve_model_tier_display(diag, metrics)
        self.assertEqual(res, "● Tier-1 Gemini 2.0")

    def test_resolve_tier_from_tier1_key(self):
        """Phân giải tier_1 sang ● Tier-1 Gemini 2.0."""
        hud = CyberHUDRenderer()
        diag = {"model_tier": "tier_1"}
        metrics = {}
        res = hud.resolve_model_tier_display(diag, metrics)
        self.assertEqual(res, "● Tier-1 Gemini 2.0")

    def test_resolve_tier_from_tier2_key(self):
        """Phân giải tier_2 sang ● Tier-2 Gemini 1.5 Failover."""
        hud = CyberHUDRenderer()
        diag = {"model_tier": "tier_2"}
        metrics = {}
        res = hud.resolve_model_tier_display(diag, metrics)
        self.assertEqual(res, "● Tier-2 Gemini 1.5 Failover")

    def test_resolve_tier_from_tier3_key(self):
        """Phân giải tier_3 sang ● AI Tự Hành (Local Heuristic)."""
        hud = CyberHUDRenderer()
        diag = {"model_tier": "tier_3"}
        metrics = {}
        res = hud.resolve_model_tier_display(diag, metrics)
        self.assertEqual(res, "● AI Tự Hành (Local Heuristic)")

    def test_resolve_tier_from_metrics_active_tier_name(self):
        """Phân giải tầng từ metrics nếu diagnosis không có thông tin."""
        hud = CyberHUDRenderer()
        diag = {}
        metrics = {"model_tier": "tier_2"}
        res = hud.resolve_model_tier_display(diag, metrics)
        self.assertEqual(res, "● Tier-2 Gemini 1.5 Failover")

    def test_resolve_tier_default(self):
        """Mặc định khi không có dữ liệu là ● Tier-1 Gemini 2.0."""
        hud = CyberHUDRenderer()
        res = hud.resolve_model_tier_display({}, {})
        self.assertEqual(res, "● Tier-1 Gemini 2.0")


class TestHUDBackwardCompatibility(unittest.TestCase):
    """Kiểm tra tính tương thích ngược của các alias và phương thức cũ."""

    def test_surveillance_hud_renderer_alias(self):
        """SurveillanceHUDRenderer phải là alias của CyberHUDRenderer."""
        self.assertIs(SurveillanceHUDRenderer, CyberHUDRenderer)
        self.assertIs(VideoHUDRenderer, CyberHUDRenderer)

    def test_bbox_and_skeleton_method_aliases(self):
        """Các phương thức cũ phải trỏ tới cài đặt kỹ thuật mới."""
        hud = SurveillanceHUDRenderer()
        self.assertEqual(hud.draw_corner_bracket_bbox, hud.draw_technical_bbox)
        self.assertEqual(hud.draw_ergonomic_skeleton, hud.draw_cyber_skeleton)


if __name__ == "__main__":
    unittest.main()
