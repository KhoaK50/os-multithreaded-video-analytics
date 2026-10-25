"""
Test Suite: OS Experimental Lab Bench (Phòng Thực Nghiệm Hệ Điều Hành Đối Chứng)
Học phần: Hệ điều hành (2611COMP133202)

Kiểm thử toàn diện 3 kịch bản thực nghiệm đối chứng:
1. Bounded Buffer & Bufferbloat vs Drop-Rate
2. Deadlock & Resource Allocation Graph (RAG) với Watchdog Timer 3.0s
3. Keyframe Memory Eviction Policy (FIFO vs Threat-Priority)
4. Tích hợp FastAPI Endpoints an toàn & trần RAM < 50MB
"""

import time
import pytest
from starlette.testclient import TestClient
from core.os_lab_engine import OSLabEngine, HARD_RAM_CEILING_MB, DEADLOCK_WATCHDOG_TIMEOUT_SEC
from core.web_server import app


class TestOSLabEngineScenarios:
    """Kiểm thử logic lõi của bộ điều phối OSLabEngine."""

    def test_buffer_clamping_and_ram_ceiling(self):
        """Kiểm tra giới hạn dung lượng đệm (2..48) và trần RAM cứng (<50MB)."""
        engine = OSLabEngine()

        # Thử ép giá trị vượt trần
        res_high = engine.configure_buffer_scenario(capacity=999, consumer_delay_ms=500, policy="drop_oldest")
        assert res_high["capacity"] == 48
        assert res_high["consumer_delay_ms"] == 120
        assert res_high["ram_usage_mb"] <= HARD_RAM_CEILING_MB

        # Thử ép giá trị dưới đáy
        res_low = engine.configure_buffer_scenario(capacity=0, consumer_delay_ms=-50, policy="drop_oldest")
        assert res_low["capacity"] == 2
        assert res_low["consumer_delay_ms"] == 0

    def test_buffer_policy_drop_vs_block(self):
        """Kiểm chứng tác động của 2 chính sách: Drop-Oldest vs Block-Producer."""
        engine = OSLabEngine()

        # Kịch bản 1A: Drop-oldest khi Consumer bị chậm 80ms
        res_drop = engine.configure_buffer_scenario(capacity=16, consumer_delay_ms=80, policy="drop_oldest")
        assert res_drop["drop_rate_pct"] > 0.0
        assert res_drop["threat_score"] < 8.8  # Đỉnh xung lực bị giảm do rơi khung hình
        assert "RƠI KHUNG" in res_drop["status_badge"] or "MẤT ĐỈNH" in res_drop["kinetic_fidelity"]

        # Kịch bản 1B: Block-producer (Bufferbloat)
        res_block = engine.configure_buffer_scenario(capacity=48, consumer_delay_ms=85, policy="block_producer")
        assert res_block["drop_rate_pct"] == 0.0
        assert res_block["latency_ms"] >= 1500
        assert "BUFFERBLOAT" in res_block["status_badge"]

    def test_deadlock_trigger_and_manual_banker_resolve(self):
        """Kiểm chứng kích hoạt bế tắc và giải phóng thủ công bằng thuật toán Banker."""
        engine = OSLabEngine()

        status_init = engine.get_deadlock_status()
        assert status_init["deadlock_state"] == "NORMAL"
        assert not status_init["cycle_detected"]

        # Kích hoạt Deadlock
        status_deadlock = engine.trigger_deadlock_simulation()
        assert status_deadlock["deadlock_state"] == "DEADLOCK_ACTIVE"
        assert status_deadlock["cycle_detected"] is True
        assert status_deadlock["pipeline_fps"] == 0.0
        assert len(status_deadlock["rag_edges"]) == 4

        # Giải phóng bằng Banker Preemption
        status_resolved = engine.resolve_deadlock(method="banker_preemption")
        assert status_resolved["deadlock_state"] == "RESOLVED"
        assert status_resolved["cycle_detected"] is False
        assert status_resolved["pipeline_fps"] == 30.0
        assert "Banker" in status_resolved["resolution_reason"]

    def test_deadlock_hard_watchdog_auto_preemption(self):
        """Bảo vệ phần cứng: Watchdog ngầm bắt buộc tự động ngắt Deadlock sau 3.0s mà không cần người dùng can thiệp."""
        engine = OSLabEngine()
        engine.trigger_deadlock_simulation()
        assert engine.deadlock_state == "DEADLOCK_ACTIVE"

        # Chờ 3.2s để watchdog thread thức dậy và tự ngắt
        time.sleep(3.2)

        status_after_watchdog = engine.get_deadlock_status()
        assert status_after_watchdog["deadlock_state"] == "RESOLVED"
        assert not status_after_watchdog["cycle_detected"]
        assert "Watchdog Timer" in status_after_watchdog["resolution_reason"]
        assert status_after_watchdog["pipeline_fps"] == 30.0

    def test_memory_eviction_fifo_vs_threat_priority(self):
        """
        Kiểm chứng thuật toán trục xuất bộ nhớ đệm 3-Slot:
        - FIFO: Đẩy mất khung hình bạo lực KF-02 (9.2 điểm) ra khỏi RAM -> Gemini chuẩn đoán sai lệch (Bỏ lọt bạo lực).
        - Threat-Priority: Khóa KF-02 trong RAM -> Gemini chuẩn đoán chuẩn xác xô xát.
        """
        engine = OSLabEngine()

        # Chạy kiểm nghiệm FIFO
        res_fifo = engine.simulate_memory_eviction(policy="fifo")
        assert res_fifo["has_peak_frame"] is False
        assert "ÂM TÍNH GIẢ" in res_fifo["verdict_accuracy"]
        # Cuối cùng RAM chỉ chứa các khung hình lành tính KF-04, KF-05, KF-06
        final_ids_fifo = [slot["id"] for slot in res_fifo["final_slots"]]
        assert "KF-02" not in final_ids_fifo

        # Chạy kiểm nghiệm Threat-Priority
        res_prio = engine.simulate_memory_eviction(policy="priority")
        assert res_prio["has_peak_frame"] is True
        assert "DUY TRÌ NHẬN DIỆN" in res_prio["verdict_accuracy"]
        # Khung bạo lực KF-02 bắt buộc phải còn nguyên trong RAM
        final_ids_prio = [slot["id"] for slot in res_prio["final_slots"]]
        assert "KF-02" in final_ids_prio


