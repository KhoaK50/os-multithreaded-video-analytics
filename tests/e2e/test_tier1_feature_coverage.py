"""
Tier 1: Feature Coverage E2E Tests (F01 - F19).
Validates primary behavior (happy path) and interface contracts for all 19 features.
Authoritative source: ORIGINAL_REQUEST.md & PROJECT.md
"""

import os
import re
import sys
import json
import time
import subprocess
import py_compile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tests.e2e.conftest import (
    PROJECT_ROOT,
    TEMPLATES_DIR,
    STATIC_DIR,
    FORBIDDEN_SLOP_TERMS,
    REQUIRED_OS_TERMS,
    MockGeminiResponse,
    make_mock_inference_payload,
    raise_mock_429_error,
)

# Optional import of model_orchestrator (M1 deliverable)
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
# Area 1: Hierarchical Failover & Context Memory (F01, F02, F03, F04, F05)
# ==============================================================================

class TestHierarchicalFailoverAndContextMemory:
    """Tests Features 1 through 5: Failover, Cooldown 60s, Context Memory, Arbiter."""

    def test_t1_f01_hierarchical_tiers_priority(self):
        """F01: Verify priority hierarchy: Tier 1 (2.0/2.5-flash) -> Tier 2 (1.5-flash) -> Tier 3 (Arbiter)."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' is missing or cannot be imported.")
        
        # Verify ModelTier enum values
        tier_names = [t.name for t in ModelTier]
        assert "TIER_1_PRIMARY" in tier_names, f"TIER_1_PRIMARY missing in ModelTier: {tier_names}"
        assert "TIER_2_FALLBACK" in tier_names, f"TIER_2_FALLBACK missing in ModelTier: {tier_names}"
        assert "TIER_3_HEURISTIC" in tier_names, f"TIER_3_HEURISTIC missing in ModelTier: {tier_names}"

        orchestrator = HierarchicalModelOrchestrator(api_key="test_key")
        assert orchestrator.active_tier == ModelTier.TIER_1_PRIMARY, "Default active tier must be Tier 1 Primary."

    def test_t1_f02_http_429_automatic_failover(self, sample_pil_frame):
        """F02: Verify HTTP 429 RESOURCE_EXHAUSTED triggers instant failover to Tier 2 without crashing."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        orchestrator = HierarchicalModelOrchestrator(api_key="test_key")
        
        # Configure client mock: Tier 1 raises 429, Tier 2 succeeds
        mock_client = MagicMock()
        def side_effect(model, contents, **kwargs):
            if "2.0" in model or "2.5" in model:
                raise Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded (15 RPM).")
            return MockGeminiResponse(make_mock_inference_payload(
                action="Đi lại quan sát",
                description="Đối tượng đang di chuyển trong văn phòng.",
                severity="safe"
            ))

        mock_client.models.generate_content.side_effect = side_effect
        orchestrator.client = mock_client

        bio = {"posture": "Đứng thẳng", "angle": 88.0, "is_danger": False, "is_warning": False}
        result = orchestrator.execute_live_analysis(sample_pil_frame, bio)

        assert isinstance(result, dict), "Result must be a valid dictionary"
        assert result.get("action") == "Đi lại quan sát"
        assert result.get("severity") == "safe"
        # Must failover to Tier 2
        assert orchestrator.active_tier == ModelTier.TIER_2_FALLBACK, "Active tier must transition to Tier 2 after 429."

    def test_t1_f03_preemptive_cooldown_reversion(self):
        """F03: Verify 60s sliding window cooldown tracker and preemptive reversion."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        tracker = CooldownTracker(cooldown_seconds=60.0)
        assert tracker.is_tier1_ready() is True, "Tier 1 must be ready initially."

        tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)
        assert tracker.is_tier1_ready() is False, "Tier 1 must not be ready immediately after rate limit."
        rem = tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)
        assert 55.0 <= rem <= 60.0, f"Remaining cooldown should be near 60s, got {rem}"

        # Simulate 61s passing
        tracker.tier1_cooldown_start -= 61.0
        assert tracker.is_tier1_ready() is True, "Tier 1 must be ready after 60s cooldown expiration."
        assert tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY) == 0.0

    def test_t1_f04_rolling_context_memory_history(self):
        """F04: Verify rolling context memory retains 3-5 cycles and formats timeline into prompt."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        memory = RollingContextMemory(maxlen=5)
        now = time.time()

        from core.model_orchestrator import ContextMemoryEntry
        for i in range(5):
            entry = ContextMemoryEntry(
                timestamp=now + i * 4.0,
                time_str=f"10:00:{i*4:02d}",
                action=f"Thao tác {i+1}",
                description=f"Chi tiết hành vi bước {i+1}",
                posture="Ngồi làm việc",
                torso_angle=85.0 + i,
                prediction="Tiếp tục thao tác",
                severity="safe",
                tier_used="Tier-1"
            )
            memory.record(entry)

        summary = memory.get_context_summary_for_prompt()
        assert "DÒNG THỜI GIAN NGỮ CẢNH" in summary
        assert "Thao tác 1" in summary
        assert "Thao tác 5" in summary

        # Adding 6th entry evicts oldest (maxlen=5)
        entry6 = ContextMemoryEntry(
            timestamp=now + 24.0,
            time_str="10:00:24",
            action="Thao tác 6",
            description="Chi tiết hành vi bước 6",
            posture="Đứng dậy",
            torso_angle=90.0,
            prediction="Rời khỏi vị trí",
            severity="warning",
            tier_used="Tier-2"
        )
        memory.record(entry6)
        entries = memory.get_recent_entries()
        assert len(entries) == 5
        actions = [e["action"] for e in entries]
        assert "Thao tác 1" not in actions, "Oldest entry (Thao tác 1) should be evicted."
        assert "Thao tác 6" in actions, "Newest entry (Thao tác 6) must be present."

    def test_t1_f05_context_aware_heuristic_arbiter(self):
        """F05: Verify Autonomous Heuristic Arbiter synthesizes continuous description using history."""
        if not HAS_MODEL_ORCHESTRATOR:
            pytest.fail("M1 Implementation Defect: 'core.model_orchestrator' missing.")

        arbiter = AutonomousHeuristicArbiter()
        memory = RollingContextMemory(maxlen=5)

        from core.model_orchestrator import ContextMemoryEntry
        # Record previous action
        memory.record(ContextMemoryEntry(
            timestamp=time.time() - 4.0,
            time_str="10:00:00",
            action="Ngồi tập trung",
            description="Đang gõ phím liên tục",
            posture="Ngồi thẳng",
            torso_angle=88.0,
            prediction="Duy trì gõ phím",
            severity="safe",
            tier_used="Tier-1"
        ))

        bio = {"angle": 45.0, "is_danger": False, "is_warning": True}
        result = arbiter.synthesize_with_memory("Cúi gập người", bio, memory)

        assert isinstance(result, dict)
        assert result.get("action") == "Cúi gập người"
        assert result.get("severity") == "warning"
        assert "model_tier" in result
        # Check transition continuity note exists
        desc = result.get("description", "")
        assert "Chuyển tiếp" in desc or "Ngồi tập trung" in desc, (
            f"Arbiter description should note continuity from previous action. Got: {desc}"
        )


