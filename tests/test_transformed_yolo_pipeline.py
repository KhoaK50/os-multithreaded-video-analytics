"""
Unit tests for the Transformed YOLO Pipeline:
1. AutoLowLightEnhancer (Zero-DCE/CLAHE pre-enhancement for dark/night frames)
2. SpatioTemporalSkeletonFilter (ST-GCN temporal smoothing & occlusion-aware biomechanics)
3. Clean Frame Annotation (No dark header bar, clean [ID #0X] labels)
"""

import math
import numpy as np
import pytest
from core.enhancer import AutoLowLightEnhancer
from core.video_annotator import SpatioTemporalSkeletonFilter


class TestAutoLowLightEnhancer:
    """Kiểm tra Bộ Tăng Cường Ánh Sáng Thích Ứng (Auto Low-Light Pre-Enhancer)."""

    def test_bright_frame_untouched(self):
        """Khung hình đủ sáng (L >= 65.0) không bị can thiệp làm biến dạng màu."""
        enhancer = AutoLowLightEnhancer(low_light_thresh=65.0)
        bright_frame = np.full((100, 100, 3), 150, dtype=np.uint8)

        mean_lum, is_low = enhancer.analyze_frame_luminance(bright_frame)
        assert mean_lum >= 65.0
        assert not is_low

        enhanced, was_enhanced = enhancer.enhance_if_needed(bright_frame)
        assert not was_enhanced
        assert np.array_equal(bright_frame, enhanced)

    def test_dark_frame_enhanced(self):
        """Khung hình tối mờ (L < 65.0) tự động được kích hoạt tăng cường dải sáng."""
        enhancer = AutoLowLightEnhancer(low_light_thresh=65.0)
        dark_frame = np.full((100, 100, 3), 30, dtype=np.uint8)

        mean_lum, is_low = enhancer.analyze_frame_luminance(dark_frame)
        assert is_low
        assert mean_lum < 65.0

        enhanced, was_enhanced = enhancer.enhance_if_needed(dark_frame)
        assert was_enhanced
        assert enhanced.shape == dark_frame.shape

        # Độ sáng trung bình sau khi tăng cường phải cao hơn ảnh gốc
        enhanced_lum, _ = enhancer.analyze_frame_luminance(enhanced)
        assert enhanced_lum > mean_lum

    def test_grayscale_frame_support(self):
        """Hỗ trợ ảnh đơn kênh (grayscale) an toàn không gây crash."""
        enhancer = AutoLowLightEnhancer(low_light_thresh=65.0)
        gray_dark = np.full((80, 80), 25, dtype=np.uint8)

        enhanced, was_enhanced = enhancer.enhance_if_needed(gray_dark)
        assert was_enhanced
        assert enhanced.ndim == 2
        assert float(np.mean(enhanced)) > float(np.mean(gray_dark))

    def test_empty_frame_handling(self):
        """Khung hình rỗng hoặc None không bị Exception."""
        enhancer = AutoLowLightEnhancer()
        res, was = enhancer.enhance_if_needed(None)
        assert res is None
        assert not was


