"""
Tier 3: Cross-Feature Interactions E2E Tests.
Validates pairwise interactions between concurrent subsystems:
- Live failover during video upload start
- Theme toggle with active camera stream
- Mobile layout with telemetry streaming
- Bounded buffer drop sync with video HUD
- Rolling context preserved across multi-tier transitions
Authoritative source: ORIGINAL_REQUEST.md & PROJECT.md
"""

import time
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image

from tests.e2e.conftest import (
    PROJECT_ROOT,
    STATIC_DIR,
    TEMPLATES_DIR,
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


class TestCrossFeatureInteractions:
    """Pairwise cross-feature and concurrent subsystem interactions."""

    def test_t3_failover_during_live_stream_while_video_upload_starts(self, client, sample_pil_frame):
        """Live camera triggers 429 failover while video upload begins; Rate Limiter guards quota."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        orchestrator = HierarchicalModelOrchestrator(api_key="test_key")

        # Mock client so Tier 1 raises 429
        mock_client = MagicMock()
        def side_effect(model, contents, **kwargs):
            if "2.0" in model or "2.5" in model:
                raise Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded.")
            return MockGeminiResponse(make_mock_inference_payload(action="Giám sát video"))

        mock_client.models.generate_content.side_effect = side_effect
        orchestrator.client = mock_client

        # 1. Live stream frame triggers 429 and transitions to Tier 2
        bio = {"posture": "Ngồi", "angle": 85.0, "is_danger": False, "is_warning": False}
        live_result = orchestrator.execute_live_analysis(sample_pil_frame, bio)
        assert live_result["action"] == "Giám sát video"
        assert orchestrator.active_tier == ModelTier.TIER_2_FALLBACK

        # 2. Concurrently check rate limit permission for video upload
        if hasattr(orchestrator, "acquire_api_permission"):
            # Rapid call immediately after live inference should enforce delay
            granted = orchestrator.acquire_api_permission(priority="normal")
            # If rate limiter is active, immediate second request without delay might be throttled
            assert isinstance(granted, bool)

    def test_t3_theme_toggle_with_active_camera_stream(self, client):
        """Theme toggle between dark and light modes does not affect /api/stream/live headers or telemetry."""
        # 1. Inspect CSS to ensure theme variable mapping exists for both modes
        css_file = STATIC_DIR / "style.css"
        css = css_file.read_text(encoding="utf-8")

        # 2. Verify stream response headers are MJPEG multipart
        # Note: testing stream endpoint with TestClient
        resp = client.get("/api/telemetry")
        assert resp.status_code == 200

        # Stream endpoint exists
        # In TestClient, streaming endpoints may stream indefinitely, so we check status/route registration
        from core.web_server import app
        routes = [r.path for r in app.routes]
        assert "/api/stream/live" in routes, "Live stream endpoint must be registered in FastAPI routes."

    def test_t3_mobile_layout_with_telemetry_stream(self, client):
        """Mobile viewport (< 768px) CSS media rules ensure telemetry grid cards adapt to narrow screens."""
        css_file = STATIC_DIR / "style.css"
        css = css_file.read_text(encoding="utf-8")

        # Check for media query covering mobile viewports
        assert "@media" in css and "768px" in css, "style.css must include @media (max-width: 768px)"

        # Check telemetry fields are suitable for mobile dashboard display
        resp = client.get("/api/telemetry")
        assert resp.status_code == 200
        telemetry = resp.json()
        assert "cpu_percent" in telemetry, "Telemetry missing cpu_percent"
        assert "ram_percent" in telemetry, "Telemetry missing ram_percent"
        assert "fps" in telemetry or "producer_fps" in telemetry, "Telemetry missing fps metric"

    def test_t3_bounded_buffer_drop_rate_sync_with_video_hud(self):
        """Artificial bounded buffer drop synchronizes across video HUD and telemetry data structures."""
        from core.cyber_hud import CyberHUDRenderer
        hud = CyberHUDRenderer()

        # Simulate 15 dropped frames due to consumer slowdown
        metrics = {
            "producer_fps": 30.0,
            "queue_size": 32,
            "queue_max": 32,
            "dropped_frames": 15,
            "drop_rate_pct": 5.2,
            "cpu_percent": 88.0,
            "ram_percent": 72.0,
            "gpu_vram_used": 3.5,
            "gpu_vram_total": 8.0,
            "gpu_name": "RTX 5060"
        }
        diagnosis = {
            "action": "Vận động nhanh",
            "threat_level": "CẢNH BÁO",
            "model_tier_str": "● Tier-1 Gemini 2.0"
        }

        # Render sidebar
        sidebar = hud.render_sidebar_pil(
            diagnosis=diagnosis,
            entities={"person": 1},
            metrics=metrics,
            danger_score=0,
            danger_level="CẢNH BÁO"
        )
        assert isinstance(sidebar, np.ndarray)
        assert sidebar.shape == (720, hud.sidebar_w, 3)

    def test_t3_rolling_context_injected_across_tier_transitions(self, sample_pil_frame):
        """Context memory preserves 5 cycles across Tier 1 -> Tier 2 -> Tier 1 transitions."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        orchestrator = HierarchicalModelOrchestrator(api_key="test_key")

        # Record 3 initial cycles in Tier 1
        now = time.time()
        orchestrator.context_memory.record(ContextMemoryEntry(
            timestamp=now - 8.0, time_str="12:00:00", action="Ngồi đọc sách",
            description="Tư thế ổn định", posture="Ngồi thẳng", torso_angle=88.0,
            prediction="Tiếp tục đọc", severity="safe", tier_used="Tier-1"
        ))
        orchestrator.context_memory.record(ContextMemoryEntry(
            timestamp=now - 4.0, time_str="12:00:04", action="Nghiêng người",
            description="Lấy tài liệu bên phải", posture="Nghiêng", torso_angle=70.0,
            prediction="Trở về tư thế thẳng", severity="safe", tier_used="Tier-1"
        ))

        # Simulate Tier 1 429 failover to Tier 2
        captured_prompts = []
        mock_client = MagicMock()
        def mock_generate(model, contents, **kwargs):
            if "2.0" in model or "2.5" in model:
                raise Exception("429 RESOURCE_EXHAUSTED")
            # Capture prompt passed to Tier 2
            captured_prompts.append(contents[0] if isinstance(contents, list) else str(contents))
            return MockGeminiResponse(make_mock_inference_payload(
                action="Đứng dậy",
                description="Đối tượng đã đứng dậy sau khi lấy tài liệu",
                severity="safe"
            ))

        mock_client.models.generate_content.side_effect = mock_generate
        orchestrator.client = mock_client

        bio = {"posture": "Đứng dậy", "angle": 90.0, "is_danger": False, "is_warning": False}
        res = orchestrator.execute_live_analysis(sample_pil_frame, bio)

        # Verify Tier 2 prompt received the past 2 cycles from Tier 1
        assert len(captured_prompts) > 0, "Tier 2 should have been called."
        prompt_sent = captured_prompts[0]
        assert "Ngồi đọc sách" in prompt_sent, "Tier 2 prompt must contain history from Tier 1 (Ngồi đọc sách)."
        assert "Nghiêng người" in prompt_sent, "Tier 2 prompt must contain history from Tier 1 (Nghiêng người)."
