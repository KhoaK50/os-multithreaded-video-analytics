import unittest
import numpy as np
from core.video_annotator import SpatialTrackStabilizer, KinematicAnomalyRanker
from core.token_guard import TokenGuard


class TestCombatDetectionAndRoleRefinement(unittest.TestCase):
    """Kiểm tra nhận diện tư thế xung đột và triệt tiêu dán nhãn 'Bế em bé'."""

    def test_spatial_track_stabilizer_no_false_child(self):
        """Kiểm tra người ngồi hoặc ở xa không bị gán nhãn 'Trẻ nhỏ / Em bé'."""
        stabilizer = SpatialTrackStabilizer(max_k=4)
        # Giả lập đối tượng nhỏ hơn do ở xa (bbox_h = 100 trên frame 720)
        c_id = stabilizer.update(1, (100, 100, 200, 200), frame_idx=0, frame_w=1280, frame_h=720)
        for f in range(1, 10):
            stabilizer.update(1, (100, 100, 200, 200), frame_idx=f, frame_w=1280, frame_h=720)
        stabilizer.finalize_roles(frame_h=720)
        role = stabilizer.get_role(c_id)
        self.assertNotIn("Trẻ nhỏ", role)
        self.assertNotIn("Em bé", role)

    def test_local_autonomous_report_identifies_clash_danger(self):
        """Kiểm tra Tier-3 Local Arbiter phát hiện xung đột và báo NGUY HIỂM thay vì AN TOÀN."""
        tg = TokenGuard(api_key="mock_key")
        event_summary = [
            {
                "timestamp": 2.5,
                "person_id": 1,
                "threat_type": "CẢNH BÁO: XUNG ĐỘT THỂ XÁC",
                "details": "Xung đột thể xác / Giằng co va chạm",
                "threat_score": 8.5
            }
        ]
        video_metadata = {"duration_sec": 10.0, "frame_count": 300, "fps": 30.0, "audio_status": "none"}
        report = tg._synthesize_local_autonomous_report(event_summary, video_metadata)

        self.assertEqual(report["threat_level"], "NGUY HIỂM")
        self.assertFalse(report["is_safe_environment"])
        self.assertIn("Xung đột thể xác", report["primary_incident"])
        self.assertNotIn("Sinh hoạt gia đình", report["primary_incident"])
        self.assertNotIn("Bế em bé", report["primary_incident"])


if __name__ == "__main__":
    unittest.main()
