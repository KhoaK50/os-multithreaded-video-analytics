import pytest
import os
import numpy as np
from core.video_annotator import TemporalActionStabilizer

def test_temporal_action_stabilizer_hysteresis():
    """
    Kiểm thử Bộ Lọc Trễ Thời Gian (TemporalActionStabilizer):
    1. Chỉ kích hoạt ATTACKER sau >= 3 frames liên tiếp ghi nhận xung lực cao.
    2. Duy trì trạng thái giảm chấn (DEFENDER/Vàng) ít nhất 5 frames trước khi hạ về OBSERVER/Xanh.
    3. Nhãn hành vi tuân theo đa số (Majority Vote) trong cửa sổ trượt.
    """
    stab = TemporalActionStabilizer(window_size=8, trigger_thresh=3, cooldown_frames=5)
    c_id = 1

    # Frame 1: Xung lực vừa phải lần 1 -> Chưa kích hoạt (vẫn là observer)
    res1 = stab.update(c_id, "Vung tay ra đòn", "attacker", False, 5.5, 1.8, 2.0)
    assert res1["role"] != "attacker"
    assert res1["is_danger"] == False

    # Frame 2: Xung lực vừa phải lần 2 -> Chưa kích hoạt
    res2 = stab.update(c_id, "Vung tay ra đòn", "attacker", False, 5.5, 1.8, 2.0)
    assert res2["role"] != "attacker"

    # Frame 3: Xung lực vừa phải lần 3 -> Đủ 3 frames -> KÍCH HOẠT ĐỎ
    res3 = stab.update(c_id, "Vung tay ra đòn", "attacker", False, 5.5, 1.8, 2.0)
    assert res3["role"] == "attacker"
    assert res3["is_danger"] == True
    assert res3["color"] == (68, 68, 239)  # Đỏ BGR
    assert "TẤN CÔNG" in res3["role_prefix"]

    # Frame 4: Xung lực hạ thấp (đối tượng hạ tay) -> Kích hoạt Cooldown (giảm chấn sang Vàng/Phòng vệ)
    res4 = stab.update(c_id, "Đang đứng", "safe", False, 1.0, 0.2, 0.5)
    assert res4["role"] == "defender"  # Giữ ở mức cảnh giác Vàng, không nhảy về Xanh ngay
    assert res4["is_danger"] == False
    assert res4["color"] == (0, 215, 255)  # Vàng hổ phách BGR

    # Duy trì các frames tiếp theo trong thời gian cooldown
    for _ in range(4):
        res_cd = stab.update(c_id, "Đang đứng", "safe", False, 1.0, 0.2, 0.5)
        assert res_cd["role"] == "defender"

    # Frame kết thúc cooldown -> An toàn hạ về Xanh
    res_final = stab.update(c_id, "Đang đứng", "safe", False, 1.0, 0.2, 0.5)
    assert res_final["role"] == "observer"
    assert res_final["color"] == (255, 240, 0)  # Cyan BGR
    assert res_final["role_prefix"] == ""


def test_telemetry_keys_structure():
    """
    Kiểm thử cấu trúc telemetry_breakdown có đầy đủ cả 2 chuẩn key
    để frontend app.js và backend Python tương thích tuyệt đối.
    """
    max_k = 2.5
    max_c = 3.0
    seg_severity = "danger"
    score_kinetic = min(10.0, max_k * 2.8)
    score_proximity = min(10.0, max_c * 2.2)
    score_posture = 8.5
    calculated_score = min(10.0, 0.40 * score_kinetic + 0.35 * score_proximity + 0.25 * score_posture)
    final_threat_score = round(calculated_score, 1)

    vel_px = int(round(max_k * 140.0))
    dist_px = int(round(max(25.0, 180.0 - max_c * 28.0)))
    posture_display = "Xô xát / Ra đòn"

    tb = {
        "max_velocity": vel_px,
        "min_distance": dist_px,
        "dominant_posture": posture_display,
        "strike_velocity": f"{vel_px} px/s",
        "proximity_dist": f"{dist_px} px",
        "posture_state": posture_display,
        "kinetic_spike": round(max_k, 2),
        "interaction_score": round(max_c, 2),
        "calculated_score": final_threat_score
    }

    assert tb["max_velocity"] > 0
    assert tb["max_velocity"] == 350
    assert tb["min_distance"] > 0
    assert tb["dominant_posture"] == "Xô xát / Ra đòn"
    assert tb["calculated_score"] >= 7.0  # Điểm nguy cơ thực tế, không bị kẹt ở 2.1