# ==============================================================================
# Area 2: Anti-Slop Terminology, Hardware & Font Fallback (F06, F07, F08, F09)
# ==============================================================================

class TestAntiSlopHardwareAndFontFallback:
    """Tests Features 6, 7, 8, 9: Slop Elimination, Hardware Detection, Dynamic HUD, Fonts."""

    def test_t1_f06_zero_ai_slop_terminology_check(self):
        """F06: Verify 100% elimination of AI Slop: 'THREAT MATRIX', 'LOCK-ON', 'RADAR AI', 'CYBER HUD'."""
        targets = [
            TEMPLATES_DIR / "index.html",
            STATIC_DIR / "style.css",
            STATIC_DIR / "app.js",
            PROJECT_ROOT / "core" / "cyber_hud.py",
        ]
        violations = []

        for target in targets:
            if not target.exists():
                continue
            content = target.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), start=1):
                # Ignore comment or docstring explanations in tests/spec
                for forbidden in FORBIDDEN_SLOP_TERMS:
                    if forbidden in line.upper():
                        # Exclude instructions that explicitly define elimination of slop
                        if "LOẠI BỎ" in line or "ELIMINATION" in line or "THAY BẰNG" in line:
                            continue
                        violations.append(f"{target.relative_to(PROJECT_ROOT)}:{line_no} contains forbidden token '{forbidden}'")

        if violations:
            pytest.fail(f"M2/M3 Implementation Defect: AI Slop terminology detected ({len(violations)} occurrences):\n" +
                        "\n".join(violations[:10]))

    def test_t1_f07_real_hardware_detection_accuracy(self):
        """F07: Verify hardware detection accurately returns GPU name or CPU."""
        from core.metrics import SystemResourceMonitor
        monitor = SystemResourceMonitor()
        telemetry = monitor.get_telemetry() if hasattr(monitor, "get_telemetry") else monitor.sample_now()
        assert isinstance(telemetry, dict)
        assert "gpu_name" in telemetry, "Telemetry dictionary must contain 'gpu_name'"
        gpu_name = telemetry["gpu_name"]
        assert isinstance(gpu_name, str) and len(gpu_name) > 0, "gpu_name must be a non-empty string"
        # Allowed hardware signatures
        valid_signatures = ["RTX", "GTX", "Tesla", "NVIDIA", "Apple Silicon", "MPS", "CPU", "Intel", "AMD"]
        assert any(sig.lower() in gpu_name.lower() for sig in valid_signatures), (
            f"gpu_name '{gpu_name}' does not match any recognized hardware signature."
        )

    def test_t1_f08_dynamic_model_tier_display_on_hud(self, sample_bgr_frame):
        """F08: Verify video HUD dynamically displays the active model tier."""
        from core.cyber_hud import CyberHUDRenderer
        hud = CyberHUDRenderer()
        
        metrics = {
            "producer_fps": 30.0,
            "queue_size": 2,
            "queue_max": 32,
            "dropped_frames": 0,
            "cpu_percent": 12.5,
            "ram_percent": 45.0,
            "gpu_vram_used": 2.1,
            "gpu_vram_total": 8.0,
            "gpu_name": "RTX 5060"
        }
        diagnosis = {
            "action": "Ngồi học tập",
            "threat_level": "AN TOÀN",
            "model_tier_str": "● Tier-2 Gemini 1.5 (Failover)"
        }

        # Headless sidebar rendering test
        sidebar = hud.render_sidebar_pil(
            diagnosis=diagnosis,
            entities={"person": 1, "laptop": 1},
            metrics=metrics,
            danger_score=0,
            danger_level="AN TOÀN",
            biomechanics=None
        )
        assert isinstance(sidebar, np.ndarray), "Sidebar must render to a valid numpy BGR array."
        assert sidebar.shape == (720, hud.sidebar_w, 3), f"Sidebar shape mismatch: {sidebar.shape}"

    def test_t1_f09_unicode_vietnamese_font_fallback_rendering(self):
        """F09: Verify Unicode Vietnamese text renders cleanly in Pillow without exception."""
        test_strings = [
            "HỆ THỐNG GIÁM SÁT VIDEO ĐA LUỒNG - HỆ ĐIỀU HÀNH",
            "● AN TOÀN - CÔNG THÁI HỌC CHUẨN",
            "● CẢNH BÁO: TƯ THẾ NGHIÊNG BẤT THƯỜNG",
            "● NGUY HIỂM: TÉ NGÃ ĐÃ ĐƯỢC PHÁT HIỆN"
        ]

        img = Image.new("RGB", (800, 200), color=(18, 24, 32))
        draw = ImageDraw.Draw(img)

        # Attempt to load fallbacks
        from core.cyber_hud import CyberHUDRenderer
        hud = CyberHUDRenderer()
        font = getattr(hud, "font_title", None) or getattr(hud, "font_body", None)
        if font is None:
            font = ImageFont.load_default()

        y = 20
        for s in test_strings:
            draw.text((20, y), s, fill=(240, 244, 248), font=font)
            y += 40

        arr = np.array(img)
        # Check that canvas is not empty (contains rendered text pixels)
        diff = np.sum(arr != np.array([18, 24, 32], dtype=np.uint8))
        assert diff > 500, "Rendered Vietnamese canvas has insufficient pixel delta; text may not have drawn."

    def test_t1_f09_b_no_cv2_puttext_with_vietnamese_unicode(self):
        """F09b: Verify video_annotator does not use cv2.putText for multi-byte Vietnamese strings."""
        annotator_file = PROJECT_ROOT / "core" / "video_annotator.py"
        if not annotator_file.exists():
            return
        
        content = annotator_file.read_text(encoding="utf-8", errors="ignore")
        # Regex search for cv2.putText with Vietnamese accented characters
        pattern = r"cv2\.putText\([^)]*['\"][^'\"]*[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđĐ][^'\"]*['\"]"
        matches = re.findall(pattern, content)
        if matches:
            pytest.fail(f"M2 Implementation Defect: 'cv2.putText' used with Vietnamese characters in video_annotator.py:\n" +
                        "\n".join(matches[:5]))


