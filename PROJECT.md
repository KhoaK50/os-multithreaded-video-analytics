# Project: OS Multithreaded Video Analytics Upgrade

## Architecture
Hệ thống Giám sát Video Đa Luồng chuẩn học thuật Hệ Điều Hành với các phân hệ chính:
1. **Producer Thread (`core/capture.py`)**: Thu nhận khung hình 30 FPS từ webcam hoặc video stream, điều tiết lưu lượng qua Hàng đợi Đệm có giới hạn (Bounded Buffer Queue) và thuật toán loại bỏ khung hình (Drop-frame Flow Control).
2. **Consumer Threads (`core/web_server.py`, `core/detector.py`, `core/video_annotator.py`)**:
   - Edge AI Consumer: Chạy mô hình YOLOv8-Pose nhận diện 17 điểm khung xương công thái học và ByteTrack trên GPU/CPU.
   - Cloud AI Consumer / Arbiter: Suy luận thị giác theo chu kỳ qua Bộ Điều Phối Chuyển Đổi Mô Hình Đa Tầng (`core/model_orchestrator.py`).
3. **Hierarchical Model Failover & Memory Engine (`core/model_orchestrator.py`)**:
   - Tier 1: `gemini-2.0-flash` / `gemini-2.5-flash` (Chất lượng thị giác cao nhất).
   - Tier 2: `gemini-1.5-flash` (Dự phòng tốc độ cao khi Tier 1 chạm 429 / Rate Limit).
   - Tier 3: Autonomous Heuristic Arbiter (Hội chẩn tự hành cục bộ có nhận thức ngữ cảnh lịch sử).
   - Cooldown Tracker: Cửa sổ trượt 60 giây và cơ chế tự phục hồi sớm (Preemptive Reversion).
   - Rolling Context Memory: Bộ nhớ đệm trượt 3-5 chu kỳ duy trì tính liên tục tư duy khi chuyển đổi mô hình.
4. **OS Video HUD Renderer (`core/cyber_hud.py`, `core/video_annotator.py`)**:
   - Khung HUD video ghép trực tiếp thông số Hệ Điều Hành: Producer FPS, Consumer state, Bounded Buffer size, Drop frames, Hardware CPU/RAM/VRAM và tên GPU thực tế.
   - Cơ chế font fallback đa nền tảng (Windows / Linux / MacOS) bảo đảm 100% hiển thị tiếng Việt Unicode tròn vành rõ chữ, loại bỏ hoàn toàn `cv2.putText` lỗi dấu.
5. **Academic OS Web Interface (`ui/templates/index.html`, `ui/static/style.css`, `ui/static/app.js`)**:
   - Chuẩn thiết kế Radix Slate (Dark & Light theme có nút chuyển đổi).
   - Phân cấp font Plus Jakarta Sans + JetBrains Mono.
   - Bảng điều khiển viễn trắc HĐH thời gian thực và huy hiệu 3 tầng mô hình minh bạch.
6. **Central Flow & Rate Controller (`core/token_guard.py`, `core/video_annotator.py`)**:
   - Điều tiết lưu lượng giữa luồng Live Camera và CapCut Timeline Video Analysis.
   - Thuật toán tích lũy khung hình sự kiện tiêu biểu (Key Anomaly Frames, tối đa 1-3 ảnh) gửi 1 lần tổng hợp duy nhất (< 1,500 tokens).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Hierarchical Model Tiers (1/2/3) | Phân tầng Tier 1 (gemini-2.0/2.5-flash), Tier 2 (gemini-1.5-flash), Tier 3 (Arbiter) | M1 | ORIGINAL_REQUEST §R1 |