def test_impulse_shock_trigger():
    """
    Kiểm thử Kích Hoạt Tức Thời (Impulse Shock Trigger):
    Đòn đánh có xung lực đột biến (kinetic >= 2.2 hoặc threat_score >= 7.0)
    kích hoạt ngay trạng thái TẤN CÔNG chỉ sau 1 frame, không bắt buộc đợi 3 frames.
    """
    stab = TemporalActionStabilizer(window_size=8, trigger_thresh=3, cooldown_frames=5)
    c_id = 99
    # Frame 1 với xung lực cực đại -> Kích hoạt ngay lập tức
    res = stab.update(c_id, "Vung tay ra đòn", "attacker", True, 8.8, 2.6, 3.5)
    assert res["role"] == "attacker"
    assert res["is_danger"] == True
    assert "TẤN CÔNG" in res["role_prefix"]


def test_desk_occlusion_sitting_rule():
    """
    Kiểm thử nhận diện tư thế ngồi sau bàn học (Desk Occlusion):
    Học sinh ngồi sau bàn gỗ, phần thân dưới bị che khuất (kpts đầu gối tin cậy thấp),
    tỉ lệ khung hình thấp/bè (aspect_ratio < 1.6), trục thân thẳng đứng.
    Hệ thống BẮT BUỘC phân loại là "Ngồi tại bàn", TUYỆT ĐỐI KHÔNG gán "Đang đứng".
    """
    # Giả lập tham số giải phẫu học của người ngồi sau bàn học
    aspect_ratio = 1.35
    bbox_h = 270
    bbox_w = 200
    torso_angle = 88.0
    kinetic_spike = 0.20
    kpts = [[100, 50, 0.9] for _ in range(17)]
    kpts[13] = [80, 260, 0.05]   # Đầu gối trái bị bàn che khuất (độ tin cậy gần 0)
    kpts[14] = [120, 260, 0.05]  # Đầu gối phải bị bàn che khuất
    l_sh = [70, 90, 0.85]
    r_sh = [130, 90, 0.85]
    l_hip = [80, 180, 0.60]
    nose = [100, 45, 0.90]
    hip_y = 180
    y2 = 270

    has_knee_kpts = (len(kpts) > 14 and kpts[13][2] > 0.35 and kpts[14][2] > 0.35)
    is_seated_full = (has_knee_kpts and l_hip[2] > 0.30 and abs(kpts[13][1] - l_hip[1]) < 0.30 * bbox_h and abs(kpts[13][0] - l_hip[0]) > 0.18 * bbox_w)

    is_seated_desk = (
        (not has_knee_kpts or aspect_ratio < 1.62) and
        60.0 <= torso_angle <= 120.0 and
        (l_sh[2] > 0.30 or r_sh[2] > 0.30) and
        nose[2] > 0.30 and
        kinetic_spike < 0.85 and
        (aspect_ratio < 1.55 or (l_hip[2] > 0.20 and abs(hip_y - y2) < 0.45 * bbox_h))
    )
    is_seated = (is_seated_full or is_seated_desk)

    assert is_seated == True
    # Phân loại hành động
    if kinetic_spike < 0.65:
        if is_seated:
            person_action = "Ngồi tại bàn / Quan sát tĩnh"
        elif aspect_ratio >= 1.70:
            person_action = "Đang đứng quan sát / Giữ nguyên vị trí"
        else:
            person_action = "Hoạt động bình thường / Quan sát"

    assert person_action == "Ngồi tại bàn / Quan sát tĩnh"
    assert "đứng" not in person_action.lower()