class TestOSLabAPIEndpoints:
    """Kiểm thử các REST API endpoints của OS Lab qua TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        self.client = TestClient(app)

    def test_api_buffer_telemetry(self):
        resp = self.client.get("/api/os_lab/scenarios/buffer")
        assert resp.status_code == 200
        data = resp.json()
        assert "capacity" in data
        assert "consumer_delay_ms" in data
        assert "ram_ceiling_mb" in data
        assert data["ram_ceiling_mb"] == 50.0

        # Cập nhật thông số buffer
        post_resp = self.client.post("/api/os_lab/scenarios/buffer", json={
            "capacity": 32,
            "consumer_delay_ms": 60,
            "policy": "block_producer"
        })
        assert post_resp.status_code == 200
        post_data = post_resp.json()
        assert post_data["capacity"] == 32
        assert post_data["consumer_delay_ms"] == 60
        assert post_data["policy"] == "block_producer"

    def test_api_deadlock_endpoints(self):
        # Kiểm tra endpoint status
        get_resp = self.client.get("/api/os_lab/scenarios/deadlock")
        assert get_resp.status_code == 200

        # Trigger deadlock
        trig_resp = self.client.post("/api/os_lab/scenarios/deadlock/trigger")
        assert trig_resp.status_code == 200
        trig_data = trig_resp.json()
        assert trig_data["deadlock_state"] == "DEADLOCK_ACTIVE"
        assert trig_data["cycle_detected"] is True

        # Resolve deadlock
        res_resp = self.client.post("/api/os_lab/scenarios/deadlock/resolve", json={"method": "banker_preemption"})
        assert res_resp.status_code == 200
        res_data = res_resp.json()
        assert res_data["deadlock_state"] == "RESOLVED"
        assert res_data["cycle_detected"] is False

    def test_api_memory_eviction(self):
        resp_fifo = self.client.post("/api/os_lab/scenarios/memory_eviction", json={"policy": "fifo"})
        assert resp_fifo.status_code == 200
        data_fifo = resp_fifo.json()
        assert data_fifo["policy"] == "fifo"
        assert data_fifo["has_peak_frame"] is False

        resp_prio = self.client.post("/api/os_lab/scenarios/memory_eviction", json={"policy": "priority"})
        assert resp_prio.status_code == 200
        data_prio = resp_prio.json()
        assert data_prio["policy"] == "priority"
        assert data_prio["has_peak_frame"] is True

    def test_dual_mode_evaluation_logic(self):
        """Kiểm chứng tính toán ma trận đối sánh 2 chế độ: Live Camera vs Import Video."""
        engine = OSLabEngine()

        # Mặc định tối ưu RTX 5060 (N=16, delay=0ms)
        opt_eval = engine.get_dual_mode_evaluation(capacity=16, consumer_delay_ms=0)
        assert opt_eval["is_stall_risk"] is False
        assert "TỐI ƯU CÂN BẰNG" in opt_eval["overall_badge"]
        assert "30.0 FPS" in opt_eval["live_camera"]["speed"]
        assert "0% rủi ro" in opt_eval["live_camera"]["stability"]
        assert "Khóa trần RAM" in opt_eval["import_video"]["stability"]

        # Trạng thái giả lập nghẽn / quá tải cực đoan
        stall_eval = engine.get_dual_mode_evaluation(capacity=64, consumer_delay_ms=200)
        assert stall_eval["is_stall_risk"] is True
        assert "STALL" in stall_eval["overall_badge"]
        assert "CẢNH BÁO" in stall_eval["live_camera"]["stability"]
        assert stall_eval["ram_ceiling_mb"] == 50.0

    def test_live_benchmark_execution(self):
        """Kiểm chứng chạy thực nghiệm đo đạc 50 khung hình trên phần cứng."""
        engine = OSLabEngine()
        bench_res = engine.run_live_benchmark(capacity=16, consumer_delay_ms=0, frames_count=50)
        assert bench_res["status"] == "ok"
        assert bench_res["frames_processed"] == 50
        assert bench_res["measured_producer_fps"] > 0
        assert bench_res["measured_consumer_fps"] > 0
        assert bench_res["ram_usage_mb"] <= 50.0
        assert bench_res["is_safe"] is True

    def test_api_dual_eval_and_benchmark(self):
        """Kiểm thử REST endpoints /api/os_lab/dual_evaluation và /api/os_lab/benchmark."""
        # GET dual_evaluation
        get_resp = self.client.get("/api/os_lab/dual_evaluation?capacity=16&consumer_delay_ms=0")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert "live_camera" in get_data
        assert "import_video" in get_data

        # POST benchmark
        post_bench = self.client.post("/api/os_lab/benchmark", json={
            "capacity": 16,
            "consumer_delay_ms": 0,
            "frames_count": 50
        })
        assert post_bench.status_code == 200
        bench_data = post_bench.json()
        assert bench_data["status"] == "ok"
        assert bench_data["frames_processed"] == 50

        # POST simulate_stall
        stall_resp = self.client.post("/api/os_lab/simulate_stall")
        assert stall_resp.status_code == 200
        stall_data = stall_resp.json()
        assert stall_data["is_simulated_stall"] is True
        assert stall_data["ram_ceiling_mb"] == 50.0


    def test_budget_partition_and_sweet_spot_law(self):
        """
        Kiểm chứng Định luật Điểm Cân Bằng Lý Tưởng Y vs Nhánh Thực Nghiệm Z
        và Hạn mức Ngân sách Tài nguyên X = Y + Z <= 80% (dự trữ >= 20% cho Hệ điều hành).
        """
        engine = OSLabEngine()

        # 1. Điểm Cân Bằng Tối Ưu (Z == Y: N=16, D=0ms, drop_oldest)
        sweet = engine.get_dual_mode_evaluation(capacity=16, consumer_delay_ms=0, policy="drop_oldest")
        bp_sweet = sweet["budget_partition"]
        ab_sweet = sweet["ab_curtain_metrics"]
        assert bp_sweet["regime"] == "OPTIMAL_SWEET_SPOT"
        assert bp_sweet["host_reserve_pct"] == 20.0
        assert bp_sweet["total_allocated_pct"] <= 80.0
        assert bp_sweet["ram_ratio_vs_y"] == 1.0
        assert ab_sweet["z_fps"] == 30.0
        assert ab_sweet["z_fps"] <= ab_sweet["y_fps"]

        # 2. Cấp phát dưới ngưỡng (Z < Y: N=4, D=60ms) -> Suy giảm FPS và rơi khung hình
        under = engine.get_dual_mode_evaluation(capacity=4, consumer_delay_ms=60, policy="drop_oldest")
        bp_under = under["budget_partition"]
        ab_under = under["ab_curtain_metrics"]
        assert bp_under["regime"] == "UNDER_PROVISIONED"
        assert bp_under["total_allocated_pct"] <= 80.0
        assert ab_under["z_fps"] < ab_under["y_fps"]
        assert ab_under["z_drop_pct"] > 0.0

        # 3. Cấp phát dư thừa quá ngưỡng (Z > Y: N=64, D=0ms) -> RAM gấp 4.0x nhưng FPS không vượt trần 30.0 của Y
        over = engine.get_dual_mode_evaluation(capacity=64, consumer_delay_ms=0, policy="drop_oldest")
        bp_over = over["budget_partition"]
        ab_over = over["ab_curtain_metrics"]
        assert bp_over["regime"] == "OVER_PROVISIONED_BLOAT"
        assert bp_over["ram_ratio_vs_y"] == 4.0
        assert bp_over["total_allocated_pct"] <= 80.0
        assert ab_over["z_fps"] <= ab_over["y_fps"]
        assert ab_over["z_latency_ms"] > ab_over["y_latency_ms"]

    def test_full_page_parallel_split_and_preflight_dom(self):
        """Kiểm chứng giao diện Chiếu Song Song Toàn Trang 50/50 (Y || Z) và Bảng Thiết lập Chuẩn hóa Nhánh Z trên HTML."""
        resp = self.client.get("/")
        assert resp.status_code == 200
        html = resp.text

        # Các thành phần Full-Page 50/50 Parallel Split (Y || Z) & Pre-Flight Setup bắt buộc có mặt
        required_ids = [
            'id="live-parallel-workspace"',
            'id="live-split-y-canvas"',
            'id="live-split-z-canvas"',
            'id="btn-launch-live-parallel"',
            'id="os-budget-partition-box"',
            'id="budget-seg-y"',
            'id="budget-seg-z"',
            'id="budget-seg-reserve"',
            'id="os-lab-policy-select"',
            'id="trimmer-os-setup-box"',
            'id="chk-auto-parallel-split"',
            'id="timeline-heatmap-bar-z"',
            'id="video-os-diff-card"',
            'id="video-parallel-workspace"',
            'id="split-vid-y-player"',
            'id="split-vid-z-canvas"',
            'id="split-y-segments-list"',
            'id="split-z-segments-list"',
        ]
        for marker in required_ids:
            assert marker in html, f"Thiếu thành phần giao diện bắt buộc: {marker}"

        # Đảm bảo đã gỡ bỏ hoàn toàn thanh kéo rèm Before/After cũ và không còn trích dẫn sách giáo khoa
        assert 'id="live-ab-overlay"' not in html
        assert 'id="video-ab-overlay"' not in html
        assert 'id="os-experiment-modal"' not in html
        assert "Silberschatz" not in html