class TestSpatioTemporalSkeletonFilter:
    """Kiểm tra Bộ Lọc Quỹ Đạo Khung Xương Không - Thời Gian (ST-GCN Trajectory Filter)."""

    def _generate_synthetic_skeleton(self, base_y=200, jitter=0.0, lower_conf=0.85):
        """Tạo bộ khung xương giả định 17 điểm với độ lệch jitter tùy chỉnh."""
        # COCO 17 keypoints:
        # 0: nose, 1-2: eyes, 3-4: ears, 5-6: shoulders, 7-8: elbows, 9-10: wrists
        # 11-12: hips, 13-14: knees, 15-16: ankles
        kpts = []
        for i in range(17):
            conf = lower_conf if i in [13, 14, 15, 16] else 0.85
            # Vị trí mẫu chuẩn
            if i == 0:
                kpts.append([320.0 + jitter, base_y - 80.0 + jitter, 0.90])
            elif i in [5, 6]:
                offset = -30.0 if i == 5 else 30.0
                kpts.append([320.0 + offset + jitter, base_y - 40.0 + jitter, 0.85])
            elif i in [11, 12]:
                offset = -25.0 if i == 11 else 25.0
                kpts.append([320.0 + offset + jitter, base_y + 40.0 + jitter, 0.80])
            elif i in [13, 14]:
                offset = -20.0 if i == 13 else 20.0
                kpts.append([320.0 + offset + jitter, base_y + 120.0 + jitter, conf])
            elif i in [15, 16]:
                offset = -20.0 if i == 15 else 20.0
                kpts.append([320.0 + offset + jitter, base_y + 200.0 + jitter, conf])
            else:
                kpts.append([320.0 + jitter, base_y + jitter, conf])
        return np.array(kpts, dtype=np.float32)

    def test_ema_smoothing_reduces_jitter(self):
        """EMA làm giảm độ lệch giật khung xương qua các chuỗi frame liên tiếp."""
        st_filter = SpatioTemporalSkeletonFilter(window_size=10, ema_alpha=0.60)
        c_id = 1

        # Frame 1: vị trí gốc
        f1 = self._generate_synthetic_skeleton(base_y=200, jitter=0.0)
        s1 = st_filter.update_skeleton(c_id, f1)

        # Frame 2: bị rung đột ngột +20px do motion blur / camera rung
        f2 = self._generate_synthetic_skeleton(base_y=200, jitter=20.0)
        s2 = st_filter.update_skeleton(c_id, f2)

        # Tọa độ mũi (kpt 0) sau khi làm mượt phải ở giữa 0 và 20 (cụ thể: 0.6*20 = 12.0)
        assert abs(s2[0][0] - (320.0 + 20.0)) < 20.0
        assert s2[0][0] < (320.0 + 20.0)  # EMA kiềm chế bước nhảy

    def test_occlusion_memory_preservation(self):
        """Khi khớp bị mất điểm / che khuất tạm thời (conf thấp), giữ lại vị trí trước đó."""
        st_filter = SpatioTemporalSkeletonFilter(window_size=10, ema_alpha=0.70)
        c_id = 2

        f1 = self._generate_synthetic_skeleton(base_y=200, jitter=0.0)
        s1 = st_filter.update_skeleton(c_id, f1)
        prev_wrist_x = s1[9][0]

        # Frame 2: Cổ tay bị mất hoàn toàn (conf = 0.05, x=0, y=0)
        f2 = f1.copy()
        f2[9] = [0.0, 0.0, 0.05]
        s2 = st_filter.update_skeleton(c_id, f2)

        # Cổ tay sau khi lọc phải được giữ lại vị trí trước đó thay vì nhảy về (0,0)
        assert abs(s2[9][0] - prev_wrist_x) < 5.0
        assert s2[9][2] > 0.30  # Giữ confidence khả dụng

    def test_lower_body_occlusion_detection(self):
        """Phát hiện chính xác che khuất nửa thân dưới (do bàn học, quầy thu ngân)."""
        st_filter = SpatioTemporalSkeletonFilter(window_size=10)
        c_id = 3

        # Tạo khung xương có chân bị che mờ (lower_conf < 0.28)
        kpts_occluded = self._generate_synthetic_skeleton(base_y=200, lower_conf=0.15)
        bbox = (250, 100, 390, 350)
        frame_h = 720

        state = st_filter.extract_biomechanical_state(c_id, kpts_occluded, bbox, frame_h)
        assert state["is_lower_occluded"] is True
        assert state["is_free_fall"] is False
        assert state["is_controlled_motion"] is True

    def test_free_fall_versus_controlled_motion(self):
        """Phân biệt chính xác rơi tự do (Free Fall) và cúi người / ngồi làm việc."""
        st_filter = SpatioTemporalSkeletonFilter(window_size=10)
        c_id = 4
        frame_h = 720
        bbox = (200, 450, 440, 680)

        # Mô phỏng tư thế ngã nằm sát sàn: đầu sát đất, trục thân bẹp (< 28 độ)
        fall_kpts = []
        for i in range(17):
            if i == 0:  # nose
                fall_kpts.append([210.0, 620.0, 0.85])
            elif i in [5, 6]:  # shoulders
                fall_kpts.append([260.0, 610.0, 0.80])
            elif i in [11, 12]:  # hips
                fall_kpts.append([400.0, 615.0, 0.80])
            elif i in [13, 14]:  # knees
                fall_kpts.append([450.0, 618.0, 0.75])
            elif i in [15, 16]:  # ankles
                fall_kpts.append([500.0, 620.0, 0.70])
            else:
                fall_kpts.append([300.0, 615.0, 0.75])
        fall_kpts = np.array(fall_kpts, dtype=np.float32)

        # Nạp chuỗi chuyển động rơi nhanh (từ đứng 90 độ rơi xuống 10 độ trong 4 frames)
        for ang in [85.0, 60.0, 30.0, 10.0]:
            st_filter.track_windows.setdefault(c_id, {"angles": []})["angles"].append(ang)

        state = st_filter.extract_biomechanical_state(c_id, fall_kpts, bbox, frame_h)
        assert state["torso_angle"] < 28.0
        assert state["angular_velocity"] >= 4.0
        assert state["is_free_fall"] is True

    def test_z_axis_looming_expansion(self):
        """Kiểm tra phản hồi với chuyển động lao thẳng theo trục Z (Looming Bounding Box Expansion)."""
        from core.video_annotator import KinematicAnomalyRanker
        ranker = KinematicAnomalyRanker(top_k=4)

        kpts = self._generate_synthetic_skeleton(base_y=200)

        # Frame 1: Đối tượng ở xa (bbox 100x200)
        det_f1 = [{
            "raw_id": 10,
            "bbox": (100, 100, 200, 300),
            "kpts": kpts,
            "torso_angle": 90.0,
            "threat_score": 0.0,
            "person_danger": False
        }]
        res_f1 = ranker.update_frame(det_f1, frame_w=1280, frame_h=720)
        assert res_f1[0]["kinetic_spike"] == 0.0

        # Frame 2: Lao thẳng vào camera (bbox phình to thành 140x280, tăng diện tích gần gấp đôi)
        det_f2 = [{
            "raw_id": 10,
            "bbox": (80, 60, 220, 340),  # w=140, h=280
            "kpts": kpts,
            "torso_angle": 90.0,
            "threat_score": 0.0,
            "person_danger": False
        }]
        res_f2 = ranker.update_frame(det_f2, frame_w=1280, frame_h=720)
        # kinetic_spike phải ghi nhận xung lực giãn nở diện tích trục Z
        assert res_f2[0]["kinetic_spike"] > 0.0
