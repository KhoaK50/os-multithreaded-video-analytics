# TEST INFRASTRUCTURE SPECIFICATION (TEST_INFRA.md)
**Project**: OS Multithreaded Video Analytics Upgrade  
**Academic Module**: Operating Systems (Hệ Điều Hành)  
**Integrity Mode**: Development & Opaque-Box E2E Testing  
**Document Version**: 1.0.0  
**Author**: E2E Testing Architect  

---

## 1. Test Philosophy: Opaque-Box & Requirement-Driven

The End-to-End (E2E) testing framework for the OS Multithreaded Video Analytics system operates on strict **opaque-box principles**:
1. **Behavioral & Contract Verification**: Tests interact exclusively through external interfaces:
   - HTTP/REST Endpoints via FastAPI `TestClient` (`/api/telemetry`, `/api/camera/logs`, `/api/stream/live`, `/api/chat`, `/api/video/process`).
   - Module public contracts defined in `PROJECT.md` (§ Interface Contracts).
   - Rendered video HUD image buffers (PIL Image and NumPy BGR arrays) evaluated headlessly.
   - Static asset compliance (CSS variables, HTML DOM structure, JS event handlers) inspected without reliance on browser instances.
2. **Authoritative Output Derivation**:
   - Every expected value is directly derived from `ORIGINAL_REQUEST.md` (Requirements R1, R2, R3 and Acceptance Criteria) and `PROJECT.md` (19 features and interface contracts).
   - No tests assert arbitrary implementation details; tests verify specified state transitions, exact terminology replacement, rate limiting thresholds (>= 4.2s, 60s cooldown), and data schema guarantees.
3. **100% Deterministic & Isolated Execution**:
   - External Google Gemini API calls are mocked using Google GenAI SDK v2 (`google-genai` v2.19.0) response structures.
   - Network timeouts, HTTP 429 `RESOURCE_EXHAUSTED` errors, and quota floods are simulated deterministically.
   - Tests do not require live internet access or real Google API keys.
4. **Zero GUI Dependency (Headless Execution)**:
   - OpenCV and Pillow rendering operations execute purely in memory without opening X11 or Win32 windows (`cv2.imshow` is never invoked).
5. **Fail-Fast & Complete Diagnostic Tracing**:
   - Comprehensive assertions provide explicit diagnostic diffs upon failure.

---

## 2. Feature Inventory Mapping (19 Features)