| 2 | HTTP 429 Automatic Failover | Bắt lỗi 429 RESOURCE_EXHAUSTED và chuyển tầng tức thì không gián đoạn luồng | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Preemptive Cooldown Reversion 60s | Bộ đếm 60s sliding window, tự động quay lại Tier 1 ngay khi hết thời gian hồi | M1 | ORIGINAL_REQUEST §R1 |
| 4 | Rolling Context Memory (3-5 cycles) | Lưu trữ và tiêm lịch sử 3-5 chu kỳ trước vào prompt khi chuyển tầng/hồi phục | M1 | ORIGINAL_REQUEST §R1 |
| 5 | Context-Aware Heuristic Arbiter | Bộ hội chẩn tự hành cục bộ có nhận thức chuyển tiếp động học từ lịch sử ngữ cảnh | M1 | ORIGINAL_REQUEST §R1 |
| 6 | 100% AI Slop Terminology Elimination | Xóa sạch THREAT MATRIX, LOCK-ON, RADAR AI, CYBER HUD, thay bằng thuật ngữ HĐH | M2, M3 | ORIGINAL_REQUEST §R2 |
| 7 | Real Hardware Detection on HUD | Nhận diện chính xác Tesla T4, RTX 5060, Apple Silicon (MPS), hoặc CPU trên HUD | M2 | ORIGINAL_REQUEST §R2 |
| 8 | Dynamic Model Tier Display on Video HUD | Hiển thị động tầng mô hình đang chạy trên video HUD theo thời gian thực | M2 | ORIGINAL_REQUEST §R2 |
| 9 | Unicode Vietnamese Font Fallback | Cơ chế font fallback đa nền tảng cho Pillow, thay thế cv2.putText tiếng Việt | M2 | ORIGINAL_REQUEST §R2 |
| 10 | Radix Slate Design System (Dark/Light) | Bảng màu Radix Slate chuẩn học thuật, hỗ trợ cả Dark và Light theme kèm nút toggle | M3 | ORIGINAL_REQUEST §R2 |
| 11 | Academic Font Pairing | Plus Jakarta Sans cho UI/tiêu đề, JetBrains Mono cho viễn trắc/mã số | M3 | ORIGINAL_REQUEST §R2 |
| 12 | OS Telemetry Dashboard Grid | Grid hiển thị Producer, Consumer, Bounded Buffer, Drop Frames, CPU/RAM/VRAM | M3 | ORIGINAL_REQUEST §R2 |
| 13 | Transparent Model Tier Badges on UI | Huy hiệu 3 màu: Tier-1 Gemini 2.5, Tier-2 Gemini 1.5 Failover, Tier-3 AI Tự Hành | M3 | ORIGINAL_REQUEST §R2 |
| 14 | Responsive UI (<768px) & Empty States | Bố cục co giãn chuẩn mobile, thanh công cụ responsive, empty states lịch sự | M3 | ORIGINAL_REQUEST §R2 |
| 15 | Central Backpressure & Rate Limiter | Khống chế nhịp độ gọi API >= 4.2s giữa Live Camera và CapCut Timeline Analysis | M4 | ORIGINAL_REQUEST §R3 |
| 16 | Key Anomaly Frames Accumulation | Gom tối đa 1-3 khung hình sự kiện tiêu biểu gửi 1 lần tổng hợp duy nhất (<1500 tokens) | M4 | ORIGINAL_REQUEST §R3 |
| 17 | Bounded Buffer Flow Telemetry Sync | Kết nối hàng đợi Producer-Consumer thực tế vào luồng viễn trắc hệ thống | M4 | ORIGINAL_REQUEST §R3 |
| 18 | 100% E2E Test Suite Pass | Toàn bộ các ca kiểm thử E2E (Tiers 1-4) vượt qua kiểm chứng nghiêm ngặt | M5 | ORIGINAL_REQUEST §AC |
| 19 | Strict Syntax Verification | Vượt qua python -m py_compile và node -c tuyệt đối không có lỗi | M5 | ORIGINAL_REQUEST §AC |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Backend Hierarchical Failover & Rolling Context | `core/model_orchestrator.py`, `core/config.py`, `core/web_server.py`, `core/gemini_analyzer.py`, `tests/test_hierarchical_failover.py` | none | **DONE** (15/15 unit tests, 8/8 stress tests pass, CLEAN audit) |
| M2 | Video HUD, Hardware Detection & Font Fallback | `core/cyber_hud.py`, `core/video_annotator.py`, `core/metrics.py`, `tests/test_hud_rendering.py` | M1 contracts | **DONE** (22/22 unit tests, 4032 frame slop sweep pass, 105.9 FPS, CLEAN audit) |
| M3 | Academic OS Web UI/UX & Radix Slate Theme | `ui/templates/index.html`, `ui/static/style.css`, `ui/static/app.js` | M1, M2 | PLANNED |
| M4 | Backpressure, Flow Control & CapCut Timeline | `core/token_guard.py`, `core/video_annotator.py`, `core/capture.py`, `core/web_server.py` | M1, M2 | PLANNED |
| M5 | E2E Acceptance, Adversarial Hardening & Syntax Pass | Full system E2E tests (Tiers 1-4), Tier 5 adversarial tests, python -m py_compile, node -c | M1, M2, M3, M4 | PLANNED |

