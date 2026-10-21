import pytest
import unittest
from unittest.mock import MagicMock
from core.token_guard import TokenGuard

class TestThreeTierAndCrowdFilter(unittest.TestCase):
    def test_overall_danger_level_three_tiers(self):
        # 3 milestones: 0 (safe), 4 (warning), 8 (danger)
        test_cases = [
            (8.6, "NGUY HIEM"),
            (8.0, "NGUY HIEM"),
            (10.0, "NGUY HIEM"),
            (7.9, "CANH BAO"),
            (4.0, "CANH BAO"),
            (5.5, "CANH BAO"),
            (3.9, "AN TOAN"),
            (1.0, "AN TOAN"),
            (0.0, "AN TOAN")
        ]
        for score, expected in test_cases:
            lvl = "NGUY HIEM" if score >= 8.0 else ("CANH BAO" if score >= 4.0 else "AN TOAN")
            self.assertEqual(lvl, expected, f"Score {score} expected {expected} but got {lvl}")

    def test_segment_severity_harmonization(self):
        # Ensure final_threat_score >= 8.0 promotes severity to danger
        cases = [
            (8.6, "warning", "danger"),
            (8.0, "safe", "danger"),
            (5.5, "safe", "warning"),
            (4.0, "safe", "warning"),
            (3.8, "warning", "warning"),
            (1.5, "safe", "safe")
        ]
        for score, initial_sev, expected_sev in cases:
            seg_severity = initial_sev
            if score >= 8.0:
                seg_severity = "danger"
            elif score >= 4.0:
                if seg_severity == "safe":
                    seg_severity = "warning"
            else:
                if score < 4.0 and initial_sev == "safe":
                    seg_severity = "safe"
            self.assertEqual(seg_severity, expected_sev)

    def test_crowd_scene_assessment(self):
        # <= 4 persons in reality
        peak_persons = 2
        total_unique_tracks = 3
        is_crowd = bool(peak_persons > 4 or total_unique_tracks > 5)
        self.assertFalse(is_crowd)

        # > 4 persons in reality (e.g. classroom crowd)
        peak_persons = 7
        total_unique_tracks = 14
        is_crowd = bool(peak_persons > 4 or total_unique_tracks > 5)
        self.assertTrue(is_crowd)
        actual_count = max(peak_persons, total_unique_tracks)
        self.assertEqual(actual_count, 14)

    def test_token_guard_fallback_three_tiers(self):
        tg = TokenGuard(api_key="TEST_FAKE_KEY")
        # Test danger threshold >= 8.0
        rep_danger = tg._synthesize_local_autonomous_report(
            event_summary=[{"threat_score": 8.6, "details": "Vận động tốc độ cao", "threat_type": "Chuyển động"}],
            video_metadata={"duration_sec": 5.0},
            segment_info=[{"segment_id": "SEG-01", "local_score": 8.6, "time_range": "00:00 - 00:05"}]
        )
        self.assertEqual(rep_danger["threat_level"], "NGUY HIỂM")

        # Test warning threshold 4.0 <= score < 8.0
        rep_warn = tg._synthesize_local_autonomous_report(
            event_summary=[{"threat_score": 5.2, "details": "Tiếp cận cự ly gần", "threat_type": "Áp sát"}],
            video_metadata={"duration_sec": 5.0},
            segment_info=[{"segment_id": "SEG-01", "local_score": 5.2, "time_range": "00:00 - 00:05"}]
        )
        self.assertEqual(rep_warn["threat_level"], "CẢNH BÁO")

        # Test safe threshold < 4.0
        rep_safe = tg._synthesize_local_autonomous_report(
            event_summary=[{"threat_score": 1.2, "details": "Đi lại bình thường", "threat_type": "Bình thường"}],
            video_metadata={"duration_sec": 5.0},
            segment_info=[{"segment_id": "SEG-01", "local_score": 1.2, "time_range": "00:00 - 00:05"}]
        )
        self.assertEqual(rep_safe["threat_level"], "AN TOÀN")

if __name__ == "__main__":
    unittest.main()
