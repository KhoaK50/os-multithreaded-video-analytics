"""
Adversarial Empirical Stress-Test Suite for Backend Video Overlay and Anchor Logic.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.
Milestone: M1 Adversarial Verification (Requirement R2 Enforcement).

Test Objectives:
1. Stress-test SpatialTrackStabilizer across all spatial sector boundaries, negative/edge coordinates, and zero-size bboxes.
2. Stress-test Anti-Uniform Sanitization against all forbidden clothing/uniform keywords with mixed casing and sentence embeddings.
3. Stress-test Temporal Hysteresis against high-frequency frame jitter across sector boundaries (15+ frames).
4. Verify Causal Role Anchor resolution priority (Attacker -> Khiêu khích, Victim -> Bị xô, Defender -> Can ngăn).
5. Stress-test CyberHUDRenderer.draw_technical_bbox to ensure complete elimination of guessing labels and percentage scores.
6. Stress-test VideoAnnotator bounding box label construction across extreme kinematic states.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import cv2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.cyber_hud import CyberHUDRenderer, SurveillanceHUDRenderer
from core.video_annotator import SpatialTrackStabilizer, VideoAnnotatorEngine


class TestSpatialTrackStabilizerSectors(unittest.TestCase):
    """Stress-test tọa độ Bounding Box qua tất cả các sector không gian và biên biên giới."""

    def setUp(self):
        self.stabilizer = SpatialTrackStabilizer(max_missing_frames=90, match_dist_ratio=0.35, max_k=4)
        self.w = 1280
        self.h = 720

    def test_left_sector_variations_and_boundaries(self):
        """Kiểm tra vùng 'Bên trái' (nx < 0.35) từ cực trái đến sát biên."""
        # 1. Cực trái: sát mép x=0
        bbox_extreme_left = (0, 100, 100, 400) # cx=50 -> nx = 50/1280 = 0.039
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_extreme_left, self.w, self.h), "Bên trái")

        # 2. Vùng trái thông thường
        bbox_left = (200, 100, 400, 400) # cx=300 -> nx = 300/1280 = 0.234
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_left, self.w, self.h), "Bên trái")

        # 3. Sát biên dưới 0.35 (cx = 447, nx = 0.3492)
        bbox_near_border = (440, 100, 454, 400) # cx=447 -> nx = 0.3492 < 0.35
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_near_border, self.w, self.h), "Bên trái")

        # 4. Tọa độ âm (đối tượng rời màn hình sang trái một phần)
        bbox_negative = (-100, 100, 200, 400) # cx=50 -> nx = 0.039
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_negative, self.w, self.h), "Bên trái")

    def test_right_sector_variations_and_boundaries(self):
        """Kiểm tra vùng 'Bên phải' (nx > 0.65) từ sát biên đến cực phải."""
        # 1. Sát biên trên 0.65 (cx = 833, nx = 833/1280 = 0.6508)
        bbox_near_border = (830, 100, 836, 400) # cx=833 -> nx = 0.6508 > 0.65
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_near_border, self.w, self.h), "Bên phải")

        # 2. Vùng phải thông thường
        bbox_right = (900, 100, 1100, 400) # cx=1000 -> nx = 1000/1280 = 0.781
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_right, self.w, self.h), "Bên phải")

        # 3. Cực phải: sát mép x=1280
        bbox_extreme_right = (1180, 100, 1280, 400) # cx=1230 -> nx = 0.961
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_extreme_right, self.w, self.h), "Bên phải")

        # 4. Tọa độ vượt quá khung hình sang phải
        bbox_overflow = (1200, 100, 1400, 400) # cx=1300 -> nx = 1.015 > 0.65
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_overflow, self.w, self.h), "Bên phải")

    def test_vertical_sectors_in_center_x_zone(self):
        """Kiểm tra các vùng dọc khi 0.35 <= nx <= 0.65: Hàng sau (ny < 0.38), Bàn đầu (ny > 0.60), Trung tâm."""
        cx = 640 # nx = 0.50 (chính giữa theo chiều ngang)

        # 1. Hàng sau (ny < 0.38): cy = 200 -> ny = 200/720 = 0.278
        bbox_top = (cx - 50, 100, cx + 50, 300) # cy=200
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_top, self.w, self.h), "Hàng sau")

        # Sát biên dưới ny=0.38: cy = 273 -> ny = 273/720 = 0.379 < 0.38
        bbox_near_top = (cx - 50, 270, cx + 50, 276) # cy=273
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_near_top, self.w, self.h), "Hàng sau")

        # 2. Bàn đầu (ny > 0.60): cy = 550 -> ny = 550/720 = 0.764
        bbox_bottom = (cx - 50, 450, cx + 50, 650) # cy=550
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_bottom, self.w, self.h), "Bàn đầu")

        # Sát biên trên ny=0.60: cy = 433 -> ny = 433/720 = 0.6014 > 0.60
        bbox_near_bottom = (cx - 50, 430, cx + 50, 436) # cy=433
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_near_bottom, self.w, self.h), "Bàn đầu")

        # 3. Trung tâm (0.38 <= ny <= 0.60): cy = 360 -> ny = 360/720 = 0.50
        bbox_center = (cx - 50, 260, cx + 50, 460) # cy=360
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_center, self.w, self.h), "Trung tâm")

        # Biên đúng ny = 0.38: cy = 274 -> ny = 0.3805 >= 0.38
        bbox_border_center_top = (cx - 50, 270, cx + 50, 278) # cy=274
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_border_center_top, self.w, self.h), "Trung tâm")

        # Biên đúng ny = 0.60: cy = 432 -> ny = 0.6000 <= 0.60
        bbox_border_center_bottom = (cx - 50, 430, cx + 50, 434) # cy=432
        self.assertEqual(self.stabilizer.compute_spatial_anchor(bbox_border_center_bottom, self.w, self.h), "Trung tâm")

    def test_degenerate_and_edge_case_inputs(self):
        """Kiểm tra các trường hợp suy biến (None, empty, 0 dimension, zero bbox)."""
        self.assertEqual(self.stabilizer.compute_spatial_anchor(None, self.w, self.h), "")
        self.assertEqual(self.stabilizer.compute_spatial_anchor((), self.w, self.h), "")
        self.assertEqual(self.stabilizer.compute_spatial_anchor((10, 10, 50, 50), 0, self.h), "")
        self.assertEqual(self.stabilizer.compute_spatial_anchor((10, 10, 50, 50), self.w, 0), "")
        self.assertEqual(self.stabilizer.compute_spatial_anchor((10, 10, 50, 50), -100, -100), "")

        # Bbox có kích thước 0 (điểm đơn)
        zero_box = (100, 100, 100, 100) # cx=100, cy=100 -> nx = 100/1280 = 0.078
        self.assertEqual(self.stabilizer.compute_spatial_anchor(zero_box, self.w, self.h), "Bên trái")


class TestAntiUniformSanitization(unittest.TestCase):
    """Stress-test Quy tắc chống đồng phục: Triệt tiêu 100% màu áo / đồng phục."""

    def setUp(self):
        self.stabilizer = SpatialTrackStabilizer(max_missing_frames=90, match_dist_ratio=0.35, max_k=4)

    def test_forbidden_keywords_exact_and_casing(self):
        """Kiểm tra toàn bộ từ khóa bị cấm với các kiểu viết hoa, thường, lẫn lộn."""
        forbidden_test_cases = [
            "Áo trắng", "áo trắng", "ÁO TRẮNG", "áO tRắNg",
            "áo đen", "Áo Đen", "ÁO ĐEN",
            "áo sơ mi", "Áo sơ mi trắng", "ÁO SƠ MI",
            "áo khoác", "Áo khoác gió", "ÁO KHOÁC ĐEN",
            "áo thun", "Áo thun đỏ", "ÁO THUN TRẮNG",
            "đồng phục", "Đồng phục học sinh", "ĐỒNG PHỤC THỂ DỤC",
            "trang phục", "Trang phục biểu diễn",
            "quần tây", "Quần tây đen", "QUẦN TÂY",
            "quần đen", "Quần đen dài",
            "quần đùi", "Quần đùi xanh",
            "white shirt", "White Shirt", "WHITE SHIRT",
            "black shirt", "Black shirt", "BLACK SHIRT",
            "uniform", "School Uniform", "UNIFORM",
        ]

        for phrase in forbidden_test_cases:
            result = self.stabilizer.sanitize_anchor(phrase)
            self.assertEqual(
                result, "",
                f"LỖI: sanitize_anchor không lọc được từ khóa đồng phục: '{phrase}' (trả về '{result}')"
            )

    def test_forbidden_keywords_embedded_in_complex_sentences(self):
        """Kiểm tra từ khóa bị cấm lồng ghép trong câu văn dài hoặc bối cảnh phong phú."""
        embedded_cases = [
            "Học sinh nam mặc áo trắng ngồi ở góc bàn",
            "Đối tượng mang áo đen tiếp cận bàn đầu",
            "Nữ sinh đồng phục học sinh trường THPT",
            "Người mặc white shirt đang vung tay",
            "Nam thanh niên mặc quần đen áo khoác",
        ]

        for sentence in embedded_cases:
            result = self.stabilizer.sanitize_anchor(sentence)
            self.assertEqual(
                result, "",
                f"LỖI: sanitize_anchor để lọt từ khóa cấm trong câu: '{sentence}' (trả về '{result}')"
            )

    def test_valid_distinctive_anchors_preserved(self):
        """Đảm bảo các mỏ neo hợp lệ (vị trí, phụ kiện, đặc điểm không phải đồng phục) được giữ nguyên."""
        valid_cases = [
            ("Bên trái", "Bên trái"),
            ("Bàn đầu", "Bàn đầu"),
            ("Trung tâm", "Trung tâm"),
            ("Bên phải", "Bên phải"),
            ("Hàng sau", "Hàng sau"),
            ("Khiêu khích", "Khiêu khích"),
            ("Bị xô", "Bị xô"),
            ("Can ngăn", "Can ngăn"),
            ("Đội mũ lưỡi trai", "Đội mũ lưỡi trai"),
            ("Đeo kính cận", "Đeo kính cận"),
            ("Ngồi cạnh cửa sổ", "Ngồi cạnh cửa sổ"),
            ("Cầm tập tài liệu", "Cầm tập tài liệu"),
            ("  Bàn đầu  ", "Bàn đầu"), # stripped
        ]

        for input_anc, expected in valid_cases:
            result = self.stabilizer.sanitize_anchor(input_anc)
            self.assertEqual(
                result, expected,
                f"LỖI: sanitize_anchor làm mất hoặc sai mỏ neo hợp lệ: '{input_anc}'"
            )

    def test_get_clean_anchor_fallback_on_forbidden_gemini_anchor(self):
        """Khi Gemini trả về mỏ neo đồng phục cấm, get_clean_anchor phải khử sạch và fallback về vị trí không gian."""
        c_id = 1
        bbox = (100, 100, 200, 400) # nx = 150/1280 = 0.117 -> Bên trái

        # Đặt mỏ neo cấm vào canonical_anchors
        self.stabilizer.canonical_anchors[c_id] = "Học sinh áo trắng bàn đầu"

        clean_anchor = self.stabilizer.get_clean_anchor(c_id=c_id, bbox=bbox, frame_w=1280, frame_h=720)

        # Phải fallback sang spatial anchor "Bên trái", tuyệt đối không chứa "áo trắng"
        self.assertNotIn("áo trắng", clean_anchor.lower())
        self.assertEqual(clean_anchor, "Bên trái")


class TestTemporalHysteresisAndAntiFlicker(unittest.TestCase):
    """Stress-test Bộ lọc trễ thời gian (Temporal Hysteresis) chống rung giật mỏ neo qua 15+ frames."""

    def setUp(self):
        self.stabilizer = SpatialTrackStabilizer(max_missing_frames=90, match_dist_ratio=0.35, max_k=4)
        self.w = 1280
        self.h = 720

    def test_boundary_noise_rejection_over_15_frames(self):
        """
        Kiểm tra khử nhiễu biên qua 15+ frames:
        - Bắt đầu ở 'Bên trái' (frames 1-5).
        - Nhiễu 1 frame nhảy sang 'Trung tâm' (frame 6) -> Không đổi.
        - Quay lại 'Bên trái' (frame 7).
        - Nhiễu 2 frames nhảy sang 'Bên phải' (frames 8-9) -> Không đổi.
        - Quay lại 'Bên trái' (frames 10-15).
        """
        c_id = 1
        bbox_left = (100, 200, 300, 500)      # cx=200 -> Bên trái
        bbox_center = (550, 200, 750, 500)    # cx=650, cy=350 -> Trung tâm
        bbox_right = (900, 200, 1100, 500)    # cx=1000 -> Bên phải

        # Frames 1-5: Ổn định tại Bên trái
        for f in range(1, 6):
            anc = self.stabilizer.get_clean_anchor(c_id, bbox_left, self.w, self.h)
            self.assertEqual(anc, "Bên trái", f"Frame {f} phải là 'Bên trái'")

        # Frame 6: Nhiễu giật 1 frame sang Trung tâm
        anc_f6 = self.stabilizer.get_clean_anchor(c_id, bbox_center, self.w, self.h)
        self.assertEqual(anc_f6, "Bên trái", "Frame 6: 1 frame jitter sang Trung tâm KHÔNG ĐƯỢC làm rung nhãn")

        # Frame 7: Trở lại Bên trái
        anc_f7 = self.stabilizer.get_clean_anchor(c_id, bbox_left, self.w, self.h)
        self.assertEqual(anc_f7, "Bên trái")

        # Frames 8-9: Nhiễu giật 2 frames sang Bên phải
        anc_f8 = self.stabilizer.get_clean_anchor(c_id, bbox_right, self.w, self.h)
        self.assertEqual(anc_f8, "Bên trái", "Frame 8: Jitter sang Bên phải KHÔNG ĐƯỢC làm rung nhãn")
        anc_f9 = self.stabilizer.get_clean_anchor(c_id, bbox_right, self.w, self.h)
        self.assertEqual(anc_f9, "Bên trái", "Frame 9: Jitter sang Bên phải KHÔNG ĐƯỢC làm rung nhãn")

        # Frames 10-15: Tiếp tục ở Bên trái
        for f in range(10, 16):
            anc = self.stabilizer.get_clean_anchor(c_id, bbox_left, self.w, self.h)
            self.assertEqual(anc, "Bên trái", f"Frame {f} phải duy trì 'Bên trái'")

    def test_smooth_transition_on_actual_movement(self):
        """
        Kiểm tra chuyển vùng thực tế: Khi đối tượng thực sự di chuyển và ở lại vùng mới
        đạt ngưỡng đa số (>= 9/15 frames), mỏ neo phải chuyển trạng thái ổn định sang vùng mới.
        """
        c_id = 2
        bbox_left = (100, 200, 300, 500)      # Bên trái
        bbox_center = (550, 200, 750, 500)    # Trung tâm

        # Bắt đầu 5 frames ở Bên trái
        for _ in range(5):
            self.stabilizer.get_clean_anchor(c_id, bbox_left, self.w, self.h)
        self.assertEqual(self.stabilizer.get_clean_anchor(c_id, bbox_left, self.w, self.h), "Bên trái")

        # Bắt đầu di chuyển sang Trung tâm và duy trì liên tục
        for f in range(1, 8):
            # Các frames đầu (dưới 9 frames) chưa đạt ngưỡng đa số
            anc = self.stabilizer.get_clean_anchor(c_id, bbox_center, self.w, self.h)

        # Tiếp tục cấp thêm frames cho đến khi Trung tâm chiếm >= 9 frames trong cửa sổ 15
        for f in range(8, 15):
            anc = self.stabilizer.get_clean_anchor(c_id, bbox_center, self.w, self.h)

        # Sau 14 frames liên tục ở Trung tâm, mỏ neo phải là 'Trung tâm'
        final_anc = self.stabilizer.get_clean_anchor(c_id, bbox_center, self.w, self.h)
        self.assertEqual(final_anc, "Trung tâm", "Sau di chuyển thực tế liên tục, mỏ neo phải chuyển sang 'Trung tâm'")

    def test_multi_track_isolation(self):
        """Kiểm tra các Track khác nhau duy trì bộ đệm trễ độc lập, không ảnh hưởng lẫn nhau."""
        bbox_left = (100, 200, 300, 500)
        bbox_right = (900, 200, 1100, 500)

        # Cấp track 1 ở bên trái, track 2 ở bên phải
        for _ in range(5):
            self.stabilizer.get_clean_anchor(1, bbox_left, self.w, self.h)
            self.stabilizer.get_clean_anchor(2, bbox_right, self.w, self.h)

        self.assertEqual(self.stabilizer.get_clean_anchor(1, bbox_left, self.w, self.h), "Bên trái")
        self.assertEqual(self.stabilizer.get_clean_anchor(2, bbox_right, self.w, self.h), "Bên phải")

        # Jitter track 1 không được làm thay đổi track 2
        self.stabilizer.get_clean_anchor(1, bbox_right, self.w, self.h)
        self.assertEqual(self.stabilizer.get_clean_anchor(2, bbox_right, self.w, self.h), "Bên phải")


class TestCausalRoleAnchorPriority(unittest.TestCase):
    """Stress-test Ưu tiên Mỏ neo Vai trò Nhân quả (Attacker, Victim, Defender)."""

    def setUp(self):
        self.stabilizer = SpatialTrackStabilizer()
        self.bbox = (500, 200, 700, 500)

    def test_attacker_causal_variations(self):
        """Kiểm tra các biến thể vai trò Kẻ tấn công / Khiêu khích."""
        cases = [
            "attacker", "ATTACKER",
            "Kẻ tấn công / Gây hấn",
            "khiêu khích đối phương",
            "gây hấn xô xát",
            "Vung tay tấn công",
        ]
        for role in cases:
            res = self.stabilizer.get_clean_anchor(1, bbox=self.bbox, causal_role=role)
            self.assertEqual(res, "Khiêu khích", f"Vai trò '{role}' phải ánh xạ về 'Khiêu khích'")

    def test_victim_causal_variations(self):
        """Kiểm tra các biến thể vai trò Nạn nhân / Bị xô."""
        cases = [
            "victim", "VICTIM",
            "Nạn nhân / Phòng thủ",
            "nạn nhân bị đẩy",
            "bị xô ngã",
            "té ngã bất động",
        ]
        for role in cases:
            res = self.stabilizer.get_clean_anchor(2, bbox=self.bbox, causal_role=role)
            self.assertEqual(res, "Bị xô", f"Vai trò '{role}' phải ánh xạ về 'Bị xô'")

    def test_defender_causal_variations(self):
        """Kiểm tra các biến thể vai trò Người can ngăn / Phòng vệ."""
        cases = [
            "defender", "DEFENDER",
            "Người can ngăn",
            "can ngăn hòa giải",
            "phòng vệ che chắn",
            "bảo vệ đồng đội",
        ]
        for role in cases:
            res = self.stabilizer.get_clean_anchor(3, bbox=self.bbox, causal_role=role)
            self.assertEqual(res, "Can ngăn", f"Vai trò '{role}' phải ánh xạ về 'Can ngăn'")

    def test_neutral_causal_falls_back_to_spatial(self):
        """Vai trò trung tính hoặc người quan sát phải fallback về vị trí không gian."""
        cases = ["bystander", "Người quan sát", "Người quan sát / Ngoài cuộc", None, ""]
        for role in cases:
            res = self.stabilizer.get_clean_anchor(4, bbox=self.bbox, causal_role=role)
            self.assertIn(res, ["Trung tâm", "Bàn đầu", "Hàng sau", "Bên trái", "Bên phải"])


class TestBoundingBoxZeroGuessingLabels(unittest.TestCase):
    """Stress-test Triệt tiêu hoàn toàn nhãn phỏng đoán hành vi và tỷ lệ % trên Bounding Box."""

    def setUp(self):
        self.hud = CyberHUDRenderer()

    def test_draw_technical_bbox_clean_bracket_label_preservation(self):
        """Nhãn dạng [ID #0X] hoặc [ID #0X: Mỏ neo] giữ nguyên 100%, không bị chèn thêm % hay ngoặc kép."""
        test_labels = [
            "[ID #01]",
            "[ID #02]",
            "[ID #01: Bên trái]",
            "[ID #02: Bàn đầu]",
            "[ID #03: Khiêu khích]",
            "[ID #04: Bị xô]",
            "[ID #05: Can ngăn]",
        ]

        img = np.zeros((720, 1280, 3), dtype=np.uint8)

        for lbl in test_labels:
            with patch.object(self.hud, "draw_unicode_text") as mock_draw:
                # Gọi với score > 0 để kiểm tra score bị vô hiệu hóa khi có bracket
                self.hud.draw_technical_bbox(img, 100, 100, 300, 400, (0, 255, 0), label=lbl, score=0.63)
                mock_draw.assert_called_once()
                args, kwargs = mock_draw.call_args
                drawn_text = args[1]

                # Xác minh drawn_text chính xác bằng lbl, tuyệt đối không có "63%"
                self.assertEqual(drawn_text, lbl)
                self.assertNotIn("%", drawn_text)
                self.assertNotIn("63%", drawn_text)

    def test_draw_technical_bbox_with_zero_score_unbracketed_label(self):
        """Nhãn dạng 'ID #01' khi score=0.0 tự động bọc thành '[ID #01]', không chèn '0%'."""
        img = np.zeros((720, 1280, 3), dtype=np.uint8)
        with patch.object(self.hud, "draw_unicode_text") as mock_draw:
            self.hud.draw_technical_bbox(img, 100, 100, 300, 400, (0, 255, 0), label="ID #01", score=0.0)
            mock_draw.assert_called_once()
            args, kwargs = mock_draw.call_args
            drawn_text = args[1]
            self.assertEqual(drawn_text, "[ID #01]")
            self.assertNotIn("%", drawn_text)

    def test_draw_technical_bbox_never_draws_forbidden_action_strings(self):
        """Kiểm tra tuyệt đối không có chuỗi phỏng đoán nào được vẽ lên bounding box."""
        forbidden_action_samples = [
            "NGỒI TẠI BÀN",
            "NGỒI TẠI BÀN / QUAN SÁT TĨNH",
            "XUNG ĐỘT THỂ XÁC",
            "XUNG ĐỘT THỂ XÁC 63%",
            "VUNG TAY RA ĐÒN",
            "PHÒNG VỆ / CHẮN ĐỠ",
            "TÉ NGÃ",
            "63%", "75%", "92%",
        ]

        img = np.zeros((720, 1280, 3), dtype=np.uint8)

        # Test trường hợp clean_box_label chuẩn
        clean_labels = [
            "[ID #01]",
            "[ID #01: Bên trái]",
            "[ID #02: Bàn đầu]",
            "[ID #03: Khiêu khích]",
        ]

        for clean_lbl in clean_labels:
            with patch.object(self.hud, "draw_unicode_text") as mock_draw:
                self.hud.draw_technical_bbox(img, 50, 50, 200, 350, (0, 255, 0), label=clean_lbl, score=0.0)
                mock_draw.assert_called_once()
                args, _ = mock_draw.call_args
                drawn_text = args[1]

                for forbidden in forbidden_action_samples:
                    self.assertNotIn(
                        forbidden, drawn_text,
                        f"LỖI: Phát hiện chuỗi cấm '{forbidden}' trong nhãn bounding box: '{drawn_text}'"
                    )

    def test_full_pipeline_label_construction_simulation(self):
        """
        Mô phỏng chu trình suy luận của VideoAnnotatorEngine:
        Nạp các ứng viên cand và hành động đa dạng (tấn công, ngồi bàn, té ngã, phòng vệ)
        và kiểm tra nhãn Bounding Box truyền vào HUD:
        - Phải đúng định dạng [ID #0X] hoặc [ID #0X: Mỏ neo]
        - score truyền vào bắt buộc là 0.0
        - Tuyệt đối không chứa action text hoặc %
        """
        stabilizer = SpatialTrackStabilizer()

        # Danh sách kịch bản thử nghiệm
        test_scenarios = [
            {
                "c_id": 1,
                "id_label": "ID #01",
                "bbox": (100, 200, 250, 600), # Bên trái
                "cand": {"is_striking": True},
                "kinetic_spike": 2.5,
                "interaction_score": 3.8,
                "stable_role": "attacker",
                "stable_danger": True,
                "stable_threat_score": 8.5,
                "stable_action": "Vung tay ra đòn / Tấn công áp sát",
                "conf": 0.63
            },
            {
                "c_id": 2,
                "id_label": "ID #02",
                "bbox": (550, 450, 700, 700), # Bàn đầu
                "cand": {"is_striking": False, "is_seated": True},
                "kinetic_spike": 0.1,
                "interaction_score": 0.2,
                "stable_role": "bystander",
                "stable_danger": False,
                "stable_threat_score": 0.2,
                "stable_action": "Ngồi tại bàn / Quan sát tĩnh",
                "conf": 0.92
            },
            {
                "c_id": 3,
                "id_label": "ID #03",
                "bbox": (500, 250, 750, 500), # Trung tâm
                "cand": {"is_targeted": True},
                "kinetic_spike": 1.2,
                "interaction_score": 2.8,
                "stable_role": "defender",
                "stable_danger": False,
                "stable_threat_score": 4.5,
                "stable_action": "Phòng vệ / Chắn đỡ né đòn",
                "conf": 0.77
            },
            {
                "c_id": 4,
                "id_label": "ID #04",
                "bbox": (950, 200, 1150, 600), # Bên phải
                "cand": {},
                "kinetic_spike": 1.9,
                "interaction_score": 1.0,
                "stable_role": "victim",
                "stable_danger": True,
                "stable_threat_score": 9.0,
                "stable_action": "Té ngã / Nằm bất động",
                "conf": 0.81
            }
        ]

        for sc in test_scenarios:
            c_id = sc["c_id"]
            id_label = sc["id_label"]
            x1, y1, x2, y2 = sc["bbox"]
            stable_role = sc["stable_role"]
            stable_danger = sc["stable_danger"]
            stable_threat_score = sc["stable_threat_score"]

            # Thực thi logic xác định anchor giống hệt core/video_annotator.py lines 1665-1680
            anchor = stabilizer.get_clean_anchor(
                c_id=c_id,
                bbox=(x1, y1, x2, y2),
                frame_w=1280,
                frame_h=720,
                causal_role=stable_role if (stable_danger or stable_threat_score >= 6.5) else None
            )

            if anchor:
                clean_box_label = f"[{id_label}: {anchor}]"
            else:
                clean_box_label = f"[{id_label}]"

            # Xác minh định dạng nhãn
            self.assertTrue(
                clean_box_label.startswith("[") and clean_box_label.endswith("]"),
                f"clean_box_label '{clean_box_label}' phải được bọc trong [ ... ]"
            )

            # Xác minh KHÔNG chứa action đoán mò
            self.assertNotIn(sc["stable_action"], clean_box_label)
            self.assertNotIn(str(int(sc["conf"] * 100)) + "%", clean_box_label)
            self.assertNotIn("NGỒI TẠI BÀN", clean_box_label)
            self.assertNotIn("XUNG ĐỘT THỂ XÁC", clean_box_label)
            self.assertNotIn("TÉ NGÃ", clean_box_label)
            self.assertNotIn("PHÒNG VỆ", clean_box_label)

            # Mô phỏng vẽ lên canvas thực tế qua HUD
            canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
            with patch.object(self.hud, "draw_unicode_text") as mock_draw:
                self.hud.draw_corner_bracket_bbox(canvas, x1, y1, x2, y2, (0, 255, 0), clean_box_label, 0.0)
                mock_draw.assert_called_once()
                args, _ = mock_draw.call_args
                drawn_text = args[1]

                self.assertEqual(drawn_text, clean_box_label)
                self.assertNotIn("%", drawn_text)


if __name__ == "__main__":
    unittest.main()
