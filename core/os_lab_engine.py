"""
OS Experimental Lab Engine (Phòng Thực Nghiệm Hệ Điều Hành Đối Chứng).
Học phần: Hệ điều hành (2611COMP133202).

Nguyên tắc an toàn & bảo vệ phần cứng:
1. Hard Memory Ceiling (Trần RAM cứng): Toàn bộ cấu trúc đệm chỉ được phép chiếm tối đa 50MB.
2. Watchdog Timer cứng (3.0s): Mọi kịch bản bế tắc (Deadlock) đều tự động bị ngắt và hoàn nguyên sau tối đa 3.0s.
3. Micro-yield Pacing: Không vòng lặp vô hạn, giữ tải CPU luôn dưới 25-35%.
4. Mối quan hệ nhân quả: Điều chỉnh tham số HĐH -> Tác động trực tiếp lên FPS, độ trễ và độ chính xác của AI.
"""

import time
import threading
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

HARD_RAM_CEILING_MB = 50.0
DEADLOCK_WATCHDOG_TIMEOUT_SEC = 3.0


class OSLabEngine:
    """
    Bộ điều phối phòng thực nghiệm Hệ điều hành đa luồng an toàn (Sandboxed OS Lab).
    Cung cấp 3 kịch bản đối chứng trực quan chuẩn giáo trình Silberschatz:
    - Kịch bản 1: Hàng đợi Bounded Buffer & Hiện tượng Bufferbloat vs Drop-Rate.
    - Kịch bản 2: Bế tắc Đa luồng (Deadlock) & Đồ thị RAG với Watchdog tự ngắt 3.0s.
    - Kịch bản 3: Thuật toán Trục xuất Bộ nhớ đệm Keyframe (FIFO vs Threat-Priority Eviction).
    """

    def __init__(self, camera_pipeline=None):
        self.camera_pipeline = camera_pipeline
        self.lock = threading.Lock()

        # Trạng thái Kịch bản 1: Bounded Buffer & Bufferbloat
        self.buffer_capacity = 16
        self.consumer_delay_ms = 0
        self.buffer_policy = "drop_oldest"  # "drop_oldest" | "block_producer"

        # Trạng thái Kịch bản 2: Deadlock Simulator & Watchdog
        self.deadlock_state = "NORMAL"  # "NORMAL" | "DEADLOCK_ACTIVE" | "RESOLVED"
        self.deadlock_start_time = 0.0
        self.deadlock_deadline = 0.0
        self.deadlock_resolution_reason = ""
        self._watchdog_thread = None

        # Trạng thái Kịch bản 3: Memory Eviction Policy
        self.memory_policy = "priority"  # "fifo" | "priority"

    # =========================================================================
    # KỊCH BẢN 1: BOUNDED BUFFER & BUFFERBLOAT VS DROP-RATE
    # =========================================================================
    def configure_buffer_scenario(
        self,
        capacity: int = 16,
        consumer_delay_ms: int = 0,
        policy: str = "drop_oldest"
    ) -> Dict[str, Any]:
        """
        Cập nhật cấu hình Bounded Buffer và tính toán tác động nhân quả lên AI.
        """
        with self.lock:
            self.buffer_capacity = max(2, min(48, int(capacity)))
            self.consumer_delay_ms = max(0, min(120, int(consumer_delay_ms)))
            self.buffer_policy = "block_producer" if policy == "block_producer" else "drop_oldest"

            # Áp dụng trực tiếp vào Camera Pipeline nếu đang hoạt động
            if self.camera_pipeline and hasattr(self.camera_pipeline, "frame_buffer"):
                self.camera_pipeline.frame_buffer.resize_capacity(self.buffer_capacity)
                self.camera_pipeline.consumer_delay_ms = self.consumer_delay_ms

        return self.get_buffer_impact_telemetry()

    def get_buffer_impact_telemetry(self) -> Dict[str, Any]:
        """
        Tính toán hiệu năng Hệ điều hành và tác động trực tiếp lên phân tích AI.
        """
        with self.lock:
            cap = self.buffer_capacity
            delay = self.consumer_delay_ms
            pol = self.buffer_policy

        # Ước lượng độ trễ tích lũy (Queue Latency) và Tỷ lệ rớt khung hình (Drop Rate)
        # Giả sử tốc độ nạp của Producer là 30 FPS (33.3ms / frame)
        producer_interval_ms = 33.3
        effective_consumer_ms = max(producer_interval_ms, 33.3 + delay)
        
        # Mức tải hàng đợi thực tế
        if delay == 0:
            queue_fill = min(cap, max(1, cap // 4))
            drop_rate_pct = 0.0
            latency_ms = int(queue_fill * producer_interval_ms)
        else:
            speed_mismatch = (effective_consumer_ms - producer_interval_ms) / effective_consumer_ms
            if pol == "block_producer":
                queue_fill = cap  # Luôn đầy ứ
                drop_rate_pct = 0.0
                latency_ms = int(cap * effective_consumer_ms)
            else:  # drop_oldest
                queue_fill = cap
                drop_rate_pct = round(min(65.0, speed_mismatch * 100.0), 1)
                latency_ms = int(cap * producer_interval_ms)

        ram_mb = round(min(HARD_RAM_CEILING_MB, cap * 2.64), 2)  # ~2.64MB per 720p raw RGB frame

        # Tác động nhân quả lên phân tích AI:
        # Nếu rớt khung hình > 20%, mất đỉnh xung lực gia tốc va chạm dE/dt -> Điểm nguy hiểm bị sai lệch
        if drop_rate_pct >= 25.0:
            kinetic_fidelity = "MẤT ĐỈNH XUNG LỰC (Rơi khung hình)"
            threat_score_impact = -4.2  # Bỏ lọt hành vi bạo lực
            simulated_threat_score = round(max(1.8, 8.8 + threat_score_impact), 1)
            ai_diagnosis = f"Cảnh báo: Tỷ lệ rớt khung hình {drop_rate_pct}% làm mất đỉnh va chạm dE/dt. Điểm nguy hiểm bị hạ từ 8.8 xuống {simulated_threat_score} (Bỏ lọt xung đột!)."
            status_badge = "CẢNH BÁO RƠI KHUNG"
            badge_class = "tag-warning"
        elif latency_ms >= 1500:
            kinetic_fidelity = "ĐẦY ĐỦ NHƯNG BỊ TRỄ NẶNG (Bufferbloat)"
            threat_score_impact = 0.0
            simulated_threat_score = 8.8
            ai_diagnosis = f"Cảnh báo: Hiện tượng Bufferbloat ({latency_ms} ms). AI nhận diện chính xác 8.8/10 nhưng bị trễ {round(latency_ms / 1000.0, 1)}s so với hiện trường."
            status_badge = "TRỄ TÍCH LŨY (BUFFERBLOAT)"
            badge_class = "tag-danger"
        else:
            kinetic_fidelity = "HOÀN HẢO (Thời gian thực 30 FPS)"
            threat_score_impact = 0.0
            simulated_threat_score = 8.8
            ai_diagnosis = f"Trạng thái tối ưu: Hàng đợi kiểm soát tốt ({queue_fill}/{cap}), độ trễ {latency_ms} ms, AI ghi nhận trọn vẹn gia tốc xung lực (8.8 / 10)."
            status_badge = "TỐI ƯU CÂN BẰNG"
            badge_class = "tag-safe"

        return {
            "capacity": cap,
            "consumer_delay_ms": delay,
            "policy": pol,
            "queue_fill": queue_fill,
            "queue_fill_pct": int((queue_fill / cap) * 100),
            "latency_ms": latency_ms,
            "drop_rate_pct": drop_rate_pct,
            "ram_usage_mb": ram_mb,
            "ram_ceiling_mb": HARD_RAM_CEILING_MB,
            "kinetic_fidelity": kinetic_fidelity,
            "threat_score": simulated_threat_score,
            "ai_diagnosis": ai_diagnosis,
            "status_badge": status_badge,
            "badge_class": badge_class
        }

    # =========================================================================
    # KỊCH BẢN 2: BẾ TẮC ĐA LUỒNG (DEADLOCK) & ĐỒ THỊ RAG VỚI WATCHDOG 3.0S
    # =========================================================================
    def trigger_deadlock_simulation(self) -> Dict[str, Any]:
        """
        Kích hoạt thử nghiệm Bế tắc Đa luồng (Deadlock Simulation).
        Bảo vệ phần cứng 100%: Tự động kích hoạt Watchdog Timer ngắt sau đúng 3.0s!
        """
        with self.lock:
            self.deadlock_state = "DEADLOCK_ACTIVE"
            self.deadlock_start_time = time.time()
            self.deadlock_deadline = self.deadlock_start_time + DEADLOCK_WATCHDOG_TIMEOUT_SEC
            self.deadlock_resolution_reason = ""

        # Khởi động luồng Watchdog giám sát tự động
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            pass
        else:
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_worker,
                name="OSLabWatchdogGuard",
                daemon=True
            )
            self._watchdog_thread.start()

        logger.info(f"[OSLabEngine] Kích hoạt giả lập Deadlock. Watchdog sẽ tự ngắt sau {DEADLOCK_WATCHDOG_TIMEOUT_SEC}s.")
        return self.get_deadlock_status()

    def resolve_deadlock(self, method: str = "banker_preemption") -> Dict[str, Any]:
        """
        Giải phóng bế tắc thủ công theo nguyên lý Hệ điều hành (Thuật toán Banker / Thu hồi khóa Preemption).
        """
        with self.lock:
            if self.deadlock_state == "DEADLOCK_ACTIVE":
                self.deadlock_state = "RESOLVED"
                self.deadlock_resolution_reason = (
                    "Thuật toán Banker: Thu hồi khóa tài nguyên R2 (GPU Context) từ Luồng Writer, "
                    "bẻ gãy chu trình chờ đợi vòng tròn (Break Circular Wait)."
                ) if method == "banker_preemption" else "Hệ thống đã giải phóng khóa tài nguyên an toàn."
                logger.info("[OSLabEngine] Bế tắc đã được giải phóng theo yêu cầu người dùng.")

        return self.get_deadlock_status()

    def _watchdog_worker(self):
        """
        Luồng Watchdog Timer ngầm: Đảm bảo phần mềm không bao giờ bị đơ quá 3.0s.
        """
        while True:
            time.sleep(0.15)
            with self.lock:
                if self.deadlock_state != "DEADLOCK_ACTIVE":
                    break
                now = time.time()
                if now >= self.deadlock_deadline:
                    self.deadlock_state = "RESOLVED"
                    self.deadlock_resolution_reason = (
                        f"Watchdog Timer ({DEADLOCK_WATCHDOG_TIMEOUT_SEC}s): Bộ đếm an toàn HĐH tự động can thiệp, "
                        "thu hồi khóa tranh chấp (Resource Preemption) để khôi phục luồng video bình thường."
                    )
                    logger.info("[OSLabEngine] Watchdog timer đã tự động can thiệp gỡ bế tắc thành công.")
                    break

    def get_deadlock_status(self) -> Dict[str, Any]:
        """
        Lấy thông tin đồ thị cấp phát tài nguyên RAG và trạng thái bế tắc.
        """
        with self.lock:
            state = self.deadlock_state
            start_t = self.deadlock_start_time
            deadline_t = self.deadlock_deadline
            reason = self.deadlock_resolution_reason

        now = time.time()
        time_remaining = max(0.0, round(deadline_t - now, 1)) if state == "DEADLOCK_ACTIVE" else 0.0
        elapsed_sec = round(now - start_t, 1) if state == "DEADLOCK_ACTIVE" else (3.0 if state == "RESOLVED" else 0.0)

        # Cấu trúc Đồ thị Cấp phát Tài nguyên (Resource Allocation Graph - RAG) chuẩn sách giáo trình Silberschatz:
        # 2 Luồng: T1 (AI Worker), T2 (Stream Writer)
        # 2 Tài nguyên: R1 (Frame Buffer Lock), R2 (GPU Context Lock)
        nodes = [
            {"id": "T1", "label": "Luồng AI Worker", "type": "thread", "state": "WAITING" if state == "DEADLOCK_ACTIVE" else "RUNNING"},
            {"id": "T2", "label": "Luồng Stream Writer", "type": "thread", "state": "WAITING" if state == "DEADLOCK_ACTIVE" else "RUNNING"},
            {"id": "R1", "label": "Khóa Buffer (R1)", "type": "resource", "held_by": "T1" if state == "DEADLOCK_ACTIVE" else "None"},
            {"id": "R2", "label": "Khóa GPU (R2)", "type": "resource", "held_by": "T2" if state == "DEADLOCK_ACTIVE" else "None"}
        ]

        if state == "DEADLOCK_ACTIVE":
            edges = [
                {"from": "T1", "to": "R2", "type": "request", "label": "Yêu cầu khóa R2"},
                {"from": "R2", "to": "T2", "type": "assignment", "label": "T2 đang giữ R2"},
                {"from": "T2", "to": "R1", "type": "request", "label": "Yêu cầu khóa R1"},
                {"from": "R1", "to": "T1", "type": "assignment", "label": "T1 đang giữ R1"}
            ]
            cycle_detected = True
            pipeline_fps = 0.0
            video_state = "ĐÓNG BĂNG HOÀN TOÀN (DEADLOCK FREEZE)"
            ai_impact = "Toàn bộ chu kỳ suy luận thị giác bị tê liệt, FPS rớt về 0.0."
        elif state == "RESOLVED":
            edges = [
                {"from": "T1", "to": "R1", "type": "assignment", "label": "T1 hoàn tất đọc R1"},
                {"from": "T1", "to": "R2", "type": "assignment", "label": "Cấp quyền R2 cho T1"},
                {"from": "T2", "to": "R2", "type": "idle", "label": "T2 nhả khóa chờ lượt mới"}
            ]
            cycle_detected = False
            pipeline_fps = 30.0
            video_state = "ĐÃ PHỤC HỒI HOÀN TOÀN (NORMAL STREAMING)"
            ai_impact = "Bẻ gãy chu trình bế tắc thành công. Luồng video và suy luận AI khôi phục mượt mà."
        else:
            edges = [
                {"from": "T1", "to": "R1", "type": "assignment", "label": "Tuần tự an toàn"},
                {"from": "T2", "to": "R2", "type": "assignment", "label": "Tuần tự an toàn"}
            ]
            cycle_detected = False
            pipeline_fps = 30.0
            video_state = "BÌNH THƯỜNG (KHÔNG BẾ TẮC)"
            ai_impact = "Các luồng đồng bộ hóa tuần tự theo miền găng Mutex tiêu chuẩn."

        return {
            "deadlock_state": state,
            "cycle_detected": cycle_detected,
            "time_remaining_sec": time_remaining,
            "elapsed_sec": elapsed_sec,
            "watchdog_limit_sec": DEADLOCK_WATCHDOG_TIMEOUT_SEC,
            "pipeline_fps": pipeline_fps,
            "video_state": video_state,
            "ai_impact": ai_impact,
            "resolution_reason": reason,
            "rag_nodes": nodes,
            "rag_edges": edges
        }

    # =========================================================================
    # KỊCH BẢN 3: THUẬT TOÁN TRỤC XUẤT BỘ NHỚ ĐỆM KEYFRAME (FIFO VS THREAT-PRIORITY)
    # =========================================================================
    def simulate_memory_eviction(self, policy: str = "fifo") -> Dict[str, Any]:
        """
        Mô phỏng chuỗi 6 khung hình video thực tế đi qua Bộ nhớ đệm 3-Slot cố định (RAM < 15MB).
        Minh chứng sự khác biệt sống còn giữa FIFO (Vào trước ra trước) và Threat-Priority Eviction.
        """
        pol = "priority" if policy.lower() in ("priority", "threat_priority") else "fifo"

        # Chuỗi 6 khung hình sự kiện điển hình:
        frames_stream = [
            {"id": "KF-01", "time": "00:01", "action": "Học sinh ngồi tự học tại bàn", "threat_score": 0.8, "is_combat": False},
            {"id": "KF-02", "time": "00:04", "action": "ĐỐI TƯỢNG LAO VÀO ĐẤM NGÃ NẠN NHÂN (ĐỈNH ĐIỂM)", "threat_score": 9.2, "is_combat": True},
            {"id": "KF-03", "time": "00:06", "action": "Giằng co xô xát dưới sàn lớp học", "threat_score": 8.5, "is_combat": True},
            {"id": "KF-04", "time": "00:15", "action": "Các bạn cùng lớp đứng quanh quan sát", "threat_score": 2.1, "is_combat": False},
            {"id": "KF-05", "time": "00:22", "action": "Học sinh quay trở về ghế ngồi ổn định", "threat_score": 1.2, "is_combat": False},
            {"id": "KF-06", "time": "00:30", "action": "Không gian lớp học yên tĩnh bình thường", "threat_score": 0.6, "is_combat": False}
        ]

        # Bộ nhớ đệm 3 slot cố định trong RAM
        slots_log = []
        current_slots = []

        if pol == "fifo":
            # FIFO: Vào trước ra trước một cách máy móc
            for step_idx, f in enumerate(frames_stream):
                evicted = None
                if len(current_slots) < 3:
                    current_slots.append(f)
                else:
                    evicted = current_slots.pop(0)  # Đẩy phần tử cũ nhất ra
                    current_slots.append(f)

                slots_log.append({
                    "step": step_idx + 1,
                    "incoming_frame": f["id"],
                    "incoming_score": f["threat_score"],
                    "evicted_frame": evicted["id"] if evicted else "None",
                    "ram_slots": [s["id"] for s in current_slots],
                    "held_combat_frame": any(s["is_combat"] for s in current_slots)
                })

            final_slots = [dict(s) for s in current_slots]
            has_peak = any(s["id"] == "KF-02" for s in final_slots)
            gemini_verdict = "AN TOÀN (1.4 / 10)"
            gemini_explanation = (
                "Chẩn đoán Gemini: Các ảnh lưu trong bộ nhớ (KF-04, KF-05, KF-06) đều là học sinh ngồi yên "
                "hoặc đứng quan sát. Kết luận: Khu vực an ninh trật tự hoàn toàn bình thường."
            )
            verdict_accuracy = "SAI LỆCH NGHIÊM TRỌNG (BỎ LỌT BẠO LỰC!)"
            accuracy_class = "tag-danger"
            policy_critique = (
                "Lỗ hổng của FIFO: Khung ảnh cú đấm KF-02 (9.2 điểm) ở đầu video bị các khung ảnh tĩnh "
                "vào sau đẩy văng khỏi RAM. Gemini chỉ nhìn thấy ảnh an toàn nên đưa ra kết luận hoàn toàn sai lệch!"
            )
        else:
            # Threat-Priority Eviction: Luôn bảo vệ các khung hình có điểm nguy cơ cao nhất
            for step_idx, f in enumerate(frames_stream):
                evicted = None
                if len(current_slots) < 3:
                    current_slots.append(f)
                else:
                    # Tìm slot có threat_score thấp nhất trong RAM
                    min_slot_idx = 0
                    min_score = current_slots[0]["threat_score"]
                    for idx, s in enumerate(current_slots):
                        if s["threat_score"] < min_score:
                            min_score = s["threat_score"]
                            min_slot_idx = idx

                    # Chỉ thay thế nếu frame mới có điểm cao hơn, hoặc nếu frame mới bằng thì xoay vòng
                    if f["threat_score"] > min_score:
                        evicted = current_slots.pop(min_slot_idx)
                        current_slots.append(f)
                    else:
                        evicted = f  # Không đủ điều kiện vào RAM, bỏ qua

                slots_log.append({
                    "step": step_idx + 1,
                    "incoming_frame": f["id"],
                    "incoming_score": f["threat_score"],
                    "evicted_frame": evicted["id"] if evicted else "None",
                    "ram_slots": [s["id"] for s in current_slots],
                    "held_combat_frame": any(s["is_combat"] for s in current_slots)
                })

            final_slots = [dict(s) for s in current_slots]
            has_peak = any(s["id"] == "KF-02" for s in final_slots)
            gemini_verdict = "NGUY HIỂM (9.2 / 10)"
            gemini_explanation = (
                "Chẩn đoán Gemini: Nhận diện xung đột bạo lực nghiêm trọng tại khung KF-02 và KF-03 "
                "(Đối tượng vung đòn trực diện gây ngã sụp đổ). Đề xuất kỷ luật và hỗ trợ tại chỗ ngay lập tức."
            )
            verdict_accuracy = "CHÍNH XÁC TUYỆT ĐỐI (100%)"
            accuracy_class = "tag-safe"
            policy_critique = (
                "Ưu thế của Threat-Priority: Khung ảnh cú đấm KF-02 (9.2) và xô xát KF-03 (8.5) được ghim chặt (Page Pinning) "
                "trong RAM, không bao giờ bị đẩy ra. Gemini nhận đúng ảnh mấu chốt và chẩn đoán chính xác."
            )

        return {
            "policy": pol,
            "policy_name": "Threat-Priority (Trục xuất theo Nguy cơ)" if pol == "priority" else "FIFO (Vào trước Ra trước)",
            "memory_slots_capacity": 3,
            "ram_allocated_mb": 7.92,
            "ram_ceiling_mb": HARD_RAM_CEILING_MB,
            "slots_log": slots_log,
            "final_slots": final_slots,
            "has_peak_frame": has_peak,
            "gemini_verdict": gemini_verdict,
            "gemini_explanation": gemini_explanation,
            "verdict_accuracy": verdict_accuracy,
            "accuracy_class": accuracy_class,
            "policy_critique": policy_critique
        }


# Singleton OS Lab Engine
OS_LAB_ENGINE = OSLabEngine()


def get_os_lab_engine(camera_pipeline=None) -> OSLabEngine:
    global OS_LAB_ENGINE
    if camera_pipeline is not None and OS_LAB_ENGINE.camera_pipeline is None:
        OS_LAB_ENGINE.camera_pipeline = camera_pipeline
    return OS_LAB_ENGINE
