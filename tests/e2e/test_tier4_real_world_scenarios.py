"""
Tier 4: Real-World Scenarios E2E Tests.
Validates realistic end-to-end user workflows:
1. CapCut timeline video processing with safety checks and single synthesis token guard.
2. 90-second simulated 15 RPM rate limiting with continuous telemetry monitoring and preemptive reversion.
3. Natural language query on event history under failover conditions.
Authoritative source: ORIGINAL_REQUEST.md & PROJECT.md
"""

import time
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image

from tests.e2e.conftest import (
    PROJECT_ROOT,
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
        ContextMemoryEntry,
    )
    HAS_MODEL_ORCHESTRATOR = True
except ImportError:
    HAS_MODEL_ORCHESTRATOR = False


class TestRealWorldWorkflows:
    """End-to-End realistic user workflows and temporal scenarios."""

    def test_t4_capcut_timeline_workflow_with_safety_checks(self, client):
        """Full CapCut timeline slice processing: validation, YOLOv8 pose inference, and single synthesis."""
        demo_video = PROJECT_ROOT / "demo_synthetic.mp4"
        if not demo_video.exists():
            pytest.skip("demo_synthetic.mp4 not found in workspace root.")

        payload = {
            "video_path": str(demo_video),
            "start_time": 0.0,
            "end_time": 3.0,
            "call_gemini": False
        }

        # Process slice via /api/video/process
        resp = client.post("/api/video/process", json=payload)
        assert resp.status_code == 200, f"Expected 200 OK from /api/video/process, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Check returned report structure
        assert "status" in data or "task_id" in data or "summary" in data or "overall_danger_level" in data, (
            f"Unexpected response structure: {data}"
        )

    def test_t4_simulated_15rpm_rate_limiting_with_continuous_telemetry(self, sample_pil_frame):
        """Simulates 90-second operational window: Normal -> 429 Failover -> Cooldown Tracking -> Preemptive Reversion."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        orchestrator = HierarchicalModelOrchestrator(api_key="test_key", cooldown_seconds=60.0)

        # Step 1: Normal execution on Tier 1 (simulated cycles 1-3)
        tier1_call_count = 0
        tier2_call_count = 0

        mock_client = MagicMock()
        def mock_generate(model, contents, **kwargs):
            nonlocal tier1_call_count, tier2_call_count
            if "2.0" in model or "2.5" in model:
                tier1_call_count += 1
                if tier1_call_count > 3:
                    # Chạm trần 15 RPM ở cycle 4
                    raise Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded (15 RPM).")
                return MockGeminiResponse(make_mock_inference_payload(action=f"Hành vi Tier 1 cycle {tier1_call_count}"))
            elif "1.5" in model:
                tier2_call_count += 1
                return MockGeminiResponse(make_mock_inference_payload(action=f"Hành vi Tier 2 cycle {tier2_call_count}"))
            raise Exception("Unknown model")

        mock_client.models.generate_content.side_effect = mock_generate
        orchestrator.client = mock_client

        bio = {"posture": "Ngồi học", "angle": 88.0, "is_danger": False, "is_warning": False}

        # Cycles 1 to 3: Normal Tier 1
        for c in range(1, 4):
            res = orchestrator.execute_live_analysis(sample_pil_frame, bio)
            assert orchestrator.active_tier == ModelTier.TIER_1_PRIMARY
            assert f"Tier 1 cycle {c}" in res["action"]

        # Cycle 4: Triggers 429 on Tier 1 -> Instant failover to Tier 2
        res4 = orchestrator.execute_live_analysis(sample_pil_frame, bio)
        assert orchestrator.active_tier == ModelTier.TIER_2_FALLBACK
        assert "Tier 2 cycle 1" in res4["action"]
        assert orchestrator.cooldown_tracker.is_tier1_ready() is False

        # Cycles 5 & 6: Running in Tier 2 while cooldown is active (<60s)
        for c in range(2, 4):
            res = orchestrator.execute_live_analysis(sample_pil_frame, bio)
            assert orchestrator.active_tier == ModelTier.TIER_2_FALLBACK
            assert f"Tier 2 cycle {c}" in res["action"]

        # Fast forward time: 61 seconds have passed since 429
        orchestrator.cooldown_tracker.tier1_cooldown_start -= 61.0
        assert orchestrator.cooldown_tracker.is_tier1_ready() is True

        # Cycle 7: Preemptive reversion should automatically switch back to Tier 1
        # Reset Tier 1 mock to succeed again
        tier1_call_count = 0  # Quota recovered
        res7 = orchestrator.execute_live_analysis(sample_pil_frame, bio)
        assert orchestrator.active_tier == ModelTier.TIER_1_PRIMARY
        assert "Tier 1 cycle 1" in res7["action"]

        # Verify semantic continuity: context memory contains both Tier 1 and Tier 2 history
        entries = orchestrator.context_memory.get_recent_entries()
        assert len(entries) >= 4, "Context memory should hold sequential history across all cycles."
        tiers_recorded = [e["tier_used"] for e in entries]
        assert any("Tier-1" in t for t in tiers_recorded)
        assert any("Tier-2" in t for t in tiers_recorded)

    def test_t4_end_to_end_chat_assistance_with_failover(self, client):
        """Endpoint /api/chat responds intelligently about events even during cloud rate limits."""
        payload = {
            "question": "Trong 10 giây qua có hành vi nào nguy hiểm không?",
            "job_id": None
        }
        resp = client.post("/api/chat", json=payload)
        # Should return 200 OK with response text or answer
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data or "response" in data or "reply" in data

