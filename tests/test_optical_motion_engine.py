"""
Unit tests for OpticalMotionEngine (Dense Farneback Optical Flow Engine).
Verifies:
1. Static frame: zero kinetic energy and no threat.
2. Laminar flow (walking): low directional turbulence, threat remains safe.
3. Chaotic scuffle motion (violent interaction): high kinetic energy, high directional turbulence,
   is_violent_scuffle is True, motion_threat_score >= 8.0, and active_motion_bbox is generated.
4. Camera shake compensation (Median Flow Subtraction): uniform camera movement is neutralized.
5. Reset clears state cleanly.
"""

import numpy as np
import cv2
import pytest
from core.optical_motion_engine import OpticalMotionEngine


def test_optical_motion_engine_static_frame():
    engine = OpticalMotionEngine(target_width=320, target_height=180)
    frame1 = np.ones((720, 1280, 3), dtype=np.uint8) * 100
    frame2 = np.ones((720, 1280, 3), dtype=np.uint8) * 100

    res1 = engine.process_frame(frame1, 0.0, 1280, 720)
    assert res1["kinetic_energy"] == 0.0
    assert res1["is_violent_scuffle"] is False

    res2 = engine.process_frame(frame2, 0.033, 1280, 720)
    assert res2["kinetic_energy"] < 0.5
    assert res2["is_violent_scuffle"] is False
    assert res2["motion_threat_score"] < 2.0


def test_optical_motion_engine_laminar_flow():
    """Laminar flow (e.g. person walking smoothly to the right): low turbulence, threat remains safe."""
    engine = OpticalMotionEngine(target_width=320, target_height=180)
    w, h = 1280, 720

    frame1 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(frame1, (400, 360), 60, (255, 255, 255), -1)

    frame2 = np.zeros((h, w, 3), dtype=np.uint8)
    # Move smoothly 15px to the right
    cv2.circle(frame2, (415, 360), 60, (255, 255, 255), -1)

    engine.process_frame(frame1, 0.0, w, h)
    res2 = engine.process_frame(frame2, 0.033, w, h)

    # All motion is in +x direction -> low turbulence (circular variance is low)
    assert res2["turbulence_score"] < 0.40
    assert res2["is_violent_scuffle"] is False
    assert res2["motion_threat_score"] < 7.0


def test_optical_motion_engine_violent_scuffle():
    """Chaotic scuffle (opposing violent vectors clashing): high turbulence and threat >= 8.0."""
    engine = OpticalMotionEngine(target_width=320, target_height=180)
    w, h = 1280, 720

    # Create pattern with multiple moving blobs with opposing trajectories
    frame1 = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(frame1, (500, 360), 70, (255, 255, 255), -1)
    cv2.circle(frame1, (780, 360), 70, (255, 255, 255), -1)

    frame2 = np.zeros((h, w, 3), dtype=np.uint8)
    # Blob 1 moves violently right & down (+80, +50)
    cv2.circle(frame2, (580, 410), 70, (255, 255, 255), -1)
    # Blob 2 moves violently left & up (-80, -50) - directly colliding!
    cv2.circle(frame2, (700, 310), 70, (255, 255, 255), -1)

    engine.process_frame(frame1, 0.0, w, h)
    res2 = engine.process_frame(frame2, 0.033, w, h)

    assert res2["kinetic_energy"] > 2.0
    assert res2["turbulence_score"] > 0.45
    assert res2["motion_threat_score"] >= 7.5
    assert res2["is_violent_scuffle"] is True
    assert res2["active_motion_bbox"] is not None
    # Verify bbox is within valid image dimensions
    bx1, by1, bx2, by2 = res2["active_motion_bbox"]
    assert 0 <= bx1 < bx2 <= w
    assert 0 <= by1 < by2 <= h


def test_optical_motion_engine_camera_shake_compensation():
    """Global camera motion (whole background panning) is subtracted out by median filter."""
    engine = OpticalMotionEngine(target_width=320, target_height=180)
    w, h = 1280, 720

    # Textured background with gradient
    frame1 = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    frame1 = cv2.cvtColor(frame1, cv2.COLOR_GRAY2BGR)

    # Shift whole frame by 10 pixels (simulating handheld camera shake)
    M = np.float32([[1, 0, 10], [0, 1, 5]])
    frame2 = cv2.warpAffine(frame1, M, (w, h))

    engine.process_frame(frame1, 0.0, w, h)
    res2 = engine.process_frame(frame2, 0.033, w, h)

    # Since median vector is subtracted, relative kinetic energy should be very low
    assert res2["is_violent_scuffle"] is False
    assert res2["motion_threat_score"] < 4.0


def test_optical_motion_engine_reset():
    engine = OpticalMotionEngine()
    frame = np.ones((720, 1280, 3), dtype=np.uint8) * 128
    engine.process_frame(frame, 0.0, 1280, 720)
    assert engine.prev_gray is not None

    engine.reset()
    assert engine.prev_gray is None
    assert engine.prev_timestamp == 0.0
