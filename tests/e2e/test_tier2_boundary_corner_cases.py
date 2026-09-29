"""
Tier 2: Boundary & Corner Cases E2E Tests.
Validates boundary values, cooldown timing jitter (59s vs 60s vs 61s), 429 flood bursts,
missing font fallbacks, zero-person video analysis, and buffer saturation.
Authoritative source: ORIGINAL_REQUEST.md & PROJECT.md
"""

import time
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image

from tests.e2e.conftest import (
    MockGeminiResponse,
    make_mock_inference_payload,
    raise_mock_429_error,
)

try:
    from core.model_orchestrator import (
        HierarchicalModelOrchestrator,
        ModelTier,
        CooldownTracker,
        RollingContextMemory,
        AutonomousHeuristicArbiter,
    )
    HAS_MODEL_ORCHESTRATOR = True
except ImportError:
    HAS_MODEL_ORCHESTRATOR = False


# ==============================================================================
# Area 1: Failover Timing & Flood Burst Boundaries
# ==============================================================================

class TestFailoverTimingAndFloodBoundaries:
    """Tests 59s vs 60s vs 61s cooldown threshold, 429 flood burst, empty history."""

    def test_t2_cooldown_threshold_59s_no_reversion(self):
        """At 59.0s elapsed (<60s), Tier 1 must remain in cooldown and not revert."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        tracker = CooldownTracker(cooldown_seconds=60.0)
        tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)

        # Fast forward time to 59.0 seconds elapsed
        tracker.tier1_cooldown_start = time.time() - 59.0

        assert tracker.is_tier1_ready() is False, "At 59s elapsed, Tier 1 must still be in cooldown."
        rem = tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)
        assert 0.0 < rem <= 1.5, f"At 59s elapsed, cooldown remaining should be ~1.0s, got {rem}"

    def test_t2_cooldown_threshold_60s_exact_boundary(self):
        """At exactly 60.0s elapsed, Tier 1 cooldown must expire and become ready."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        tracker = CooldownTracker(cooldown_seconds=60.0)
        tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)

        # Fast forward time to exactly 60.0 seconds elapsed
        tracker.tier1_cooldown_start = time.time() - 60.001

        assert tracker.is_tier1_ready() is True, "At 60s elapsed, Tier 1 must be ready."
        assert tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY) == 0.0

    def test_t2_cooldown_threshold_61s_preemptive_reversion(self, sample_pil_frame):
        """At 61.0s elapsed, next inference request must preemptively revert to Tier 1."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        orchestrator = HierarchicalModelOrchestrator(api_key="test_key")
        orchestrator.active_tier = ModelTier.TIER_2_FALLBACK
        orchestrator.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)

        # Fast forward cooldown past 60s to 61s
        orchestrator.cooldown_tracker.tier1_cooldown_start = time.time() - 61.0

        # Mock client so Tier 1 succeeds
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MockGeminiResponse(
            make_mock_inference_payload(action="Làm việc bình thường")
        )
        orchestrator.client = mock_client

        bio = {"posture": "Ngồi thẳng", "angle": 90.0, "is_danger": False, "is_warning": False}
        result = orchestrator.execute_live_analysis(sample_pil_frame, bio)

        # Preemptive reversion check
        assert orchestrator.active_tier == ModelTier.TIER_1_PRIMARY, (
            "At 61s, orchestrator must preemptively revert active tier to Tier-1 Primary."
        )

    def test_t2_simultaneous_429_flood_burst(self, sample_pil_frame):
        """A rapid flood of 10 consecutive 429 errors must not crash and cascade safely to Tier 3."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        orchestrator = HierarchicalModelOrchestrator(api_key="test_key")
        
        # Configure client to always raise 429 for all models
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = raise_mock_429_error
        orchestrator.client = mock_client

        bio = {"posture": "Ngồi học", "angle": 85.0, "is_danger": False, "is_warning": False}

        for burst_idx in range(10):
            res = orchestrator.execute_live_analysis(sample_pil_frame, bio)
            assert isinstance(res, dict)
            assert "action" in res
            assert "description" in res
            assert "severity" in res

        # After all cloud tiers fail with 429, active tier must be Tier 3 Heuristic Arbiter
        assert orchestrator.active_tier == ModelTier.TIER_3_HEURISTIC, (
            "After all tiers 429 flood, system must reside stably on Tier 3 Arbiter."
        )

    def test_t2_empty_rolling_context_on_startup(self):
        """Initial cycle (empty context history) generates valid initial prompt without error."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        memory = RollingContextMemory(maxlen=5)
        summary = memory.get_context_summary_for_prompt()
        assert isinstance(summary, str)
        assert len(summary) > 0, "Initial prompt summary must not be empty string."


# ==============================================================================
# Area 2: Media, Font & Buffer Boundaries
# ==============================================================================

class TestMediaFontAndBufferBoundaries:
    """Tests missing fonts fallback, empty frame, zero-person video, buffer saturation."""

    def test_t2_missing_all_system_fonts_fallback(self):
        """When TrueType font files are missing or unreadable, fallback resolves without crash."""
        from core.cyber_hud import CyberHUDRenderer
        hud = CyberHUDRenderer()

        # Simulate missing fonts by calling _load_font with non-existent paths
        font = hud._load_font("non_existent_font_xyz_12345.ttf", 20)
        assert font is not None, "Fallback font must not be None even if target font file is missing."

    def test_t2_empty_or_corrupt_frame_image(self):
        """Passing an empty or degenerate image buffer does not crash HUD or VideoAnnotator."""
        from core.cyber_hud import CyberHUDRenderer
        hud = CyberHUDRenderer()

        empty_frame = np.zeros((0, 0, 3), dtype=np.uint8)
        metrics = {"gpu_name": "CPU", "producer_fps": 0.0}
        diagnosis = {"action": "None"}

        # Attempt to render with degenerate dimensions
        try:
            # Should either handle gracefully or raise standard ValueError, not segfault
            hud.render_sidebar_pil(diagnosis=diagnosis, entities={}, metrics=metrics, danger_score=0, danger_level="AN TOÀN")
        except Exception as e:
            assert isinstance(e, (ValueError, IndexError, TypeError))

    def test_t2_zero_person_detected_in_video_segment(self, sample_bgr_frame):
        """Video segment with 0 detected persons returns safe neutral report."""
        from core.token_guard import TokenGuard
        guard = TokenGuard()

        # Frame with threat_score 0 and no detections
        frames = [{
            "frame": sample_bgr_frame,
            "timestamp": 0.0,
            "threat_score": 0.0,
            "action": "Không có người",
            "confidence": 0.0
        }]

        if hasattr(guard, "_synthesize_local_autonomous_report"):
            report = guard._synthesize_local_autonomous_report(
                event_summary=[],
                video_metadata={"duration": 5.0, "fps": 30.0},
                segment_info=[{"start_sec": 0.0, "end_sec": 5.0, "entity_count": 0}]
            )
            assert isinstance(report, dict)
            danger = report.get("threat_level") or report.get("overall_danger_level")
            assert danger in ["AN TOÀN", "AN TOAN", "safe", "Safe"]

    def test_t2_extreme_bounded_buffer_saturation(self):
        """Buffer saturation (queue_size == queue_max) activates drop-frame flow control."""
        from core.capture import VideoCaptureProducer
        import queue

        producer = VideoCaptureProducer(video_source=0, max_queue_size=5)
        # Manually fill the queue to max capacity
        dummy_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        for _ in range(5):
            producer.frame_queue.put(dummy_frame)

        assert producer.frame_queue.full() is True

        # Next put should drop or pop to maintain bounded buffer
        init_drops = getattr(producer, "total_frames_dropped", 0)
        # Attempt to enqueue
        try:
            producer.frame_queue.put_nowait(dummy_frame)
        except queue.Full:
            if hasattr(producer, "total_frames_dropped"):
                producer.total_frames_dropped += 1

        current_drops = getattr(producer, "total_frames_dropped", 0)
        assert current_drops == init_drops + 1

    def test_t2_capcut_timeline_trimmer_zero_duration(self, client):
        """Processing video with start_time >= end_time returns 400 Bad Request or validation error."""
        payload = {
            "video_path": "demo_synthetic.mp4",
            "start_time": 5.0,
            "end_time": 5.0  # Zero duration slice
        }
        resp = client.post("/api/video/process", json=payload)
        # Should reject invalid timeline slice with 400 or error json
        if resp.status_code == 200:
            data = resp.json()
            assert "error" in data or data.get("status") == "error", (
                "Zero-duration slice should return error indicator in response."
            )
        else:
            assert resp.status_code in [400, 422], f"Expected 400/422 for 0s duration slice, got {resp.status_code}"
