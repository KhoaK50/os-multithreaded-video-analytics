import unittest
import numpy as np
from core.video_annotator import KinematicAnomalyRanker

class TestKinematicAnomalyRanker(unittest.TestCase):

    def setUp(self):
        self.ranker = KinematicAnomalyRanker(top_k=4)

    def _make_dummy_kpts(self, wrist_y_offset=0, knee_y_offset=0):
        # 17 keypoints (x, y, conf)
        kpts = np.zeros((17, 3), dtype=np.float32)
        kpts[:, 2] = 0.9  # high confidence
        # Shoulders (5, 6)
        kpts[5] = [200, 100, 0.9]
        kpts[6] = [240, 100, 0.9]
        # Wrists (9, 10)
        kpts[9] = [190, 140 + wrist_y_offset, 0.9]
        kpts[10] = [250, 140 + wrist_y_offset, 0.9]
        # Knees (13, 14)
        kpts[13] = [210, 240 + knee_y_offset, 0.9]
        kpts[14] = [230, 240 + knee_y_offset, 0.9]
        # Ankles (15, 16)
        kpts[15] = [210, 300, 0.9]
        kpts[16] = [230, 300, 0.9]
        return kpts

    def test_small_group_all_in_focus(self):
        """Khi video chỉ có <= 4 người, tất cả đều được giữ trong tiêu điểm."""
        detections = [
            {"raw_id": 1, "bbox": (50, 50, 100, 200), "conf": 0.9, "kpts": self._make_dummy_kpts()},
            {"raw_id": 2, "bbox": (150, 50, 200, 200), "conf": 0.9, "kpts": self._make_dummy_kpts()},
            {"raw_id": 3, "bbox": (250, 50, 300, 200), "conf": 0.9, "kpts": self._make_dummy_kpts()}
        ]
        res = self.ranker.update_frame(detections, frame_w=640, frame_h=480)
        self.assertEqual(len(res), 3)
        for det in res:
            self.assertTrue(det["is_focus"])
            self.assertFalse(det["is_ghost"])

    def test_crowd_filters_bystanders_and_spotlights_active_actors(self):
        """Khi có đám đông 7 người, người vung tay và người ngã phải được xếp vào Top-4."""
        # Frame 1: Cả 7 người đứng yên
        f1_dets = []
        for i in range(1, 8):
            f1_dets.append({
                "raw_id": i,
                "bbox": (50 * i, 100, 50 * i + 40, 300),
                "conf": 0.9,
                "kpts": self._make_dummy_kpts(),
                "torso_angle": 90.0,
                "threat_score": 0.0
            })
        self.ranker.update_frame(f1_dets, frame_w=1280, frame_h=720)

        # Frame 2:
        # Đối tượng 1 và 2: Xung đột, vung tay cực mạnh (wrist dịch chuyển lớn)
        # Đối tượng 3: Ngã xuống sàn (chiều cao bbox sụt giảm và torso_angle = 20)
        # Đối tượng 4, 5, 6, 7: Đứng yên xem (không dịch chuyển)
        f2_dets = []
        for i in range(1, 8):
            if i in (1, 2):
                # Vung tay mạnh
                kpts = self._make_dummy_kpts(wrist_y_offset=-60)
                bbox = (50 * i, 100, 50 * i + 40, 300)
                angle = 85.0
                threat = 5.0
            elif i == 3:
                # Ngã xuống sàn
                kpts = self._make_dummy_kpts()
                bbox = (150, 250, 250, 310) # Bbox sụt chiều cao
                angle = 20.0
                threat = 8.0
            else:
                # Đứng yên ngoài cuộc
                kpts = self._make_dummy_kpts()
                bbox = (50 * i, 100, 50 * i + 40, 300)
                angle = 90.0
                threat = 0.0

            f2_dets.append({
                "raw_id": i,
                "bbox": bbox,
                "conf": 0.9,
                "kpts": kpts,
                "torso_angle": angle,
                "threat_score": threat,
                "person_danger": (i == 3)
            })

        res = self.ranker.update_frame(f2_dets, frame_w=1280, frame_h=720)
        
        res_by_id = {d["raw_id"]: d for d in res}
        # Đối tượng 1, 2, 3 bắt buộc phải trong Top-4 Focus
        self.assertTrue(res_by_id[1]["is_focus"], "Kẻ xung đột #1 phải trong focus")
        self.assertTrue(res_by_id[2]["is_focus"], "Kẻ xung đột #2 phải trong focus")
        self.assertTrue(res_by_id[3]["is_focus"], "Nạn nhân ngã #3 phải trong focus")

        # Ít nhất 3 người đứng yên (5, 6, 7) phải bị gắn nhãn Ghosted
        ghost_count = sum(1 for d in res if d["is_ghost"])
        self.assertEqual(ghost_count, 3, "Có đúng 3 người ngoài cuộc vượt quá Top-4 bị Ghosted")

if __name__ == "__main__":
    unittest.main()
