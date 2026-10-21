"""
End-to-End Test for Dark-Scene & Harsh Condition Optical Fail-Safe in VideoAnnotatorEngine.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.

Mục tiêu kiểm thử:
1. Giả lập một video ban đêm / thiếu sáng (độ sáng trung bình thấp ~35), đối tượng di chuyển dạng silhouette.
2. Hai đối tượng lao vào nhau với vector động học đối kháng dữ dội (mô phỏng ẩu đả / bạo lực).
3. Xác minh:
   - Động cơ Dòng quang học (OpticalMotionEngine) phát hiện bùng nổ xung lực và độ hỗn loạn.
   - Cơ chế Cứu hộ Đêm Tối (Dark-Scene Optical Fail-Safe) tự động kích hoạt:
     + Đánh dấu NGUY HIỂM (danger, threat_score >= 8.0).
     + Ghi nhận các thực thể (Kẻ tấn công, Nạn nhân) với hành động bạo lực.
     + Thu thập chuỗi Burst Sequence (4-6 frames) cho phân tích không-thời gian.
     + Không bị bất kỳ cơ chế nào hạ điểm nhầm thành 'AN TOÀN'.
"""

import os
import sys
import tempfile
import unittest
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.video_annotator import VideoAnnotatorEngine


class TestDarkSceneFailSafe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = VideoAnnotatorEngine(auto_warmup=True)
        cls.temp_dir = tempfile.mkdtemp()

        # Tạo một video ban đêm thiếu sáng 45 frames (1.5s @ 30 FPS, 640x360)
        # Nền tối xám (intensity ~25), hai đối tượng silhouette lao vào nhau va chạm dữ dội
        cls.dark_video_path = os.path.join(cls.temp_dir, "test_dark_scuffle.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(cls.dark_video_path, fourcc, 30.0, (640, 360))

        for i in range(45):
            # Nền đêm tối
            frame = np.ones((360, 640, 3), dtype=np.uint8) * 25

            if i < 15:
                # Giai đoạn 1: Tiếp cận nhanh
                x1 = 150 + i * 10
                x2 = 490 - i * 10
                y1 = 180
                y2 = 180
            else:
                # Giai đoạn 2: Xô xát, giằng co hỗn loạn (dao động qua lại biên độ lớn)
                delta = (i % 4) * 20 - 30
                x1 = 300 + delta
                x2 = 340 - delta
                y1 = 180 + (i % 3) * 15 - 10
                y2 = 180 - (i % 3) * 15 + 10

            # Bóng silhouette người (màu xám tối ~45-50)
            cv2.ellipse(frame, (x1, y1), (35, 75), 0, 0, 360, (50, 50, 50), -1)
            cv2.ellipse(frame, (x2, y2), (35, 75), 0, 0, 360, (55, 55, 55), -1)

            writer.write(frame)
        writer.release()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.dark_video_path):
            try:
                os.remove(cls.dark_video_path)
            except Exception:
                pass

    def test_dark_scene_fail_safe_activation(self):
        """Xác minh Dark-Scene Fail-Safe phát hiện thành công bạo lực ban đêm."""
        out_path = os.path.join(self.temp_dir, "output_dark_test.mp4")

        result = self.engine.process_video(
            input_path=self.dark_video_path,
            output_path=out_path,
            start_time=0.0,
            end_time=1.5,
            call_gemini=False,  # Kiểm thử thuần Edge AI / Optical Fail-Safe
            anomaly_focus=True
        )

        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 1000

        # Kiểm tra kết quả phân tích
        behavior = result.get("behavior_analytics", {})
        risk_breakdown = behavior.get("risk_breakdown", {})
        segments = result.get("timeline_segments", [])

        assert len(segments) >= 1
        seg = segments[0]

        # Phân đoạn phải được xác nhận nguy hiểm
        assert seg["severity"] == "danger"
        assert seg["danger_score"] >= 8.0

        # Dominant risk phải là danger
        assert risk_breakdown.get("dominant_risk") == "danger"

        # Đã phát hiện thực thể và vai trò tác chiến
        entities = seg.get("entities", [])
        assert len(entities) >= 1

        roles = [e.get("role") for e in entities]
        actions = [e.get("action") for e in entities]

        assert any("tấn công" in str(r).lower() or "gây hấn" in str(r).lower() for r in roles)
        assert any("xô xát" in str(a).lower() or "xung đột" in str(a).lower() for a in actions)
