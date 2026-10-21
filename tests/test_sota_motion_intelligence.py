"""
Unit tests for SOTA Zero-Training Motion Intelligence Techniques:
1. Motion History Image (MHI) & Temporal Kinetic Decay
2. Centripetal Convergence Vector (CCV) Kinematics
3. Peak Derivative Impact Trigger (dE/dt)
"""

import numpy as np
import cv2
import pytest
from core.optical_motion_engine import OpticalMotionEngine


def test_mhi_temporal_decay_vs_persistence():
    """Verify that transient motion decays quickly while persistent turbulence maintains high MHI persistence."""
    engine = OpticalMotionEngine(target_width=320, target_height=180, tau_frames=10)
    w, h = 640, 360

    # 1. Transient motion (flash/light sweep lasting only 1 frame)
    frame_static = np.zeros((h, w, 3), dtype=np.uint8)
    frame_flash = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.rectangle(frame_flash, (100, 100), (200, 200), (255, 255, 255), -1)

    engine.process_frame(frame_static, 0.0, w, h)
    engine.process_frame(frame_flash, 0.033, w, h)
    assert np.max(engine.mhi_map) > 0.0

    # After several static frames, MHI should completely decay to 0
    for i in range(12):
        res = engine.process_frame(frame_static, 0.033 * (i + 2), w, h)

    assert np.max(engine.mhi_map) == 0.0
    assert res["mhi_persistence"] == 0.0

    # 2. Persistent movement: moving blob across multiple consecutive frames
    engine.reset()
    for step in range(8):
        f = np.zeros((h, w, 3), dtype=np.uint8)
        # Oscillate blob back and forth in same region (simulating scuffle/struggle)
        offset = (step % 2) * 20
        cv2.circle(f, (300 + offset, 180), 40, (255, 255, 255), -1)
        res_pers = engine.process_frame(f, 0.033 * step, w, h)

    assert res_pers["mhi_persistence"] > 0.0


def test_centripetal_convergence_head_on_vs_parallel():
    """Verify Centripetal Convergence Vector differentiates direct collision approach from parallel movement."""
    engine = OpticalMotionEngine(target_width=320, target_height=180)
    w, h = 640, 360

    # Scenario A: Head-on collision approach (Left blob moves Right, Right blob moves Left)
    f1 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(f1, (200, 180), 30, (255, 255, 255), -1)  # Left entity
    cv2.circle(f1, (340, 180), 30, (255, 255, 255), -1)  # Right entity

    f2 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(f2, (230, 180), 30, (255, 255, 255), -1)  # Moves +30px to right
    cv2.circle(f2, (310, 180), 30, (255, 255, 255), -1)  # Moves -30px to left

    bbox_left = (170, 150, 260, 210)
    bbox_right = (280, 150, 370, 210)

    engine.process_frame(f1, 0.0, w, h)
    engine.process_frame(f2, 0.033, w, h)

    ccv_head_on = engine.compute_centripetal_convergence(bbox_left, bbox_right, w, h)
    assert ccv_head_on["is_converging"] is True
    assert ccv_head_on["convergence_rate"] > 0.8

    # Scenario B: Parallel movement (both blobs move in same direction +30px to right)
    engine.reset()
    f3 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(f3, (200, 180), 30, (255, 255, 255), -1)
    cv2.circle(f3, (340, 180), 30, (255, 255, 255), -1)

    f4 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(f4, (230, 180), 30, (255, 255, 255), -1)  # Both move +30px to right
    cv2.circle(f4, (370, 180), 30, (255, 255, 255), -1)

    engine.process_frame(f3, 0.0, w, h)
    engine.process_frame(f4, 0.033, w, h)

    ccv_parallel = engine.compute_centripetal_convergence(bbox_left, bbox_right, w, h)
    assert ccv_parallel["is_converging"] is False


def test_peak_derivative_impact_trigger_dE_dt():
    """Verify that sudden strike/shockwave triggers dE/dt peak and is_impact_shockwave."""
    engine = OpticalMotionEngine(target_width=320, target_height=180)
    w, h = 640, 360

    f1 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(f1, (300, 180), 20, (255, 255, 255), -1)

    # Frame 2: very slight movement
    f2 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(f2, (302, 180), 20, (255, 255, 255), -1)

    engine.process_frame(f1, 0.0, w, h)
    res2 = engine.process_frame(f2, 0.033, w, h)
    assert res2["is_impact_shockwave"] is False

    # Frame 3: sudden explosive strike displacement (60 pixels in 0.033s)
    f3 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(f3, (360, 220), 40, (255, 255, 255), -1)

    res3 = engine.process_frame(f3, 0.066, w, h)
    assert res3["dE_dt"] > 5.0
    assert res3["is_impact_shockwave"] is True
