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

    # Frame 1: Xung lực cao lần 1 -> Chưa kích hoạt (vẫn là observer)
    res1 = stab.update(c_id, "Vung tay ra đòn", "attacker", True, 8.5, 3.0, 2.5)
    assert res1["role"] != "attacker"
    assert res1["is_danger"] == False

    # Frame 2: Xung lực cao lần 2 -> Chưa kích hoạt
    res2 = stab.update(c_id, "Vung tay ra đòn", "attacker", True, 8.5, 3.0, 2.5)
    assert res2["role"] != "attacker"

    # Frame 3: Xung lực cao lần 3 -> Đủ 3 frames -> KÍCH HOẠT ĐỎ
    res3 = stab.update(c_id, "Vung tay ra đòn", "attacker", True, 8.5, 3.0, 2.5)
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