## Interface Contracts
### `core/model_orchestrator.py` ↔ `core/web_server.py`
- `HierarchicalModelOrchestrator.execute_live_analysis(frame_img: Image, bio: dict) -> dict`:
  - Trả về: `{"action": str, "description": str, "prediction_next_4s": str, "severity": str, "model_tier": str}`
  - Không ném ngoại lệ 429 ra ngoài; tự động failover sang Tier 2 hoặc Tier 3.
- `HierarchicalModelOrchestrator.get_active_tier_info() -> dict`:
  - Trả về: `{"active_tier": str, "tier_name": str, "tier_badge": str, "is_cooldown": bool, "cooldown_remaining": float}`
- `HierarchicalModelOrchestrator.acquire_api_permission(priority: str = "normal") -> bool`:
  - Điều phối nhịp độ >= 4.2s giữa Live Stream và Video Upload.

### `core/web_server.py` ↔ `ui/static/app.js`
- Endpoint `/api/telemetry` GET:
  - Trả về JSON: `{producer_running: bool, producer_fps: float, consumer_status: str, queue_size: int, queue_max: int, dropped_frames: int, drop_rate_pct: float, cpu_percent: float, ram_percent: float, gpu_vram_used: float, gpu_vram_total: float, gpu_name: str, active_model_tier: str, active_tier_name: str, cooldown_remaining: float}`
- Endpoint `/api/camera/logs` GET:
  - Mỗi bản ghi bổ sung trường: `model_tier: str` (ví dụ: `"tier_1"`, `"tier_2"`, `"tier_3"`).

### `core/metrics.py` ↔ `core/cyber_hud.py`
- `SystemResourceMonitor.get_telemetry() -> dict`:
  - Bao gồm `gpu_name`: Tên thiết bị rút gọn ("RTX 5060", "Tesla T4", "Apple Silicon (MPS)", "CPU").
- `CyberHUDRenderer.render_sidebar_pil(..., metrics: dict, diagnosis: dict)`:
  - `metrics` chứa `gpu_name`, `queue_size`, `queue_max`, `dropped_frames`.
  - `diagnosis` chứa `model_tier_str` (chuỗi hiển thị động thay vì hardcode).

## Code Layout
- `core/model_orchestrator.py`: Lớp điều phối phân tầng, CooldownTracker, RollingContextMemory, HeuristicArbiter.
- `core/config.py`: Cấu hình mô hình, hạn mức thời gian và đường dẫn font.
- `core/cyber_hud.py`: Lớp vẽ HUD video (alias `SurveillanceHUDRenderer`).
- `core/video_annotator.py`: Động cơ xử lý video offline, dán nhãn Unicode Pillow, tích lũy key anomaly frames.
- `core/token_guard.py`: Lọc keyframe đỉnh điểm, gom cụm request dưới 1,500 tokens.
- `core/web_server.py`: FastAPI server, quản lý luồng camera và các endpoint viễn trắc.
- `ui/templates/index.html`: Giao diện web chuẩn học thuật Hệ Điều Hành.
- `ui/static/style.css`: Hệ thống thiết kế Radix Slate Dark & Light.
- `ui/static/app.js`: Điều khiển viễn trắc client, chuyển đổi theme, render nhật ký và timeline.
- `tests/test_hierarchical_failover.py`: Bộ unit tests cho cơ chế failover, cooldown và rolling context.
- `tests/e2e/`: Bộ E2E opaque-box tests (Tiers 1-4).
