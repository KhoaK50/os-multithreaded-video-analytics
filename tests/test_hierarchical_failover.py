"""
Unit Test Suite for Hierarchical Model Failover, Preemptive Cooldown Reversion,
and Rolling Context Memory Engine.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.

Bộ kiểm thử đạt chuẩn 100% không phụ thuộc kết nối mạng / tiêu tốn API Key thật.
Sử dụng unittest.mock mô phỏng chính xác hành vi của SDK Google GenAI v2.19.0.
"""

import os
import sys
import time
import json
import unittest
from unittest import mock
import numpy as np
from PIL import Image

# Import orchestrator logic từ core.model_orchestrator
from core.model_orchestrator import (
    HierarchicalModelOrchestrator,
    ModelTier,
    CooldownTracker,
    RollingContextMemory,
    AutonomousHeuristicArbiter,
    ContextMemoryEntry,
    is_rate_limit_error
)

from google.genai import errors


class TestHierarchicalFailoverSuite(unittest.TestCase):
    """
    Tập hợp các ca kiểm thử bảo đảm:
    - Tier 1 -> Tier 2 failover tức thì khi gặp HTTP 429
    - Preemptive Cooldown Reversion sau 60s
    - Rolling Context Memory tiêm ngữ cảnh 3-5 chu kỳ
    - Tier 3 Autonomous Heuristic Arbiter khi toàn bộ API bị chặn
    """

    def setUp(self):
        """Khởi tạo orchestrator với API Key giả lập và mock client."""
        self.orchestrator = HierarchicalModelOrchestrator(
            api_key="mock_test_key_ai_os_2026",
            tier1_model="gemini-2.0-flash",
            tier2_model="gemini-1.5-flash",
            cooldown_seconds=60.0,
            rate_limit_interval=4.2
        )
        self.mock_client = mock.MagicMock()
        self.orchestrator.client = self.mock_client

        # Tạo frame ảnh giả lập và biomechanics mẫu
        self.dummy_img = Image.new("RGB", (640, 480), color=(100, 100, 100))
        self.dummy_bio = {
            "posture": "Ngồi thẳng học tập",
            "angle": 88.5,
            "is_danger": False,
            "is_warning": False
        }

    # =========================================================================
    # Test 1: Luồng thực thi Tier 1 bình thường (Normal Execution)
    # =========================================================================
    def test_01_tier1_normal_execution(self):
        """Xác nhận Tier 1 hoạt động trơn tru khi không có lỗi, ghi nhận memory."""
        mock_response = mock.MagicMock()
        mock_response.text = json.dumps({
            "action": "Tập trung gõ máy tính",
            "description": "Đối tượng ngồi ngay ngắn trước màn hình, thao tác bàn phím đều đặn.",
            "prediction_next_4s": "Tiếp tục công việc soạn thảo văn bản kỹ thuật.",
            "severity": "safe"
        })
        self.mock_client.models.generate_content.return_value = mock_response

        res = self.orchestrator.execute_live_analysis(self.dummy_img, self.dummy_bio)

        # Kiểm tra kết quả trả về
        self.assertEqual(res["action"], "Tập trung gõ máy tính")
        self.assertEqual(res["severity"], "safe")
        self.assertEqual(res["model_tier"], ModelTier.TIER_1_PRIMARY.value)

        # Kiểm tra mô hình được gọi
        call_kwargs = self.mock_client.models.generate_content.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-2.0-flash")

        # Kiểm tra Rolling Context Memory được cập nhật
        self.assertEqual(len(self.orchestrator.context_memory.history), 1)
        self.assertEqual(self.orchestrator.context_memory.history[0].action, "Tập trung gõ máy tính")
        self.assertEqual(self.orchestrator.active_tier, ModelTier.TIER_1_PRIMARY)

    # =========================================================================
    # Test 2: Bắt lỗi HTTP 429 trên Tier 1 -> Failover tức thì sang Tier 2
    # =========================================================================
    def test_02_tier1_http_429_triggers_immediate_failover_to_tier2(self):
        """Giả lập lỗi 429 RESOURCE_EXHAUSTED trên Tier 1, hệ thống chuyển sang Tier 2."""
        err_429 = errors.ClientError(
            code=429,
            response_json={
                "error": {
                    "code": 429,
                    "message": "Resource has been exhausted (rate limit 15 RPM).",
                    "status": "RESOURCE_EXHAUSTED"
                }
            }
        )

        tier2_response = mock.MagicMock()
        tier2_response.text = json.dumps({
            "action": "Nghiêng người với tài liệu",
            "description": "Đối tượng nghiêng nhẹ sang bên phải để lấy giáo trình học tập.",
            "prediction_next_4s": "Mở sách và tiếp tục đối chiếu với tài liệu điện tử.",
            "severity": "safe"
        })

        def side_effect(*args, **kwargs):
            model_called = kwargs.get("model")
            if model_called == "gemini-2.0-flash":
                raise err_429
            elif model_called == "gemini-1.5-flash":
                return tier2_response
            raise ValueError(f"Mô hình không xác định: {model_called}")

        self.mock_client.models.generate_content.side_effect = side_effect

        # Thực thi
        res = self.orchestrator.execute_live_analysis(self.dummy_img, self.dummy_bio)

        # Kiểm tra kết quả failover
        self.assertEqual(res["action"], "Nghiêng người với tài liệu")
        self.assertEqual(res["model_tier"], ModelTier.TIER_2_FALLBACK.value)
        self.assertEqual(self.orchestrator.active_tier, ModelTier.TIER_2_FALLBACK)

        # Xác nhận Cooldown Tracker đã được kích hoạt cho Tier 1 (khoảng 60s)
        remaining = self.orchestrator.cooldown_tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)
        self.assertTrue(55.0 <= remaining <= 60.0)
        self.assertFalse(self.orchestrator.cooldown_tracker.is_tier1_ready())

    # =========================================================================
    # Test 3: Tiêm bộ nhớ ngữ cảnh trượt (Rolling Context Memory) vào Prompt
    # =========================================================================
    def test_03_rolling_context_memory_injection_into_prompt(self):
        """Xác nhận prompt gửi tới mô hình chứa đầy đủ 3 chu kỳ quan sát trước đó."""
        # Nạp thủ công 3 sự kiện lịch sử vào memory
        actions = ["Gõ phím liên tục", "Chống cằm suy nghĩ", "Uống nước giải lao"]
        for idx, act in enumerate(actions):
            self.orchestrator.context_memory.record(
                ContextMemoryEntry(
                    timestamp=time.time() - (30 - idx * 10),
                    time_str=f"10:00:{idx*10:02d}",
                    action=act,
                    description=f"Mô tả chi tiết hành vi {act}",
                    posture="Ngồi thẳng",
                    torso_angle=85.0 + idx,
                    prediction="Duy trì ổn định",
                    severity="safe",
                    tier_used="Tier-1 Gemini 2.0"
                )
            )

        mock_response = mock.MagicMock()
        mock_response.text = json.dumps({
            "action": "Tiếp tục làm việc tập trung",
            "description": "Sau khi uống nước, đối tượng quay lại đặt hai tay lên bàn phím.",
            "prediction_next_4s": "Gõ phím liên tục.",
            "severity": "safe"
        })
        self.mock_client.models.generate_content.return_value = mock_response

        # Thực thi chu kỳ kế tiếp
        self.orchestrator.execute_live_analysis(self.dummy_img, self.dummy_bio)

        # Trích xuất nội dung prompt đã truyền vào SDK
        call_kwargs = self.mock_client.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        prompt_text = contents[0]

        # Kiểm tra sự xuất hiện của các hành vi trước đó và mốc thời gian T-3, T-2, T-1
        self.assertIn("DÒNG THỜI GIAN NGỮ CẢNH HÀNH VI", prompt_text)
        self.assertIn("Gõ phím liên tục", prompt_text)
        self.assertIn("Chống cằm suy nghĩ", prompt_text)
        self.assertIn("Uống nước giải lao", prompt_text)
        self.assertIn("(T-3)", prompt_text)
        self.assertIn("(T-2)", prompt_text)
        self.assertIn("(T-1)", prompt_text)
        self.assertIn("YÊU CẦU: Tiếp nối diễn biến hành vi liền mạch", prompt_text)

    # =========================================================================
    # Test 4: Tự phục hồi sau 60s Cooldown (Preemptive Cooldown Reversion)
    # =========================================================================
    def test_04_preemptive_cooldown_reversion_after_60s(self):
        """Sau 60s hết cooldown của Tier 1, lượt gọi tiếp theo phải tự động quay lại Tier 1."""
        # 1. Giả lập Tier 1 vừa bị 429 và rơi vào Tier 2
        self.orchestrator.active_tier = ModelTier.TIER_2_FALLBACK
        self.orchestrator.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)
        self.assertFalse(self.orchestrator.cooldown_tracker.is_tier1_ready())

        # 2. Tua nhanh thời gian bằng cách điều chỉnh mốc thời gian bắt đầu cooldown lùi về 65s trước
        self.orchestrator.cooldown_tracker.tier1_cooldown_start = time.time() - 65.0
        self.assertTrue(self.orchestrator.cooldown_tracker.is_tier1_ready())

        # 3. Chuẩn bị mock response cho Tier 1
        tier1_response = mock.MagicMock()
        tier1_response.text = json.dumps({
            "action": "Ngồi học tập nghiêm túc",
            "description": "Mô hình Tier 1 phục hồi thành công và phân tích thị giác độ phân giải cao.",
            "prediction_next_4s": "Duy trì đọc giáo trình.",
            "severity": "safe"
        })
        self.mock_client.models.generate_content.return_value = tier1_response

        # 4. Thực thi lượt suy luận tiếp theo
        res = self.orchestrator.execute_live_analysis(self.dummy_img, self.dummy_bio)

        # 5. Xác nhận hệ thống đã chủ động quay lại Tier 1
        self.assertEqual(res["model_tier"], ModelTier.TIER_1_PRIMARY.value)
        self.assertEqual(self.orchestrator.active_tier, ModelTier.TIER_1_PRIMARY)
        call_kwargs = self.mock_client.models.generate_content.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gemini-2.0-flash")

    # =========================================================================
    # Test 5: Cả Tier 1 & Tier 2 đều chặn 429 -> Kích hoạt Tier 3 Heuristic Arbiter
    # =========================================================================
    def test_05_all_cloud_tiers_exhausted_activates_rich_heuristic_arbiter(self):
        """Khi cả 2 tầng API Cloud đều lỗi 429, Tier 3 Arbiter tự kích hoạt an toàn với ngữ cảnh phong phú."""
        err_429 = errors.ClientError(
            code=429,
            response_json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}
        )
        self.mock_client.models.generate_content.side_effect = err_429

        # Nạp 1 sự kiện ngữ cảnh trước đó
        self.orchestrator.context_memory.record(
            ContextMemoryEntry(
                timestamp=time.time() - 4.0,
                time_str="10:15:00",
                action="Đang đứng trình bày",
                description="Đứng trước bảng",
                posture="Đứng thẳng",
                torso_angle=89.0,
                prediction="Tiếp tục giảng bài",
                severity="safe",
                tier_used="Tier-1 Gemini 2.0"
            )
        )

        # Biomechanics hiện tại: Đã chuyển sang ngồi cúi xuống
        bio_cur = {
            "posture": "Cúi đầu đọc tài liệu",
            "angle": 55.0,
            "is_danger": False,
            "is_warning": True
        }

        res = self.orchestrator.execute_live_analysis(self.dummy_img, bio_cur)

        # Xác nhận Tier 3 Arbiter được gọi
        self.assertEqual(res["model_tier"], ModelTier.TIER_3_HEURISTIC.value)
        self.assertEqual(res["action"], "Cúi đầu đọc tài liệu")
        self.assertEqual(res["severity"], "warning")
        self.assertEqual(self.orchestrator.active_tier, ModelTier.TIER_3_HEURISTIC)

        # Kiểm tra nhận thức chuyển tiếp ngữ cảnh (Context-aware transition note)
        self.assertIn("Chuyển tiếp trạng thái từ 'Đang đứng trình bày' sang 'Cúi đầu đọc tài liệu'", res["description"])
        self.assertIn("bộ hội chẩn tự hành cục bộ", res["description"])

    # =========================================================================
    # Test 6: Kiểm thử độc lập CooldownTracker (Độ trễ và bộ đếm cửa sổ trượt)
    # =========================================================================
    def test_06_cooldown_tracker_sliding_window_unit(self):
        """Kiểm thử unit test riêng biệt cho lớp CooldownTracker."""
        tracker = CooldownTracker(cooldown_seconds=60.0)
        self.assertTrue(tracker.is_tier1_ready())
        self.assertEqual(tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY), 0.0)

        # Kích hoạt cooldown
        tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)
        self.assertFalse(tracker.is_tier1_ready())
        self.assertGreater(tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY), 50.0)

        # Giả lập trôi qua 30s
        tracker.tier1_cooldown_start = time.time() - 30.0
        self.assertFalse(tracker.is_tier1_ready())
        rem = tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)
        self.assertTrue(28.0 <= rem <= 31.0)

        # Giả lập trôi qua 61s -> Tự phục hồi
        tracker.tier1_cooldown_start = time.time() - 61.0
        self.assertTrue(tracker.is_tier1_ready())
        self.assertEqual(tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY), 0.0)

    # =========================================================================
    # Test 7: Kiểm thử RollingContextMemory giới hạn FIFO (maxlen=5)
    # =========================================================================
    def test_07_rolling_context_memory_fifo_bounded_buffer(self):
        """Kiểm tra giới hạn FIFO của bộ nhớ trượt, không bị phình to vô hạn."""
        memory = RollingContextMemory(maxlen=5)
        for i in range(8):
            memory.record(
                ContextMemoryEntry(
                    timestamp=float(i),
                    time_str=f"00:00:{i:02d}",
                    action=f"Hành vi #{i}",
                    description=f"Mô tả #{i}",
                    posture="Bình thường",
                    torso_angle=90.0,
                    prediction="Ổn định",
                    severity="safe",
                    tier_used="Tier-1"
                )
            )

        # Chiều dài chỉ tối đa là 5
        self.assertEqual(len(memory.history), 5)
        # Mục đầu tiên phải là #3 và mục cuối cùng là #7
        self.assertEqual(memory.history[0].action, "Hành vi #3")
        self.assertEqual(memory.history[-1].action, "Hành vi #7")

    # =========================================================================
    # Test 8: Kiểm thử get_active_tier_info chuẩn Contract viễn trắc HĐH
    # =========================================================================
    def test_08_get_active_tier_info_telemetry(self):
        """Kiểm tra dữ liệu viễn trắc phục vụ API /api/telemetry và Video HUD."""
        # Trạng thái ban đầu: Tier 1
        info1 = self.orchestrator.get_active_tier_info()
        self.assertEqual(info1["active_tier"], "tier_1")
        self.assertEqual(info1["tier_name"], "gemini-2.0-flash")
        self.assertEqual(info1["tier_badge"], "● Tier-1 Gemini 2.0")
        self.assertFalse(info1["is_cooldown"])
        self.assertEqual(info1["cooldown_remaining"], 0.0)

        # Chuyển sang Tier 2 (Failover)
        self.orchestrator.active_tier = ModelTier.TIER_2_FALLBACK
        self.orchestrator.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)
        info2 = self.orchestrator.get_active_tier_info()
        self.assertEqual(info2["active_tier"], "tier_2")
        self.assertEqual(info2["tier_name"], "gemini-1.5-flash")
        self.assertEqual(info2["tier_badge"], "● Tier-2 Gemini 1.5 (Failover)")
        self.assertTrue(info2["is_cooldown"])
        self.assertGreater(info2["cooldown_remaining"], 0.0)

        # Chuyển sang Tier 3 (Arbiter)
        self.orchestrator.active_tier = ModelTier.TIER_3_HEURISTIC
        info3 = self.orchestrator.get_active_tier_info()
        self.assertEqual(info3["active_tier"], "tier_3")
        self.assertEqual(info3["tier_badge"], "● AI Tự Hành (Local Heuristic)")

    # =========================================================================
    # Test 9: Điều phối nhịp độ gọi API an toàn (Pacing >= 4.2s)
    # =========================================================================
    def test_09_acquire_api_permission_pacing(self):
        """Kiểm tra cơ chế cấp phép API điều tiết lưu lượng khống chế trần 15 RPM."""
        # Cuộc gọi đầu tiên được phép
        self.assertTrue(self.orchestrator.acquire_api_permission("normal"))

        # Cuộc gọi ngay tức thì tiếp theo bị từ chối (Backpressure / Throttled)
        self.assertFalse(self.orchestrator.acquire_api_permission("normal"))

        # Cuộc gọi khẩn cấp (priority='high') luôn được phép
        self.assertTrue(self.orchestrator.acquire_api_permission("high"))

        # Giả lập thời gian trôi qua 4.5s
        self.orchestrator.last_api_call_time = time.time() - 4.5
        self.assertTrue(self.orchestrator.acquire_api_permission("normal"))

    # =========================================================================
    # Test 10: Xử lý phản hồi JSON bọc trong Markdown Code Block (```json ... ```)
    # =========================================================================
    def test_10_json_markdown_fence_stripping(self):
        """Kiểm tra khả năng bóc tách JSON an toàn khi Gemini trả về Markdown fence."""
        raw_markdown = """```json
{
    "action": "Đang đứng phát biểu",
    "description": "Đối tượng đứng tự tin, hai tay cử động nhịp nhàng theo lời nói.",
    "prediction_next_4s": "Tiếp tục bài thuyết trình.",
    "severity": "safe"
}
```"""
        mock_response = mock.MagicMock()
        mock_response.text = raw_markdown
        self.mock_client.models.generate_content.return_value = mock_response

        res = self.orchestrator.execute_live_analysis(self.dummy_img, self.dummy_bio)
        self.assertEqual(res["action"], "Đang đứng phát biểu")
        self.assertEqual(res["severity"], "safe")

    # =========================================================================
    # Test 11: Khởi tạo không có API Key hoạt động trơn tru qua Tier 3
    # =========================================================================
    def test_11_graceful_handling_without_api_key(self):
        """Khi không cấu hình API Key, hệ thống tự động chạy Tier 3 Arbiter không crash."""
        orch_no_key = HierarchicalModelOrchestrator(api_key=None, api_keys=[])
        orch_no_key.client = None

        res = orch_no_key.execute_live_analysis(self.dummy_img, self.dummy_bio)
        self.assertEqual(res["model_tier"], ModelTier.TIER_3_HEURISTIC.value)
        self.assertEqual(res["action"], "Ngồi thẳng học tập")
        self.assertIn("bộ hội chẩn tự hành cục bộ", res["description"])

    # =========================================================================
    # Test 12: Nhận diện chính xác mọi dạng thức ngoại lệ 429
    # =========================================================================
    def test_12_generic_string_429_detection(self):
        """Kiểm tra hàm is_rate_limit_error nhận diện mọi dạng lỗi 429/ResourceExhausted."""
        # 1. Google GenAI ClientError
        err1 = errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        self.assertTrue(is_rate_limit_error(err1))

        # 2. Google GenAI APIError với code=429
        err2 = errors.APIError(429, {"error": {"code": 429}})
        self.assertTrue(is_rate_limit_error(err2))

        # 3. Generic Exception chứa chữ 429
        err3 = Exception("HTTP Error 429: Too Many Requests")
        self.assertTrue(is_rate_limit_error(err3))

        # 4. Generic Exception chứa RESOURCE_EXHAUSTED
        err4 = Exception("Resource has been exhausted: quota limit exceeded")
        self.assertTrue(is_rate_limit_error(err4))

        # 5. Ngoại lệ 500 Internal Error (Không phải rate limit)
        err5 = Exception("500 Internal Server Error")
        self.assertFalse(is_rate_limit_error(err5))
        self.assertFalse(is_rate_limit_error(None))

    # =========================================================================
    # Test 13: execute_multimodal_failover từ Tier 1 sang Tier 2 khi gặp 429
    # =========================================================================
    def test_13_multimodal_failover_tier1_to_tier2(self):
        """Kiểm tra execute_multimodal_failover tự động chuyển từ Tier 1 sang Tier 2 khi gặp 429."""
        err_429 = errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        tier2_resp = mock.MagicMock()
        tier2_resp.text = json.dumps({"status": "success", "detailed_diagnosis": "Tier 2 Report"})

        def side_effect(*args, **kwargs):
            m = kwargs.get("model")
            if m == "gemini-2.0-flash":
                raise err_429
            elif m == "gemini-1.5-flash":
                return tier2_resp
            raise ValueError(f"Unknown model: {m}")

        self.mock_client.models.generate_content.side_effect = side_effect
        data, used_tier = self.orchestrator.execute_multimodal_failover(contents=["test prompt"])
        self.assertEqual(used_tier, ModelTier.TIER_2_FALLBACK)
        self.assertEqual(data["detailed_diagnosis"], "Tier 2 Report")

    # =========================================================================
    # Test 14: TokenGuard tích hợp ModelOrchestrator failover và fallback Tier 3
    # =========================================================================
    def test_14_token_guard_failover_and_tier3_fallback(self):
        """Kiểm tra TokenGuard định tuyến qua Orchestrator và fallback Tier 3 khi cạn quota."""
        from core.token_guard import TokenGuard
        tg = TokenGuard(api_key="mock_key", orchestrator=self.orchestrator)
        
        # Giả lập cả 2 tầng Cloud đều bị 429
        err_429 = errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        self.mock_client.models.generate_content.side_effect = err_429

        meta = {"video_source": "test_video_sample_unique_9999.mp4", "audio_status": "none"}
        ev_summary = [{"timestamp": 5.0, "threat_type": "HÀNH VI", "details": "Đi lại", "threat_score": 0.1}]
        peak_kf = []
        result = tg.synthesize_video_report(meta, ev_summary, peak_kf)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["model_tier"], "Tier-3 Local Arbiter")
        self.assertIn("Tier-3 Autonomous Heuristic", result["detailed_diagnosis"])

    # =========================================================================
    # Test 15: GeminiVideoAnalyzer cơ chế failover Tier 1 -> Tier 2 và Tier 3
    # =========================================================================
    def test_15_gemini_video_analyzer_failover(self):
        """Kiểm tra GeminiVideoAnalyzer tự động failover sang Tier 2 khi Tier 1 lỗi 429."""
        from core.gemini_analyzer import GeminiVideoAnalyzer
        analyzer = GeminiVideoAnalyzer(api_key="mock_key", orchestrator=self.orchestrator)
        mock_genai_client = mock.MagicMock()
        analyzer.client = mock_genai_client

        err_429 = errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})
        tier2_resp = mock.MagicMock()
        tier2_resp.text = "Câu trả lời từ Gemini Tier-2."

        def qa_side_effect(*args, **kwargs):
            m = kwargs.get("model")
            if m == "gemini-2.0-flash":
                raise err_429
            elif m == "gemini-1.5-flash":
                return tier2_resp
            raise ValueError(f"Unknown model: {m}")

        mock_genai_client.models.generate_content.side_effect = qa_side_effect

        events = [{"formatted_time": "10:00", "action": "Ngồi học", "confidence": 0.9, "is_danger": False}]
        ans = analyzer.ask_about_events("Đang làm gì?", events)
        self.assertEqual(ans, "Câu trả lời từ Gemini Tier-2.")


if __name__ == "__main__":
    unittest.main()