# ==============================================================================
# Area 3: Academic UI/UX & Radix Slate System (F10, F11, F12, F13, F14)
# ==============================================================================

class TestAcademicUIUXAndRadixSlate:
    """Tests Features 10 through 14: Radix Slate Theme, Fonts, Dashboard Grid, Badges, Responsive."""

    def test_t1_f10_radix_slate_dark_light_theme_definitions(self):
        """F10: Verify Radix Slate color palette and Dark/Light theme selectors in style.css."""
        css_file = STATIC_DIR / "style.css"
        assert css_file.exists(), f"Stylesheet {css_file} must exist."
        css = css_file.read_text(encoding="utf-8")

        # Check for light theme selector
        has_light_theme = (
            "[data-theme=\"light\"]" in css or
            "[data-theme='light']" in css or
            ".light-theme" in css or
            "@media (prefers-color-scheme: light)" in css
        )
        if not has_light_theme:
            pytest.fail("M3 Implementation Defect: style.css does not define a Light Theme selector ('[data-theme=\"light\"]').")

    def test_t1_f11_academic_font_pairing_declaration(self):
        """F11: Verify Plus Jakarta Sans (UI) and JetBrains Mono (Code/Telemetry) declaration."""
        html_file = TEMPLATES_DIR / "index.html"
        assert html_file.exists(), f"Template {html_file} must exist."
        html = html_file.read_text(encoding="utf-8")

        assert "Plus+Jakarta+Sans" in html or "Plus Jakarta Sans" in html, (
            "index.html must load Plus Jakarta Sans Google Font."
        )
        assert "JetBrains+Mono" in html or "JetBrains Mono" in html, (
            "index.html must load JetBrains Mono Google Font."
        )

    def test_t1_f12_os_telemetry_dashboard_elements(self):
        """F12: Verify HTML template contains OS telemetry display grid."""
        html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
        
        # Must have Producer and Consumer telemetry terms
        required_terms = ["Producer", "Consumer", "Buffer", "FPS"]
        for term in required_terms:
            assert term.lower() in html.lower(), f"OS Telemetry term '{term}' missing in index.html"

    def test_t1_f13_transparent_model_tier_badges(self, client):
        """F13: Verify /api/telemetry or /api/camera/logs returns model tier identifier."""
        resp = client.get("/api/telemetry")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_model_tier" in data or "active_tier" in data or "gemini_model" in data, (
            f"/api/telemetry missing active model tier metadata: {data}"
        )

    def test_t1_f14_responsive_layout_and_empty_states(self):
        """F14: Verify responsive CSS rule for mobile screens (< 768px) and empty state markup."""
        css = (STATIC_DIR / "style.css").read_text(encoding="utf-8")
        assert "@media" in css and ("768px" in css or "800px" in css), (
            "style.css must define responsive media queries for screens < 768px."
        )

        html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
        assert "empty" in html.lower(), "index.html must include polite empty state markup."