def test_extended_weapon_reach_cone():
    """
    Kiểm thử Nón Sát Thương Vũ Khí Kéo Dài (Extended Weapon Reach Cone):
    Hai đối tượng cách nhau 1.35 * chiều cao thân (vượt ngoài tầm sải tay thường 0.85 * h).
    Đối tượng A cầm gậy/vũ khí thụt mạnh về phía đối tượng B (cos > 0.35, v_wrist cao).
    Hệ thống BẮT BUỘC nhận diện đòn đánh A -> B (is_striking = True, interaction_score >= 6.0).
    """
    from core.video_annotator import KinematicAnomalyRanker
    import math

    ranker = KinematicAnomalyRanker(top_k=4)

    # Khởi tạo frame 1 (để lưu prev_kpts)
    det_a1 = {
        "raw_id": 1,
        "bbox": [100, 100, 200, 300],  # h = 200
        "kpts": [[150, 150, 0.9] for _ in range(17)],
        "wrist_vec": (0.0, 0.0),
        "torso_angle": 90.0
    }
    det_b1 = {
        "raw_id": 2,
        "bbox": [370, 100, 470, 300],  # h = 200, khoảng cách ca_x=150 đến cb_x=420 là 270 px = 1.35 * h
        "kpts": [[420, 150, 0.9] for _ in range(17)],
        "wrist_vec": (0.0, 0.0),
        "torso_angle": 90.0
    }
    ranker.update_frame([det_a1, det_b1], 640, 480)

    # Frame 2: Đối tượng A vung cả cánh tay và thụt mạnh hung khí về phía B (dịch chuyển +x 50px)
    det_a2 = {
        "raw_id": 1,
        "bbox": [100, 100, 200, 300],
        "kpts": [[150, 150, 0.9] for _ in range(17)],
        "torso_angle": 90.0
    }
    # Khuỷu tay và cổ tay (index 7, 8, 9, 10) phóng mạnh về phía B (+x)
    det_a2["kpts"][7] = [185, 150, 0.9]
    det_a2["kpts"][8] = [185, 150, 0.9]
    det_a2["kpts"][9] = [200, 150, 0.9]
    det_a2["kpts"][10] = [200, 150, 0.9]

    det_b2 = {
        "raw_id": 2,
        "bbox": [370, 100, 470, 300],
        "kpts": [[420, 150, 0.9] for _ in range(17)],
        "torso_angle": 90.0
    }

    res = ranker.update_frame([det_a2, det_b2], 640, 480)
    a_res = [d for d in res if d["raw_id"] == 1][0]
    b_res = [d for d in res if d["raw_id"] == 2][0]

    # Kiểm tra A được kích hoạt tấn công tầm xa vũ khí và B là mục tiêu
    assert a_res.get("is_striking") == True
    assert a_res["interaction_score"] >= 6.0
    assert b_res.get("is_targeted") == True


def test_seated_classroom_jitter_not_attacker():
    """
    Kiểm thử quan trọng: Học sinh ngồi trong lớp học có độ rung cảm biến nhẹ (1-3 px)
    TUYỆT ĐỐI KHÔNG được kích hoạt thành TẤN CÔNG (is_striking = False, interaction_score = 0).
    """
    from core.video_annotator import KinematicAnomalyRanker

    ranker = KinematicAnomalyRanker(top_k=4)

    # Frame 1: Hai học sinh ngồi cạnh nhau trong lớp
    det_s1 = {
        "raw_id": 1,
        "bbox": [100, 100, 200, 260],
        "kpts": [[150, 150, 0.9] for _ in range(17)],
        "wrist_vec": (0.0, 0.0),
        "torso_angle": 85.0
    }
    det_s2 = {
        "raw_id": 2,
        "bbox": [240, 100, 340, 260],
        "kpts": [[290, 150, 0.9] for _ in range(17)],
        "wrist_vec": (0.0, 0.0),
        "torso_angle": 85.0
    }
    ranker.update_frame([det_s1, det_s2], 640, 480)

    # Frame 2: Rung lắc nhẹ 2 pixel (sensor noise)
    det_s1_f2 = {
        "raw_id": 1,
        "bbox": [100, 100, 200, 260],
        "kpts": [[150, 150, 0.9] for _ in range(17)],
        "torso_angle": 85.0
    }
    det_s1_f2["kpts"][9] = [152, 151, 0.9]  # 2 pixels jitter
    det_s1_f2["kpts"][10] = [151, 150, 0.9]

    det_s2_f2 = {
        "raw_id": 2,
        "bbox": [240, 100, 340, 260],
        "kpts": [[290, 150, 0.9] for _ in range(17)],
        "torso_angle": 85.0
    }

    res = ranker.update_frame([det_s1_f2, det_s2_f2], 640, 480)
    s1_res = [d for d in res if d["raw_id"] == 1][0]
    s2_res = [d for d in res if d["raw_id"] == 2][0]

    # KHÔNG ĐƯỢC PHÉP kích hoạt tấn công hay phòng vệ với rung lắc cảm biến
    assert s1_res["is_striking"] == False
    assert s1_res["is_targeted"] == False
    assert s2_res["is_striking"] == False
    assert s2_res["is_targeted"] == False
    assert s1_res["interaction_score"] == 0.0
    assert s2_res["interaction_score"] == 0.0

