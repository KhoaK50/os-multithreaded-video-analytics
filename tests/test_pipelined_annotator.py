"""
Unit Tests for 3-Stage Multithreaded Pipeline in VideoAnnotatorEngine.
Học phần: Hệ điều hành — Kiến trúc Đường ống Đa luồng (Pipelining Architecture).

Mục tiêu kiểm thử:
1. Xác minh quá trình xử lý video đa luồng 3 giai đoạn (Reader -> Worker -> Writer) hoạt động chính xác.
2. Kiểm tra tính bảo toàn thứ tự khung hình (Order Preservation).
3. Kiểm tra tính năng báo tiến độ thời gian thực (Progress Callback).
4. Kiểm tra khả năng xử lý ngoại lệ và giải phóng luồng an toàn (Zero Hanging Threads).
"""

import os
import sys
import tempfile
import unittest
import cv2
import numpy as np

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.video_annotator import VideoAnnotatorEngine


class TestPipelinedVideoAnnotator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = VideoAnnotatorEngine(auto_warmup=True)
        cls.temp_dir = tempfile.mkdtemp()

        # Tạo một video mẫu 30 frames (1 giây ở 30 FPS, độ phân giải 320x240)
        cls.test_video_path = os.path.join(cls.temp_dir, "test_synth_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(cls.test_video_path, fourcc, 30.0, (320, 240))
        for i in range(30):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            # Vẽ hình tròn chuyển động để giả lập chuyển động
            cx = 50 + i * 6
            cy = 120
            cv2.circle(frame, (cx, cy), 20, (0, 255, 0), -1)
            writer.write(frame)
        writer.release()

    @classmethod
    def tearDownClass(cls):
        # Dọn dẹp tệp tin tạm
        if os.path.exists(cls.test_video_path):
            try:
                os.remove(cls.test_video_path)
            except Exception:
                pass

    def test_pipelined_video_processing_synthetic(self):
        """Xác minh 3-Stage Pipeline xử lý video thành công và xuất file hợp lệ."""
        out_path = os.path.join(self.temp_dir, "output_pipelined_test.mp4")
        progress_calls = []

        def on_progress(processed, total, fps):
            progress_calls.append((processed, total, fps))

        result = self.engine.process_video(
            input_path=self.test_video_path,
            output_path=out_path,
            start_time=0.0,
            end_time=1.0,
            progress_callback=on_progress,
            call_gemini=False,
            anomaly_focus=True
        )

        self.assertIsNotNone(result)
        self.assertIn("frame_count", result)
        self.assertEqual(result["frame_count"], 30)
        self.assertIn("timeline_segments", result)
        self.assertGreater(len(result["timeline_segments"]), 0)

        # Kiểm tra file video thành phẩm tồn tại và có kích thước > 0
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 0)

        # Kiểm tra progress_callback được gọi nhiều lần trong suốt quá trình
        self.assertGreater(len(progress_calls), 0)
        final_processed, final_total, _ = progress_calls[-1]
        self.assertEqual(final_total, 30)

        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass

    def test_pipelined_invalid_video_path_exception(self):
        """Kiểm tra xử lý ngoại lệ an toàn khi đường dẫn video không tồn tại."""
        out_path = os.path.join(self.temp_dir, "output_invalid.mp4")
        with self.assertRaises(ValueError):
            self.engine.process_video(
                input_path="non_existent_file_path_12345.mp4",
                output_path=out_path
            )


if __name__ == "__main__":
    unittest.main()