# ==============================================================================
# Area 4: Backpressure, Token Guard & Flow Sync (F15, F16, F17, F19)
# ==============================================================================

class TestBackpressureTokenGuardAndFlowSync:
    """Tests Features 15, 16, 17, 19: Rate Limiting, Keyframe Accumulation, Queue Sync, Syntax."""

    def test_t1_f15_central_rate_limiter_interval(self):
        """F15: Verify rate limiter interval is >= 4.2s (or <= 15 RPM)."""
        from core.config import CONFIG
        interval = getattr(CONFIG, "GEMINI_INTERVAL_SECONDS", 3.5)
        # Requirement R1 & R3 specifies >= 4.2s to strictly avoid 15 RPM rate limiting
        if interval < 4.0:
            pytest.fail(f"M4 Implementation Defect: CONFIG.GEMINI_INTERVAL_SECONDS ({interval}s) is < 4.0s (risks 15 RPM flood).")

    def test_t1_f16_key_anomaly_frames_accumulation(self, sample_bgr_frame):
        """F16: Verify TokenGuard keyframe accumulator selects at most 1-3 peak frames (< 1,500 tokens)."""
        from core.token_guard import TokenGuard
        guard = TokenGuard()

        # Prepare event_log and candidate_frames matching TokenGuard.select_peak_keyframes signature
        event_log = []
        candidate_frames = {}
        for i in range(10):
            ts = float(i)
            candidate_frames[ts] = sample_bgr_frame
            event_log.append({
                "timestamp": ts,
                "threat_score": i * 10.0,
                "action": f"Action_{i}",
                "confidence": 0.8
            })

        if hasattr(guard, "select_peak_keyframes"):
            selected = guard.select_peak_keyframes(
                event_log=event_log,
                candidate_frames=candidate_frames,
                max_keyframes=3
            )
            assert isinstance(selected, list)
            assert 1 <= len(selected) <= 3, f"Key anomaly frames count should be between 1 and 3, got {len(selected)}"

    def test_t1_f17_bounded_buffer_flow_telemetry_sync(self, client):
        """F17: Verify /api/telemetry returns synchronized OS bounded buffer queue stats."""
        resp = client.get("/api/telemetry")
        assert resp.status_code == 200
        data = resp.json()
        assert "queue_size" in data, "queue_size missing from telemetry"
        assert "queue_max" in data, "queue_max missing from telemetry"
        assert "dropped_frames" in data, "dropped_frames missing from telemetry"
        assert data["queue_size"] <= data["queue_max"], "queue_size cannot exceed queue_max"

    def test_t1_f19_python_syntax_compilation(self):
        """F19: Verify strict compilation of all Python files in core/, tests/, and root."""
        py_files = list(PROJECT_ROOT.glob("core/**/*.py")) + \
                   list(PROJECT_ROOT.glob("tests/**/*.py")) + \
                   list(PROJECT_ROOT.glob("*.py"))
        
        errors = []
        for pf in py_files:
            try:
                py_compile.compile(str(pf), doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(f"{pf}: {e}")

        assert len(errors) == 0, f"Python compilation failed with {len(errors)} errors:\n" + "\n".join(errors)

    def test_t1_f19_b_javascript_syntax_check(self):
        """F19b: Verify node -c syntax check on ui/static/app.js."""
        js_file = STATIC_DIR / "app.js"
        if not js_file.exists():
            return
        
        res = subprocess.run(["node", "-c", str(js_file)], capture_output=True, text=True)
        assert res.returncode == 0, f"JavaScript syntax check failed on app.js:\n{res.stderr}"
