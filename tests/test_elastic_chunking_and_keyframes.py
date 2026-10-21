"""
Test Suite for Elastic Adaptive Chunking & Multi-Phase Keyframe Extraction.
Học phần: Hệ điều hành & Phân tích Động học Video Thông Minh.

Kiểm tra:
1. Tính chất toán học của thuật toán Phân đoạn Co Giãn Động (Elastic Adaptive Chunking):
   - Đảm bảo video ngắn (3s-7s) không bị băm vụn (< 3.5s).
   - Đảm bảo video trung bình (8s-28s) và dài (30s-60s+) phân bổ cân đối, không có phân đoạn thừa đuôi rác.
2. Trích xuất Keyframes Đa pha Thời gian (Multi-Phase Temporal Extraction):
   - Đảm bảo khi video an toàn / không có nguy cơ, hệ thống luôn trích xuất 3 mốc (Khởi phát -> Cao trào -> Hệ quả)
     thay vì chỉ gửi duy nhất 1 ảnh tĩnh cho Gemini.
3. Loại bỏ hoàn toàn nhãn võ đoán ("Ngồi tại bàn / Học tập", "Quan sát tĩnh", "Người quan sát không gian").
"""

import os
import sys
import unittest
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.token_guard import TokenGuard


class TestElasticChunkingAndKeyframes(unittest.TestCase):
    def setUp(self):
        self.guard = TokenGuard()

    def _compute_elastic_segments(self, clip_duration: float, start_time: float = 0.0):
        """Mô phỏng thuật toán Elastic Adaptive Chunking trong VideoAnnotator."""
        if clip_duration <= 7.0:
            num_segments = 1
        elif clip_duration <= 14.0:
            num_segments = 2
        elif clip_duration <= 28.0:
            num_segments = max(2, int(round(clip_duration / 6.0)))
        else:
            num_segments = max(3, int(round(clip_duration / 8.0)))

        seg_duration = clip_duration / float(num_segments)
        segments = []
        clip_end_time = start_time + clip_duration
        for s_i in range(num_segments):
            s_start = start_time + s_i * seg_duration
            s_end = clip_end_time if (s_i == num_segments - 1) else (start_time + (s_i + 1) * seg_duration)
            segments.append({
                "index": s_i + 1,
                "start_sec": s_start,
                "end_sec": s_end,
                "duration": s_end - s_start
            })
        return segments

    def test_short_clip_elastic_chunking(self):
        """Video 5s trên Action Datasets (UCF101/HMDB51) phải có đúng 1 phân đoạn 5s duy nhất."""
        segs_5s = self._compute_elastic_segments(5.0)
        self.assertEqual(len(segs_5s), 1)
        self.assertAlmostEqual(segs_5s[0]["duration"], 5.0)
        self.assertAlmostEqual(segs_5s[0]["start_sec"], 0.0)
        self.assertAlmostEqual(segs_5s[0]["end_sec"], 5.0)

        segs_3s = self._compute_elastic_segments(3.0)
        self.assertEqual(len(segs_3s), 1)
        self.assertAlmostEqual(segs_3s[0]["duration"], 3.0)

        segs_7s = self._compute_elastic_segments(7.0)
        self.assertEqual(len(segs_7s), 1)
        self.assertAlmostEqual(segs_7s[0]["duration"], 7.0)

    def test_medium_clip_elastic_chunking(self):
        """Video 8s - 14s chia đều 2 phân đoạn cân đối, không có phân đoạn nào < 3.5s."""
        segs_8s = self._compute_elastic_segments(8.0)
        self.assertEqual(len(segs_8s), 2)
        self.assertAlmostEqual(segs_8s[0]["duration"], 4.0)
        self.assertAlmostEqual(segs_8s[1]["duration"], 4.0)

        segs_10s = self._compute_elastic_segments(10.0)
        self.assertEqual(len(segs_10s), 2)
        self.assertAlmostEqual(segs_10s[0]["duration"], 5.0)
        self.assertAlmostEqual(segs_10s[1]["duration"], 5.0)

        segs_14s = self._compute_elastic_segments(14.0)
        self.assertEqual(len(segs_14s), 2)
        self.assertAlmostEqual(segs_14s[0]["duration"], 7.0)
        self.assertAlmostEqual(segs_14s[1]["duration"], 7.0)

    def test_long_clip_elastic_chunking(self):
        """Video 30s - 60s chia tối ưu theo chu kỳ ~8s, không có đuôi rác."""
        segs_30s = self._compute_elastic_segments(30.0)
        # 30 / 8 = 3.75 -> round = 4 phân đoạn (7.5s mỗi đoạn)
        self.assertEqual(len(segs_30s), 4)
        for s in segs_30s:
            self.assertGreaterEqual(s["duration"], 6.5)
            self.assertLessEqual(s["duration"], 9.0)

        segs_60s = self._compute_elastic_segments(60.0)
        # 60 / 8 = 7.5 -> round = 8 phân đoạn (7.5s mỗi đoạn)
        self.assertEqual(len(segs_60s), 8)
        for s in segs_60s:
            self.assertAlmostEqual(s["duration"], 7.5)

    def test_multi_phase_keyframe_extraction_empty_events(self):
        """Khi video an toàn (event_log rỗng), TokenGuard phải trích xuất 3 khung hình đa pha (Khởi phát, Cao trào, Hệ quả)."""
        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # Giả lập candidate_frames qua 5 giây (mỗi 0.5s có 1 frame)
        candidate_frames = {
            round(t, 1): dummy_frame for t in np.arange(0.0, 5.1, 0.5)
        }

        # Event log rỗng (như các video hành động thông thường, thể thao, sinh hoạt)
        event_log = []
        kfs = self.guard.select_peak_keyframes(
            event_log=event_log,
            candidate_frames=candidate_frames,
            max_keyframes=3
        )

        self.assertEqual(len(kfs), 3, "Bắt buộc phải trả về 3 khung hình đa pha thay vì 1 ảnh tĩnh!")
        timestamps = [k["timestamp"] for k in kfs]
        self.assertEqual(timestamps, sorted(timestamps), "Keyframes phải được sắp xếp theo thời gian tăng dần")
        # Khung hình đầu ở khoảng đầu (0.0s), khung giữa ở giữa (~2.5s), khung cuối ở cuối (5.0s)
        self.assertAlmostEqual(timestamps[0], 0.0, delta=0.5)
        self.assertAlmostEqual(timestamps[1], 2.5, delta=0.5)
        self.assertAlmostEqual(timestamps[2], 5.0, delta=0.5)

        threat_types = [k["threat_type"] for k in kfs]
        self.assertIn("KHỞI ĐẦU", threat_types[0])
        self.assertIn("CAO TRÀO", threat_types[1])
        self.assertIn("HỆ QUẢ", threat_types[2])

    def test_no_sitting_override_in_synthesize_report(self):
        """Báo cáo tự hành không được ép đè 'Ngồi tại bàn / Học tập' vào posture_override."""
        dummy_meta = {"duration_sec": 5.0, "frame_count": 150, "fps": 30.0}
        dummy_segs = [{"segment_id": "SEG-01", "time_range": "00:00 ➔ 00:05", "entity_count": 1, "local_score": 0.2}]
        res = self.guard._synthesize_local_autonomous_report(
            event_summary=[],
            video_metadata=dummy_meta,
            segment_info=dummy_segs,
            reason="test"
        )
        self.assertEqual(res["status"], "success")
        for seg in res.get("segment_analyses", []):
            self.assertIsNone(seg.get("posture_override"), "posture_override phải là None, không được ép 'Ngồi tại bàn'!")

        # Kiểm tra danh sách nhân vật không có nhãn người quan sát không gian sáo rỗng
        for act in res.get("detected_actors", []):
            self.assertNotIn("Quan sát không gian", act.get("action", ""))
            self.assertNotIn("Người quan sát không gian", act.get("actor_label", ""))


if __name__ == "__main__":
    unittest.main()
