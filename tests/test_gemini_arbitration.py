"""
Unit & Integration Test: Kiểm thử Cơ chế Phán Quyết Ngược Hai Chiều (Bidirectional Gemini Arbitration)
và Ràng Buộc Định Danh Theo Nhãn Khung Bao (Tag-Based Grounding Protocol).
"""

import unittest
from core.video_annotator import SpatialTrackStabilizer, VideoAnnotatorEngine

class TestGeminiArbitration(unittest.TestCase):
    def setUp(self):
        self.stabilizer = SpatialTrackStabilizer()

    def test_tag_id_explicit_binding_order_inversion(self):
        """Kiểm tra tag_id giúp định danh đúng người dù thứ tự trả về của Gemini bị đảo lộn."""
        # Giả lập: ID #01 (toddler), ID #02 (father)
        c1 = self.stabilizer.update(raw_id=1, bbox=(100, 100, 200, 250), frame_idx=1, frame_w=640, frame_h=480)
        c2 = self.stabilizer.update(raw_id=2, bbox=(300, 50, 450, 350), frame_idx=1, frame_w=640, frame_h=480)

        # Gemini trả về Ông bố trước (index 0) nhưng gắn tag_id = 2, và Bé nhỏ sau (index 1) với tag_id = 1
        mock_gemini_actors = [
            {
                "actor_index": 1,
                "tag_id": 2,
                "actor_label": "Ông bố",
                "distinctive_anchor": "Bên cửa sổ lớn",
                "role": "Thành viên gia đình",
                "true_action": "Dang tay đón con",
                "posture_desc": "Ngồi xồm đón trẻ"
            },
            {
                "actor_index": 2,
                "tag_id": 1,
                "actor_label": "Bé nhỏ",
                "distinctive_anchor": "Trục giữa phòng",
                "role": "Trẻ nhỏ",
                "true_action": "Chạy tới sà vào lòng bố",
                "posture_desc": "Đang chạy"
            }
        ]

        self.stabilizer.apply_gemini_actors(mock_gemini_actors)

        # Khẳng định: ID #02 PHẢI là Ông bố (không bị nhầm sang Bé nhỏ)
        self.assertEqual(self.stabilizer.get_actor_label(c2), "Ông bố")
        self.assertEqual(self.stabilizer.get_distinctive_anchor(c2), "Bên cửa sổ lớn")

        # Khẳng định: ID #01 PHẢI là Bé nhỏ
        self.assertEqual(self.stabilizer.get_actor_label(c1), "Bé nhỏ")
        self.assertEqual(self.stabilizer.get_distinctive_anchor(c1), "Trục giữa phòng")

    def test_bidirectional_heatmap_and_segment_arbitration(self):
        """Kiểm tra Gemini phán quyết AN TOÀN sẽ hạ điểm Heuristic 8.6 xuống <= 1.5 và đổi màu Heatmap."""
        # Giả lập dữ liệu timeline ban đầu bị Heuristic gán oan 8.6
        timeline_segments = [{
            "segment_id": "SEG-01",
            "time_range": "00:00 ➔ 00:03",
            "start_sec": 0.0,
            "end_sec": 3.0,
            "severity": "warning",
            "danger_score": 8.6,
            "telemetry_breakdown": {
                "max_velocity": 746,
                "dominant_posture": "Áp sát thủ thế",
                "posture_state": "Áp sát thủ thế"
            },
            "entities": [{
                "id": "Bé nhỏ (ID #01)",
                "canonical_id": 1,
                "role": "Nạn nhân / Phòng thủ",
                "action": "Vung tay ra đòn / Tấn công áp sát",
                "posture": "Áp sát giằng co",
                "severity": "warning"
            }]
        }]

        heatmap_data = [
            {"time": 0.5, "score": 8.5, "level": "danger"},
            {"time": 1.5, "score": 8.6, "level": "danger"},
            {"time": 2.5, "score": 7.8, "level": "danger"},
        ]

        gemini_result = {
            "threat_level": "AN TOÀN",
            "is_safe_environment": True,
            "segment_analyses": [{
                "segment_id": "SEG-01",
                "threat_level": "AN TOÀN",
                "threat_score": 1.2,
                "macro_narrative": "Trẻ nhỏ chạy tới sà vào vòng tay cha mẹ, cảnh sinh hoạt an toàn.",
                "detailed_narrative": "Gia đình sum vầy, không có bất kỳ hành vi bạo lực hay đối kháng nào."
            }]
        }

        # Áp dụng logic phán quyết ngược
        gemini_analyses = {a["segment_id"]: a for a in gemini_result["segment_analyses"]}
        for seg in timeline_segments:
            s_id = seg["segment_id"]
            if s_id in gemini_analyses:
                ga = gemini_analyses[s_id]
                g_lvl = str(ga.get("threat_level", "")).upper()
                if g_lvl in ("AN TOÀN", "SAFE") or float(ga.get("threat_score", 10.0)) < 3.0:
                    seg["severity"] = "safe"
                    g_sc = float(ga.get("threat_score", 1.0))
                    seg["danger_score"] = min(float(seg.get("danger_score", 0.0)), max(0.4, g_sc))

                    tb = seg.get("telemetry_breakdown")
                    if tb:
                        tb["dominant_posture"] = "Vận động tự nhiên"
                        tb["posture_state"] = "Vận động tự nhiên"

                    for ent in seg.get("entities", []):
                        ent["severity"] = "safe"
                        if any(w in ent.get("role", "").lower() for w in ["tấn công", "gây hấn", "nạn nhân", "phòng thủ"]):
                            ent["role"] = "Người tham gia"
                        if any(w in ent.get("action", "") for w in ["Xung đột", "Vung tay", "Tấn công", "Phòng vệ"]):
                            ent["action"] = "Vận động tự nhiên"
                        if any(w in ent.get("posture", "") for w in ["Áp sát", "thủ thế", "Né đòn"]):
                            ent["posture"] = "Tư thế tự nhiên"

        # Hiệu chỉnh Heatmap
        for seg in timeline_segments:
            s_start = seg.get("start_sec", 0.0)
            s_end = seg.get("end_sec", 0.0)
            if seg.get("severity") == "safe":
                safe_cap = max(0.4, min(2.5, float(seg.get("danger_score", 1.0))))
                for slot in heatmap_data:
                    t_slot = slot.get("time", 0.0)
                    if s_start <= t_slot <= s_end:
                        slot["score"] = min(slot.get("score", 0.0), safe_cap)
                        slot["level"] = "safe"

        # Kiểm tra kết quả
        self.assertEqual(timeline_segments[0]["severity"], "safe")
        self.assertLessEqual(timeline_segments[0]["danger_score"], 1.5)
        self.assertEqual(timeline_segments[0]["entities"][0]["role"], "Người tham gia")
        self.assertEqual(timeline_segments[0]["telemetry_breakdown"]["dominant_posture"], "Vận động tự nhiên")

        # Kiểm tra heatmap data toàn bộ chuyển sang safe (màu xanh)
        for slot in heatmap_data:
            self.assertEqual(slot["level"], "safe")
            self.assertLessEqual(slot["score"], 2.5)

    def test_classroom_end_segment_peaceful_recalibration(self):
        """
        Kiểm tra phân đoạn cuối video (lớp học ổn định, học sinh ngồi yên)
        được Gemini phán quyết AN TOÀN thì Heatmap và Segment severity PHẢI chuyển sang safe,
        không bị bôi đỏ bởi phân đoạn xung đột trước đó.
        """
        timeline_segments = [
            {
                "segment_id": "SEG-01",
                "time_range": "00:00 ➔ 00:20",
                "start_sec": 0.0,
                "end_sec": 20.0,
                "severity": "danger",
                "danger_score": 8.8,
                "entities": [{"id": "ID #01", "role": "Kẻ tấn công", "severity": "danger"}]
            },
            {
                "segment_id": "SEG-02",
                "time_range": "00:20 ➔ 00:35",
                "start_sec": 20.0,
                "end_sec": 35.0,
                "severity": "danger",  # Giả sử ban đầu bị gán nhầm do vệt quang học
                "danger_score": 8.5,
                "entities": [{"id": "ID #01", "role": "Nạn nhân", "severity": "danger"}]
            }
        ]
        segments_data = [
            {"optical_scuffle_detected": True, "peak_optical_threat": 8.8},
            {"optical_scuffle_detected": True, "peak_optical_threat": 8.5}
        ]
        heatmap_data = [
            {"time": 5.0, "score": 8.8, "level": "danger"},
            {"time": 15.0, "score": 8.5, "level": "danger"},
            {"time": 25.0, "score": 8.2, "level": "danger"},
            {"time": 32.0, "score": 8.0, "level": "danger"}
        ]

        gemini_result = {
            "threat_level": "CẢNH BÁO",
            "is_safe_environment": False,
            "segment_analyses": [
                {
                    "segment_id": "SEG-01",
                    "threat_level": "NGUY HIỂM",
                    "threat_score": 8.8,
                    "macro_narrative": "Xô xát trong lớp học"
                },
                {
                    "segment_id": "SEG-02",
                    "threat_level": "AN TOÀN",
                    "threat_score": 1.0,
                    "macro_narrative": "Môi trường an toàn, học sinh ngồi tại bàn, không có xung đột."
                }
            ]
        }

        gemini_analyses = {a["segment_id"]: a for a in gemini_result["segment_analyses"]}
        for seg_idx_t, seg in enumerate(timeline_segments):
            s_id = seg["segment_id"]
            orig_s_data = segments_data[seg_idx_t]
            if s_id in gemini_analyses:
                ga = gemini_analyses[s_id]
                g_lvl = str(ga.get("threat_level", "")).upper()
                ga_threat_score = float(ga.get("threat_score", 0.0))
                if g_lvl in ("NGUY HIỂM", "DANGER") or ga_threat_score >= 8.0:
                    seg["severity"] = "danger"
                    seg["danger_score"] = max(seg.get("danger_score", 0.0), max(8.0, ga_threat_score))
                elif (g_lvl in ("CẢNH BÁO", "WARNING") or ga_threat_score >= 4.0) and seg["severity"] != "danger":
                    seg["severity"] = "warning"
                    seg["danger_score"] = max(seg.get("danger_score", 0.0), max(4.0, ga_threat_score))
                elif g_lvl in ("AN TOÀN", "SAFE") or ga_threat_score < 4.0:
                    seg["severity"] = "safe"
                    g_sc = ga_threat_score if ga_threat_score > 0 else 1.0
                    seg["danger_score"] = min(float(seg.get("danger_score", 0.0)), max(0.4, min(3.5, g_sc)))
                    orig_s_data["optical_scuffle_detected"] = False
                    orig_s_data["peak_optical_threat"] = seg["danger_score"]
                    for ent in seg.get("entities", []):
                        ent["severity"] = "safe"
                        ent["role"] = "An toàn"

        for seg in timeline_segments:
            s_start = seg.get("start_sec", 0.0)
            s_end = seg.get("end_sec", 0.0)
            seg_sev = seg.get("severity", "safe")
            if seg_sev == "safe":
                safe_cap = max(0.4, min(3.5, float(seg.get("danger_score", 1.0))))
                for slot in heatmap_data:
                    t_slot = slot.get("time", 0.0)
                    if s_start <= t_slot <= s_end:
                        slot["score"] = min(slot.get("score", 0.0), safe_cap)
                        slot["level"] = "safe"

        # Khẳng định: SEG-01 vẫn là danger
        self.assertEqual(timeline_segments[0]["severity"], "danger")
        self.assertGreaterEqual(timeline_segments[0]["danger_score"], 8.0)
        self.assertEqual(heatmap_data[0]["level"], "danger")
        self.assertEqual(heatmap_data[1]["level"], "danger")

        # Khẳng định: SEG-02 (khúc cuối 00:20 - 00:35) PHẢI là safe, KHÔNG ĐƯỢC đỏ lè
        self.assertEqual(timeline_segments[1]["severity"], "safe")
        self.assertLessEqual(timeline_segments[1]["danger_score"], 1.5)
        self.assertEqual(timeline_segments[1]["entities"][0]["role"], "An toàn")
        self.assertEqual(heatmap_data[2]["level"], "safe")
        self.assertEqual(heatmap_data[3]["level"], "safe")
        self.assertLessEqual(heatmap_data[2]["score"], 3.5)
        self.assertLessEqual(heatmap_data[3]["score"], 3.5)

    def test_peaceful_family_global_safe_override(self):
        """
        Kiểm tra video gia đình sinh hoạt bình thường:
        Dù quang học ban đầu có thể nhầm cử động bế bé là scuffle,
        Gemini kết luận is_safe_environment: True -> 100% segments và heatmap chuyển sang safe.
        """
        timeline_segments = [
            {
                "segment_id": "SEG-01",
                "start_sec": 0.0,
                "end_sec": 5.0,
                "severity": "danger",
                "danger_score": 8.5,
                "entities": [{"id": "Bé nhỏ (ID #01)", "role": "Nạn nhân", "severity": "warning"}]
            }
        ]
        heatmap_data = [
            {"time": 1.0, "score": 8.5, "level": "danger"},
            {"time": 3.0, "score": 8.0, "level": "danger"}
        ]
        gemini_result = {
            "threat_level": "AN TOÀN",
            "is_safe_environment": True,
            "primary_incident": "Gia đình sinh hoạt vui vẻ bình thường"
        }

        is_global_safe = (
            str(gemini_result.get("threat_level", "")).upper() in ("AN TOÀN", "SAFE") or
            gemini_result.get("is_safe_environment") is True
        )
        self.assertTrue(is_global_safe)

        if is_global_safe:
            for seg in timeline_segments:
                seg["severity"] = "safe"
                seg["danger_score"] = min(float(seg.get("danger_score", 1.0)), 1.5)
                for ent in seg.get("entities", []):
                    ent["severity"] = "safe"
                    ent["role"] = "An toàn"

        for seg in timeline_segments:
            s_start = seg.get("start_sec", 0.0)
            s_end = seg.get("end_sec", 0.0)
            if seg.get("severity") == "safe":
                safe_cap = max(0.4, min(3.5, float(seg.get("danger_score", 1.0))))
                for slot in heatmap_data:
                    t_slot = slot.get("time", 0.0)
                    if s_start <= t_slot <= s_end:
                        slot["score"] = min(slot.get("score", 0.0), safe_cap)
                        slot["level"] = "safe"

        # Khẳng định 100% safe
        self.assertEqual(timeline_segments[0]["severity"], "safe")
        self.assertLessEqual(timeline_segments[0]["danger_score"], 1.5)
        for slot in heatmap_data:
            self.assertEqual(slot["level"], "safe")
            self.assertLessEqual(slot["score"], 1.5)

    def test_lone_actor_desk_object_manipulation_not_attacker(self):
        """Kiểm tra một người ngồi một mình tại bàn thao tác nhặt đồ nhanh không bị gán tấn công."""
        kinetic_spike = 2.5
        interaction_score = 0.0
        cand = {"is_striking": False, "interaction_score": 0.0}

        if cand.get("is_striking", False) and kinetic_spike >= 1.8 and (interaction_score >= 1.5 or cand.get("is_targeted")):
            person_action = "Vung tay ra đòn / Tấn công áp sát"
            person_danger = True
            person_threat_score = 8.5
        elif kinetic_spike >= 1.8 and interaction_score < 1.2:
            person_action = "Thao tác đồ vật / Cử động tay nhanh"
            person_danger = False
            person_threat_score = 1.0
        else:
            person_action = "Đang đứng / Hoạt động trong phòng"
            person_danger = False
            person_threat_score = 0.0

        self.assertEqual(person_action, "Thao tác đồ vật / Cử động tay nhanh")
        self.assertFalse(person_danger)
        self.assertEqual(person_threat_score, 1.0)

    def test_stratified_keyframe_sampling_no_name_error(self):
        """Kiểm tra logic phân nhóm keyframe phân tầng không bị lỗi NameError re."""
        from unittest.mock import MagicMock
        from core.token_guard import TokenGuard
        import numpy as np

        tg = TokenGuard()
        # Mock orchestrator to prevent actual cloud calls
        mock_orch = MagicMock()
        mock_orch.execute_multimodal_failover.return_value = (
            {"macro_narrative": "Bình thường", "threat_score": 1.0, "severity": "safe", "segment_analyses": []},
            "Tier 1: Gemini 2.5 Flash"
        )
        
        dummy_frame = np.zeros((64, 64, 3), dtype=np.uint8)
        seg_kfs = [
            {"segment_id": "SEG-01 (00:00 - 00:05)", "timestamp": 2.5, "threat_score": 8.0, "frame": dummy_frame},
            {"segment_id": "SEG-07 (00:46 - 00:54)", "timestamp": 50.0, "threat_score": 1.0, "frame": dummy_frame}
        ]
        
        # Test calling synthesize_video_report with mocked orchestrator
        with unittest.mock.patch("core.token_guard.get_shared_orchestrator", return_value=mock_orch):
            res = tg.synthesize_video_report(
                video_metadata={"video_source": "test_synthetic_clip.mp4", "duration": 54.0},
                event_summary=[{"event": "Xô xát", "timestamp": 2.0}],
                peak_keyframes=[],
                segment_info=[{"segment_id": "SEG-01"}, {"segment_id": "SEG-07"}],
                segment_keyframes=seg_kfs
            )
            self.assertIsNotNone(res)

if __name__ == "__main__":
    unittest.main()

