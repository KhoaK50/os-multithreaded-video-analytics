import os
import sys
import unittest
import numpy as np
import cv2

from core.video_annotator import VideoAnnotatorEngine, format_time

class TestTimelineSegmenter(unittest.TestCase):
    """
    Kiểm thử chuyên sâu tính năng Phân đoạn Timeline (Temporal Behavior Segmenter),
    Tracking đối tượng liên tục (ByteTrack), và tạo Heatmap.
    """

    def setUp(self):
        self.engine = VideoAnnotatorEngine()
        self.test_dir = os.path.join(os.path.dirname(__file__), "..", "recordings")
        os.makedirs(self.test_dir, exist_ok=True)

    def test_format_time(self):
        self.assertEqual(format_time(0), "00:00")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(3661), "61:01")

    def test_process_short_synthetic_video(self):
        # Tạo 1 video giả lập 3 giây (30fps = 90 frames)
        dummy_path = os.path.join(self.test_dir, "test_synthetic_timeline.mp4")
        out_path = os.path.join(self.test_dir, "test_synthetic_annotated.mp4")

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(dummy_path, fourcc, 30.0, (320, 240))
        for i in range(90):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            # Giả lập vẽ 1 khối người
            cv2.rectangle(frame, (100, 50), (220, 200), (200, 200, 200), -1)
            cv2.putText(frame, f"F:{i}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            writer.write(frame)
        writer.release()

        try:
            result = self.engine.process_video(
                input_path=dummy_path,
                output_path=out_path,
                start_time=0.0,
                end_time=3.0,
                call_gemini=False
            )

            # Kiểm tra các trường dữ liệu kết quả
            self.assertIn("timeline_segments", result)
            self.assertIn("heatmap_data", result)
            self.assertIn("entities_detected", result)
            self.assertIn("overall_danger_level", result)
            self.assertIn("duration_seconds", result)

            # Xác minh danh sách phân đoạn
            segments = result["timeline_segments"]
            self.assertIsInstance(segments, list)
            self.assertGreaterEqual(len(segments), 1)

            first_seg = segments[0]
            self.assertIn("segment_id", first_seg)
            self.assertIn("time_range", first_seg)
            self.assertIn("entities", first_seg)
            self.assertIn("severity", first_seg)
            self.assertIn("snapshot_url", first_seg)

            # Xác minh Heatmap
            heatmap = result["heatmap_data"]
            self.assertIsInstance(heatmap, list)
            self.assertGreater(len(heatmap), 0)

            # Xác minh video output được tạo
            self.assertTrue(os.path.exists(out_path))
            self.assertGreater(os.path.getsize(out_path), 0)

        finally:
            if os.path.exists(dummy_path):
                try:
                    os.remove(dummy_path)
                except Exception:
                    pass
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass

if __name__ == "__main__":
    unittest.main()
