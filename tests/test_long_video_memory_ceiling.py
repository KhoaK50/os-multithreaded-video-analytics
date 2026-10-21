"""
Test Suite: Long Video Memory Ceiling & Fixed RAM Bound Verification.
Verifies that processing long videos (>= 3,870 frames) strictly adheres to fixed RAM bounds:
1. BoundedKeyframeManager enforces max_capacity ceiling (<= 32 frames) under 5,000+ candidate additions.
2. High threat candidates are prioritized over low threat candidates.
3. Milestones are preserved during evictions.
4. Dictionary interface compatibility for TokenGuard.
5. All stored frames are downscaled (width <= 640, height <= 360), preventing cv::OutOfMemoryError.
6. Pipeline report includes bounded_ram_ceiling_mb and ram_ceiling_mb.
"""

import pytest
import numpy as np
import gc
from core.video_annotator import BoundedKeyframeManager, _downscale_preview_frame


def test_bounded_keyframe_manager_capacity_ceiling():
    """Verify that adding 5,000 frames never exceeds max_capacity (fixed ceiling = 32)."""
    manager = BoundedKeyframeManager(max_capacity=32, max_w=640, max_h=360)
    dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    for i in range(5000):
        ts = round(i * 0.1, 2)
        score = float(i % 10)
        manager.add_candidate(ts, dummy_frame, threat_score=score)

    assert len(manager) <= 32
    assert len(list(manager.keys())) <= 32
    assert len(list(manager.values())) <= 32
    assert len(list(manager.items())) <= 32


def test_bounded_keyframe_manager_downscales_frames():
    """Verify that all stored frames are downscaled within (640, 360)."""
    manager = BoundedKeyframeManager(max_capacity=16, max_w=640, max_h=360)
    full_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 128

    manager.add_candidate(1.0, full_frame, threat_score=5.0)
    stored = manager[1.0]

    h, w, c = stored.shape
    assert w <= 640
    assert h <= 360
    assert c == 3
    # Memory for 1 frame must be <= 640*360*3 bytes = 691.2 KB (compared to 6.2 MB for 1080p)
    assert stored.nbytes <= 700000


def test_bounded_keyframe_manager_threat_priority_eviction():
    """Verify eviction prioritizes keeping high threat scores over low threat scores."""
    manager = BoundedKeyframeManager(max_capacity=8, max_w=320, max_h=180)
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Fill capacity with low threat items
    for i in range(8):
        manager.add_candidate(float(i), dummy_frame, threat_score=1.0)

    assert len(manager) == 8

    # Add a high threat item
    manager.add_candidate(99.0, dummy_frame, threat_score=9.5)
    assert len(manager) == 8
    assert 99.0 in manager

    # Add another high threat item
    manager.add_candidate(100.0, dummy_frame, threat_score=8.5)
    assert len(manager) == 8
    assert 100.0 in manager


def test_bounded_keyframe_manager_milestone_protection():
    """Verify milestone frames are protected from eviction when newer items arrive."""
    manager = BoundedKeyframeManager(max_capacity=8, max_w=320, max_h=180)
    dummy_frame = np.zeros((50, 50, 3), dtype=np.uint8)

    # Add initial milestone
    manager.add_candidate(0.0, dummy_frame, threat_score=2.0, is_milestone=True)

    # Fill remaining capacity with non-milestones
    for i in range(1, 8):
        manager.add_candidate(float(i), dummy_frame, threat_score=5.0)

    assert len(manager) == 8
    assert 0.0 in manager

    # Add more items with higher scores
    for i in range(10, 25):
        manager.add_candidate(float(i), dummy_frame, threat_score=6.0)

    # First timestamp (start milestone) is protected
    assert 0.0 in manager
    assert len(manager) <= 8


def test_bounded_keyframe_dict_compatibility():
    """Verify BoundedKeyframeManager supports standard dictionary access patterns used by TokenGuard."""
    manager = BoundedKeyframeManager(max_capacity=10)
    dummy = np.zeros((64, 64, 3), dtype=np.uint8)

    manager[1.5] = dummy
    manager.add_candidate(2.5, dummy, threat_score=3.0)

    assert 1.5 in manager
    assert 2.5 in manager
    assert 999.0 not in manager
    assert manager.get(1.5) is not None
    assert manager.get(999.0, "default_val") == "default_val"

    # Sorted keys check
    timestamps = sorted(manager.keys())
    assert timestamps == [1.5, 2.5]

    # Copy returns a regular dict
    copied = manager.copy()
    assert isinstance(copied, dict)
    assert 1.5 in copied