| Feature # | Feature Name | Mapped Test File | Test Tiers | Authoritative Source |
|---|---|---|---|---|
| **F01** | Hierarchical Model Tiers (1/2/3) | `tests/e2e/test_tier1_feature_coverage.py` | Tier 1, Tier 3 | `PROJECT.md` §27, `ORIGINAL_REQUEST.md` §14-18 |
| **F02** | HTTP 429 Automatic Failover | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier2_boundary_corner_cases.py` | Tier 1, Tier 2, Tier 3 | `PROJECT.md` §30, `ORIGINAL_REQUEST.md` §19-20 |
| **F03** | Preemptive Cooldown Reversion 60s | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier2_boundary_corner_cases.py` | Tier 1, Tier 2, Tier 4 | `PROJECT.md` §31, `ORIGINAL_REQUEST.md` §21-23 |
| **F04** | Rolling Context Memory (3-5 cycles) | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier4_real_world_scenarios.py` | Tier 1, Tier 4 | `PROJECT.md` §32, `ORIGINAL_REQUEST.md` §24-26 |
| **F05** | Context-Aware Heuristic Arbiter | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier2_boundary_corner_cases.py` | Tier 1, Tier 2 | `PROJECT.md` §33, `ORIGINAL_REQUEST.md` §18, 58 |
| **F06** | 100% AI Slop Terminology Elimination | `tests/e2e/test_tier1_feature_coverage.py` | Tier 1 | `PROJECT.md` §34, `ORIGINAL_REQUEST.md` §28-37, 61-62 |
| **F07** | Real Hardware Detection on HUD | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier3_cross_feature_interactions.py` | Tier 1, Tier 3 | `PROJECT.md` §35, `ORIGINAL_REQUEST.md` §45 |
| **F08** | Dynamic Model Tier Display on Video HUD | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier3_cross_feature_interactions.py` | Tier 1, Tier 3 | `PROJECT.md` §36, `ORIGINAL_REQUEST.md` §45, 65 |
| **F09** | Unicode Vietnamese Font Fallback | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier2_boundary_corner_cases.py` | Tier 1, Tier 2 | `PROJECT.md` §37, `ORIGINAL_REQUEST.md` §46, 64 |
| **F10** | Radix Slate Design System (Dark/Light) | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier3_cross_feature_interactions.py` | Tier 1, Tier 3 | `PROJECT.md` §38, `ORIGINAL_REQUEST.md` §39 |
| **F11** | Academic Font Pairing | `tests/e2e/test_tier1_feature_coverage.py` | Tier 1 | `PROJECT.md` §39, `ORIGINAL_REQUEST.md` §40 |
| **F12** | OS Telemetry Dashboard Grid | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier3_cross_feature_interactions.py` | Tier 1, Tier 3 | `PROJECT.md` §40, `ORIGINAL_REQUEST.md` §32-36 |
| **F13** | Transparent Model Tier Badges on UI | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier3_cross_feature_interactions.py` | Tier 1, Tier 3 | `PROJECT.md` §41, `ORIGINAL_REQUEST.md` §65 |
| **F14** | Responsive UI (<768px) & Empty States | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier3_cross_feature_interactions.py` | Tier 1, Tier 3 | `PROJECT.md` §42, `ORIGINAL_REQUEST.md` §42-43 |
| **F15** | Central Backpressure & Rate Limiter | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier2_boundary_corner_cases.py` | Tier 1, Tier 2, Tier 4 | `PROJECT.md` §43, `ORIGINAL_REQUEST.md` §48-49 |
| **F16** | Key Anomaly Frames Accumulation | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier4_real_world_scenarios.py` | Tier 1, Tier 4 | `PROJECT.md` §44, `ORIGINAL_REQUEST.md` §50 |
| **F17** | Bounded Buffer Flow Telemetry Sync | `tests/e2e/test_tier1_feature_coverage.py`, `tests/e2e/test_tier3_cross_feature_interactions.py` | Tier 1, Tier 3 | `PROJECT.md` §45, `ORIGINAL_REQUEST.md` §34 |
| **F18** | 100% E2E Test Suite Pass | `tests/e2e/runner.py` | Meta Tier | `PROJECT.md` §46, `ORIGINAL_REQUEST.md` § AC |
| **F19** | Strict Syntax Verification | `tests/e2e/runner.py`, `tests/e2e/test_tier1_feature_coverage.py` | Meta Tier | `PROJECT.md` §47, `ORIGINAL_REQUEST.md` §69 |

---

## 3. Test Architecture & Directory Layout

```
tests/e2e/
├── __init__.py                                 # Package marker
├── conftest.py                                 # Pytest & Unittest fixtures, mock factories, helper assertions
├── test_tier1_feature_coverage.py              # Tier 1: Functional coverage across 19 features (>=5 per area)
├── test_tier2_boundary_corner_cases.py         # Tier 2: Boundary, flood, cooldown jitter, font fallback stress
├── test_tier3_cross_feature_interactions.py     # Tier 3: Pairwise concurrent interactions & system integration
├── test_tier4_real_world_scenarios.py          # Tier 4: Realistic user workflows (CapCut, rate limits, telemetry)
└── runner.py                                   # Standalone master runner (supports unittest & pytest CLI)
```

---

## 4. 4-Tier Methodology Details

### Tier 1: Feature Coverage (>=5 test cases per functional area)
1. **Area 1: Hierarchical Failover & Model Orchestration (F01, F02, F03, F04, F05)**:
   - `test_t1_f01_hierarchical_tiers_priority`: Verify default selection order: Tier 1 -> Tier 2 -> Tier 3.
   - `test_t1_f02_http_429_immediate_failover`: Verify HTTP 429 triggers instant failover without thread interruption.
   - `test_t1_f03_preemptive_cooldown_timer`: Verify 60s cooldown countdown computation.
   - `test_t1_f04_rolling_context_memory_history`: Verify 3-5 cycles of event history are recorded and formatted.
   - `test_t1_f05_heuristic_arbiter_rich_context`: Verify Tier 3 Arbiter synthesizes continuous descriptions using past posture data.
2. **Area 2: Anti-Slop Terminology & Hardware/Font HUD (F06, F07, F08, F09)**:
   - `test_t1_f06_zero_ai_slop_in_codebase`: Scan templates, CSS, JS, Python HUD for forbidden sci-fi tokens.
   - `test_t1_f07_real_hardware_detection_hud`: Verify accurate GPU/CPU detection (Tesla T4, RTX, MPS, CPU).
   - `test_t1_f08_dynamic_model_tier_display_hud`: Verify HUD dynamically reflects current active tier badge.
   - `test_t1_f09_vietnamese_font_fallback_rendering`: Verify Vietnamese Unicode text ("HỆ ĐIỀU HÀNH", "AN TOÀN") renders without glyph boxes or '?' replacement.
   - `test_t1_f09_b_pillow_unicode_over_cv2_puttext`: Verify absence of unescaped `cv2.putText` with multi-byte Vietnamese chars.
3. **Area 3: Academic UI/UX & Radix Slate System (F10, F11, F12, F13, F14)**:
   - `test_t1_f10_radix_slate_dark_light_theme_definitions`: Verify Radix Slate color variables exist for both dark and light modes.
   - `test_t1_f11_academic_font_pairing_declaration`: Verify Plus Jakarta Sans (UI) and JetBrains Mono (Telemetry/Code) linkage and CSS rules.
   - `test_t1_f12_os_telemetry_dashboard_elements`: Verify DOM elements for Producer FPS, Consumer state, Bounded Buffer, Drop Frames, CPU/RAM/VRAM exist in template.
   - `test_t1_f13_transparent_model_tier_badges`: Verify badge elements for Tier-1, Tier-2, and Tier-3 exist with correct classes.
   - `test_t1_f14_responsive_layout_and_empty_states`: Verify media queries for `<768px` and structured empty state markup.
4. **Area 4: Backpressure, Token Guard & Flow Sync (F15, F16, F17, F19)**:
   - `test_t1_f15_central_rate_limiter_interval`: Verify minimum delay of >= 4.2s is enforced between API requests.
   - `test_t1_f16_key_anomaly_frames_accumulation`: Verify maximum 1-3 anomaly frames accumulated for single request (<1500 tokens).
   - `test_t1_f17_bounded_buffer_telemetry_sync`: Verify `/api/telemetry` reports actual queue size and dropped frames.
   - `test_t1_f19_python_syntax_compilation`: Verify all Python files in `core/`, `tests/`, `main.py` compile with `py_compile`.
   - `test_t1_f19_b_javascript_syntax_check`: Verify `ui/static/app.js` passes Node syntax check (`node -c`).

### Tier 2: Boundary & Corner Cases (>=5 test cases per functional area)
1. **Area 1: Failover Timing & Flood Boundaries**:
   - `test_t2_cooldown_threshold_59s_no_reversion`: At 59.0s elapsed, Tier 1 is still in cooldown; system stays on Tier 2.
   - `test_t2_cooldown_threshold_60s_exact_boundary`: At exactly 60.0s elapsed, Tier 1 cooldown expires; system allows reversion.
   - `test_t2_cooldown_threshold_61s_reversion_confirmed`: At 61.0s elapsed, next inference preemptively reverts to Tier 1.
   - `test_t2_simultaneous_429_flood_burst`: Rapid burst of 10 consecutive 429 errors does not crash server or trigger infinite loops; safely cascades to Tier 3.
   - `test_t2_empty_rolling_context_on_startup`: Cycle 0 with zero prior history generates valid initial prompt without exception.
2. **Area 2: Media, Font & Buffer Boundaries**:
   - `test_t2_missing_all_system_fonts_fallback`: When primary TrueType font files are missing, fallback chain resolves without crash.
   - `test_t2_empty_or_corrupt_frame_image`: Passing invalid image dimensions (0x0 or corrupted bytes) handles gracefully with fallback error log.
   - `test_t2_zero_person_detected_in_video_segment`: Timeline processing on a clip with 0 detected people returns valid neutral OS telemetry report.
   - `test_t2_extreme_bounded_buffer_saturation`: Buffer capacity reached (`queue_size == queue_max`); verifies drop-frame flow control increments `dropped_frames` counter.
   - `test_t2_capcut_timeline_trimmer_zero_duration`: Start time equal to end time (0 duration slice) returns 400 Bad Request or validation error instead of processing indefinitely.

### Tier 3: Cross-Feature Interactions
1. `test_t3_live_failover_during_video_upload_start`: Live camera triggers 429 failover while video upload begins; Rate Limiter queues video request until live failover stabilizes.
2. `test_t3_theme_toggle_with_active_camera_stream`: Toggling theme (`data-theme="light"` / `dark`) while `/api/stream/live` is streaming maintains consistent contrast without breaking video MJPEG feed.
3. `test_t3_mobile_viewport_with_high_rate_telemetry`: Simulating `<768px` viewport CSS rules while `/api/telemetry` pushes rapid metrics maintains responsive layout grid without element clipping.
4. `test_t3_bounded_buffer_drop_rate_sync_with_video_hud`: Artificial consumer bottleneck triggers frame drops; verify HUD sidebar and `/api/telemetry` report identical drop numbers.
5. `test_t3_rolling_context_injected_across_tier_transitions`: Tier 1 logs 3 cycles -> Tier 1 hits 429 -> Tier 2 receives full 3-cycle summary in prompt -> Tier 2 logs 2 cycles -> Tier 1 recovers -> Tier 1 receives combined 5-cycle history.

### Tier 4: Real-World Scenarios
1. `test_t4_capcut_timeline_workflow_with_safety_checks`:
   - Step 1: User specifies CapCut timeline slice (e.g. 00:01 to 00:06).
   - Step 2: System extracts frames, runs YOLOv8-pose edge inference.
   - Step 3: Anomaly keyframe accumulator picks peak frames (<= 3).
   - Step 4: TokenGuard requests single synthesis report with token limit < 1500.
   - Step 5: VideoAnnotator creates labeled H.264 video with Unicode Vietnamese HUD.
   - Step 6: Verifies output video exists, response JSON matches academic schema.
2. `test_t4_simulated_15rpm_rate_limiting_with_continuous_telemetry`:
   - Simulates continuous camera execution over 90 seconds.
   - Rate limit enforces >= 4.2s cadence.
   - At second 15, Tier 1 is flooded with 429; failover to Tier 2 occurs immediately.
   - At second 76 (61s after 429), preemptive reversion to Tier 1 occurs seamlessly.
   - Telemetry endpoint continuously reports accurate `active_model_tier`, `cooldown_remaining`, and thread metrics throughout the 90s lifecycle.

---

## 5. Test Runner & Invocation Guide

### Standard Invocation
```powershell
# Run the complete E2E test suite using python runner (works in any environment)
python tests/e2e/runner.py

# Run specific tier
python tests/e2e/runner.py --tier 1
python tests/e2e/runner.py --tier 2
python tests/e2e/runner.py --tier 3
python tests/e2e/runner.py --tier 4

# Run via pytest
python -m pytest tests/e2e -v
```

### Output Reporting
`tests/e2e/runner.py` outputs colorized terminal summaries and generates a machine-readable summary:
- Total tests executed, passed, failed, skipped.
- Per-tier breakdown.
- Feature coverage checklist validation.
