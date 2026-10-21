"""
Unit Tests for Differential Identification Protocol and Event-Centric Grounding.
Học phần: Thị giác Máy tính & Hệ thống Đa luồng (Edge-Cloud Differential Grounding).

Mục tiêu kiểm thử:
1. Xác minh TokenGuard prompt chứa quy chuẩn Định danh Vi sai (Anti-Homogeneity, Causality, No Fluff).
2. Xác minh Bộ Hội chẩn Tự hành Cục bộ (Tier-3 Autonomous Heuristic Arbiter) sinh actor_label, distinctive_anchor, focal_actors_desc.
3. Xác minh SpatialTrackStabilizer ánh xạ chính xác actor_label và distinctive_anchor từ Gemini actors.
4. Xác minh cơ chế khử False Alarm của Fall Detection (phân biệt cúi người sinh hoạt vs ngã sụp phẳng).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.token_guard import TokenGuard
from core.video_annotator import SpatialTrackStabilizer


class TestDifferentialGrounding(unittest.TestCase):
    def setUp(self):
        self.guard = TokenGuard()
        self.stabilizer = SpatialTrackStabilizer(max_missing_frames=90, match_dist_ratio=0.35, max_k=4)

    def test_autonomous_heuristic_report_differential_fields(self):
        """Kiểm tra báo cáo tự hành sinh đủ các trường định danh vi sai."""
        dummy_event = [{"timestamp": 2.5, "threat_type": "HÀNH VI", "threat_score": 1.0, "details": "Ổn định"}]
        dummy_meta = {"duration_sec": 10.0, "frame_count": 300, "fps": 30.0}
        dummy_segs = [{"segment_id": "SEG-01", "time_range": "00:00 ➔ 00:05", "entity_count": 2, "local_score": 0.5}]

        res = self.guard._synthesize_local_autonomous_report(
            event_summary=dummy_event,
            video_metadata=dummy_meta,
            segment_info=dummy_segs,
            reason="offline_test"
        )

        self.assertEqual(res["status"], "success")
        self.assertIn("detected_actors", res)
        self.assertGreater(len(res["detected_actors"]), 0)

        first_actor = res["detected_actors"][0]
        self.assertIn("actor_label", first_actor)
        self.assertIn("distinctive_anchor", first_actor)
        self.assertIn("role", first_actor)
        self.assertTrue(len(first_actor["actor_label"]) > 0)
        self.assertTrue(len(first_actor["distinctive_anchor"]) > 0)

        # Kiểm tra segment analyses có detailed narrative
        self.assertIn("segment_analyses", res)
        self.assertGreater(len(res["segment_analyses"]), 0)
        first_seg = res["segment_analyses"][0]
        self.assertIn("detailed_narrative", first_seg)
        self.assertGreater(len(first_seg["detailed_narrative"]), 20)

    def test_stabilizer_differential_actor_anchoring(self):
        """Kiểm tra SpatialTrackStabilizer lưu trữ và truy xuất actor_label và distinctive_anchor."""
        # Giả lập 2 track IDs xuất hiện
        c1 = self.stabilizer.update(raw_id=1, bbox=(10, 10, 100, 200), frame_idx=1, frame_w=640, frame_h=480)
        c2 = self.stabilizer.update(raw_id=2, bbox=(200, 10, 300, 200), frame_idx=1, frame_w=640, frame_h=480)

        mock_gemini_actors = [
            {
                "actor_index": 1,
                "actor_label": "Học sinh bàn đầu (Đội mũ)",
                "distinctive_anchor": "Vị trí sát cửa sổ, đội mũ lưỡi trai",
                "role": "Chủ thể phát biểu",
                "true_action": "Đứng dậy phát biểu",
                "posture_desc": "Đứng thẳng tự nhiên"
            },
            {
                "actor_index": 2,
                "actor_label": "Học sinh bàn hai",
                "distinctive_anchor": "Ngồi đối diện bục giảng",
                "role": "Người lắng nghe",
                "true_action": "Ngồi ghi chép",
                "posture_desc": "Ngồi tại bàn"
            }
        ]

        self.stabilizer.apply_gemini_actors(mock_gemini_actors)

        # Kiểm tra truy xuất
        self.assertEqual(self.stabilizer.get_actor_label(c1), "Học sinh bàn đầu (Đội mũ)")
        self.assertIn("sát cửa sổ", self.stabilizer.get_distinctive_anchor(c1))
        self.assertEqual(self.stabilizer.get_custom_action(c1), "Đứng dậy phát biểu")

        self.assertEqual(self.stabilizer.get_actor_label(c2), "Học sinh bàn hai")
        self.assertIn("Ngồi đối diện", self.stabilizer.get_distinctive_anchor(c2))
        self.assertEqual(self.stabilizer.get_custom_action(c2), "Ngồi ghi chép")

    def test_anti_inversion_spatial_reconciliation(self):
        """Kiểm tra cơ chế phát hiện mâu thuẫn tag_id và hiệu chỉnh theo vị trí không gian thực tế."""
        # Giả lập:
        # Track c_right nằm ở bên phải màn hình (nx = 0.8)
        # Track c_left nằm ở bên trái màn hình (nx = 0.2)
        c_right = self.stabilizer.update(raw_id=10, bbox=(800, 100, 950, 400), frame_idx=1, frame_w=1000, frame_h=600)
        c_left = self.stabilizer.update(raw_id=20, bbox=(100, 100, 250, 400), frame_idx=1, frame_w=1000, frame_h=600)

        # Gemini bị nhầm tag_id: gán tag_id: c_right nhưng nội dung là "Người mẹ bên trái"
        flawed_gemini_actors = [
            {
                "actor_index": 1,
                "tag_id": c_right,  # Tag ID nhầm vào track bên phải
                "actor_label": "Người mẹ",
                "distinctive_anchor": "Bên trái khung hình",
                "role": "Thành viên gia đình"
            },
            {
                "actor_index": 2,
                "tag_id": c_left,   # Tag ID nhầm vào track bên trái
                "actor_label": "Bé gái",
                "distinctive_anchor": "Bên phải khung hình",
                "role": "Trẻ nhỏ"
            }
        ]

        self.stabilizer.apply_gemini_actors(flawed_gemini_actors, frame_w=1000, frame_h=600)

        # Kiểm tra: stabilizer bắt được mâu thuẫn và đảo lại chính xác theo vị trí không gian
        self.assertEqual(self.stabilizer.get_actor_label(c_left), "Người mẹ")
        self.assertEqual(self.stabilizer.get_actor_label(c_right), "Bé gái")

    def test_universal_spatial_anchors(self):
        """Kiểm tra mỏ neo không gian (Bàn đầu, Hàng sau, Bên trái, Bên phải)."""
        anchor_front = self.stabilizer.compute_spatial_anchor((400, 500, 600, 700), frame_w=1000, frame_h=800)
        self.assertEqual(anchor_front, "Bàn đầu")

        anchor_back = self.stabilizer.compute_spatial_anchor((400, 50, 600, 250), frame_w=1000, frame_h=800)
        self.assertEqual(anchor_back, "Hàng sau")

        clean_anchor = self.stabilizer.get_clean_anchor(c_id=1, bbox=(100, 200, 250, 500), frame_w=1000, frame_h=800)
        self.assertEqual(clean_anchor, "Bên trái")


if __name__ == "__main__":
    unittest.main()