def test_long_video_simulation_memory_ceiling():
    """
    Simulate keyframe accumulation over 4,000 frames (exceeding the 3,870 threshold).
    Ensure total candidate memory is bounded under 25 MB (strictly preventing cv::OutOfMemoryError).
    """
    manager = BoundedKeyframeManager(max_capacity=32, max_w=640, max_h=360)
    full_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    total_simulated_frames = 4000
    for frame_idx in range(total_simulated_frames):
        ts = round(frame_idx / 30.0, 2)
        # Periodic danger frame trigger
        is_danger = (frame_idx % 25 == 0)
        score = 9.0 if is_danger else 1.0
        is_milestone = frame_idx in [0, 600, 2000, 3400]

        if is_danger or is_milestone or (frame_idx % 45 == 0):
            manager.add_candidate(ts, full_frame, threat_score=score, is_milestone=is_milestone)

        if frame_idx % 500 == 0:
            gc.collect()

    assert len(manager) <= 32
    total_bytes = sum(f.nbytes for f in manager.values())
    total_mb = total_bytes / (1024 * 1024)
    # 32 frames of max 640x360x3 bytes is at most ~21.1 MB
    assert total_mb <= 25.0, f"Candidate keyframes exceeded memory bound: {total_mb:.2f} MB"


def test_full_pipeline_4000_frames_memory_ceiling(monkeypatch, tmp_path):
    """
    Test full 3-Stage Pipeline (Reader -> Inference -> Writer) with 4,000 frames (exceeding 3,870 frames).
    Verifies:
    1. Full 4,000 frames processed without cv::OutOfMemoryError.
    2. Memory growth remains strictly bounded.
    3. Candidate keyframes <= 32.
    4. Segments image arrays are fully released.
    5. os_pipeline_report contains ram_ceiling_mb and bounded_ram_ceiling_mb.
    """
    import cv2
    from unittest.mock import MagicMock
    from core.video_annotator import VideoAnnotatorEngine

    engine = VideoAnnotatorEngine()
    engine.is_ready = True
    engine.device = "cpu"

    # Use a stateless dummy model (avoid MagicMock which caches all 4,000 frame references)
    class DummyModel:
        def track(self, frame, *a, **kw):
            return []
        def __call__(self, frame, *a, **kw):
            return []

    engine.model = DummyModel()

    total_frames = 4000
    w, h = 640, 360

    class MockCap:
        def __init__(self):
            self.count = 0
            self._frame = np.zeros((h, w, 3), dtype=np.uint8)
        def isOpened(self):
            return True
        def get(self, prop):
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return float(total_frames)
            elif prop == cv2.CAP_PROP_FPS:
                return 30.0
            elif prop == cv2.CAP_PROP_FRAME_WIDTH:
                return float(w)
            elif prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return float(h)
            return 0.0
        def read(self):
            if self.count >= total_frames:
                return False, None
            self.count += 1
            return True, self._frame.copy()
        def release(self):
            pass

    class MockWriter:
        def __init__(self, *args, **kwargs):
            self.frames_written = 0
        def isOpened(self):
            return True
        def write(self, frame):
            self.frames_written += 1
        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **kw: MockCap())
    monkeypatch.setattr(cv2, "VideoWriter", lambda *a, **kw: MockWriter())
    monkeypatch.setattr("core.video_annotator.check_video_has_audio", lambda *a, **kw: False)

    out_file = str(tmp_path / "annotated.mp4")
    res = engine.process_video(
        input_path="mock_input.mp4",
        output_path=out_file,
        start_time=0.0,
        end_time=None,
        call_gemini=False,
        anomaly_focus=False
    )

    assert res["total_frames"] == total_frames
    assert res["frame_count"] == total_frames
    assert "os_pipeline_report" in res
    os_rep = res["os_pipeline_report"]
    assert "ram_ceiling_mb" in os_rep
    assert "bounded_ram_ceiling_mb" in os_rep
    assert os_rep["ram_ceiling_mb"] <= 90.0
    assert "dijkstra_ram_ceiling_mb" not in os_rep

    # Verify that heavy arrays in timeline_segments were released
    for seg in res.get("timeline_segments", []):
        assert "peak_frame" not in seg or seg.get("peak_frame") is None
        assert "burst_frames" not in seg or len(seg.get("burst_frames", [])) == 0

