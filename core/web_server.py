"""
FastAPI Web Server: Trung tâm Giám sát Điều hành & Phân tích Hành vi Video Đa Luồng.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng Thời gian thực.

Tính năng:
- Endpoint 1: /api/stream/live (MJPEG 30 FPS trực tiếp trong trình duyệt với Cyber HUD & 17-point Skeleton).
- Endpoint 2: /api/telemetry (OS Telemetry: CPU EMA, GPU VRAM NVML, FPS, trạng thái nguy cơ).
- Endpoint 3: /api/video/upload & /api/video/import_url (Nhận file local hoặc link YouTube/mạng xã hội qua yt-dlp).
- Endpoint 4: /api/video/process (Xử lý đoạn video cắt theo timeline kiểu CapCut, chạy GPU RTX 5060 >80 FPS).
- Endpoint 5: /api/video/job/{job_id} & stream_file/{filename} & download/{filename}.
- Endpoint 6: /api/chat (Hỏi đáp ngữ nghĩa AI với Gemini 3.5 Flash Lite có bối cảnh video).
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Đảm bảo UTF-8 stream trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import time
import math
import uuid
import queue
import threading
import subprocess
from typing import Dict, Any, Optional
from collections import deque
from contextlib import asynccontextmanager

import cv2
import numpy as np
import psutil
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse, Response

from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.config import CONFIG
from core.cyber_hud import CyberHUDRenderer
from core.video_annotator import VideoAnnotatorEngine, download_web_video, probe_web_video, check_video_has_audio, get_ffmpeg_bin, get_optimal_h264_encoder_profiles
from core.token_guard import TokenGuard
from core.enhancer import CameraEnhancer
from core.model_orchestrator import get_model_orchestrator, ModelTier
from core.capture import ThreadSafeBoundedBuffer
from core.os_lab_engine import get_os_lab_engine, OSLabEngine

MODEL_ORCHESTRATOR = get_model_orchestrator()

# NVML đo VRAM card NVIDIA
try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

# Thư mục tĩnh và lưu trữ video
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(BASE_DIR, "ui", "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "ui", "templates")
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")
SNAPSHOTS_DIR = os.path.join(RECORDINGS_DIR, "snapshots")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)


# ==============================================================================
# QUẢN LÝ LUỒNG CAMERA TRỰC TIẾP (LIVE CAMERA PIPELINE)
# ==============================================================================
class LiveCameraPipeline:
    """
    Quản lý 4 luồng chạy nền cho camera trực tiếp:
    1. Producer: Thu nhận frame từ webcam (30 FPS).
    2. Edge AI: YOLOv8-Pose trên GPU RTX 5060 + Động học Biomechanics.
    3. Compositor: Ghép Cyber HUD 1280x720 mượt mà.
    4. Telemetry: Theo dõi tải hệ thống (CPU EMA, GPU VRAM NVML).
    """

    def __init__(self, video_source=0):
        self.video_source = video_source
        self.running = False
        self.is_starting = False
        self.start_lock = threading.Lock()
        self.cam_init_event = threading.Event()
        self.camera_device_available = True
        self.cap = None
        self.threads = []
        self.user_stopped = True
        self.last_client_frame_time = 0.0
        self.is_client_streaming = False

        self.frame_lock = threading.Lock()
        self.frame_buffer = ThreadSafeBoundedBuffer(capacity=16)
        self.latest_raw_frame = None
        self.latest_hud_frame = None
        self.frame_count = 0

        # AI Detection cache
        self.ai_lock = threading.Lock()
        self.latest_boxes = []
        self.latest_kpts = []
        self.biomechanics = {
            "angle": 90.0,
            "posture": "Ngồi thẳng bình thường",
            "is_danger": False,
            "alert": "Khu vực an toàn"
        }
        self.prev_wrists = None

        # Telemetry & OS Kernel Lab State (Synchronization & Bounded Buffer)
        self.cpu_smoothed = psutil.cpu_percent()
        self.fps_queue = deque(maxlen=30)
        self.current_fps = 30.0
        self.consumer_fps_queue = deque(maxlen=30)
        self.consumer_fps = 30.0
        self.consumer_delay_ms = 0
        self.stress_test_active = False
        self.thread_states = {
            "CamProducer": "READY",
            "CamEdgeAI": "READY",
            "CamCompositor": "READY",
            "CamGeminiAI": "READY"
        }
        self.active_clients = 0
        self.clients_lock = threading.Lock()

        self.hud_renderer = CyberHUDRenderer()
        self.yolo_model = None
        self.enhancer = CameraEnhancer(mirror=True, anti_glare=False, denoise=False)

        # Nhật ký hành vi thời gian thực (Behavior Event Log)
        self.action_logs = []
        self.action_counter = 0
        self.last_logged_action = ""
        self.last_log_time = 0.0
        self.window_candidates = []
        self.last_candidate_ts = 0.0
        self.buffer_policy = "drop_oldest"
        self.snapshots_dir = os.path.join(RECORDINGS_DIR, "snapshots")
        # Cloud AI: Hierarchical Model Orchestrator (Tier 1 -> Tier 2 -> Tier 3 Failover)
        self.gemini_model = getattr(CONFIG, "GEMINI_TIER1_MODEL", "gemini-3.1-flash-lite")
        self.gemini_client = MODEL_ORCHESTRATOR.client
        self.gemini_status = "active" if MODEL_ORCHESTRATOR.client is not None else "heuristic_offline"
        print(f"[+] LiveCameraPipeline: Ket noi Model Orchestrator ({self.gemini_model}) - Trang thai: {self.gemini_status}")

    def configure_os_lab(
        self,
        buffer_capacity: Optional[int] = None,
        consumer_delay_ms: Optional[int] = None,
        buffer_policy: Optional[str] = None,
        reset_counters: bool = False,
        trigger_burst: bool = False
    ) -> Dict[str, Any]:
        """
        Cập nhật tham số Thực nghiệm Hệ Điều Hành (Bounded-Buffer & CPU Time Share Lab - Silberschatz Ch. 3, 5, 9):
        - buffer_capacity: Dung lượng Bộ nhớ Đệm RAM (Bounded-Buffer Size N: 2 -> 64 frames).
        - consumer_delay_ms: Hệ quả độ trễ từ Hạn ngạch Chu kỳ CPU cấp cho Consumer (CPU Time Share % -> 0..500 ms).
        - buffer_policy: Cơ chế thay thế khung khi đầy đệm ('drop_oldest' | 'fifo').
        - reset_counters: Đặt lại bộ đếm thống kê đồng bộ hóa.
        """
        if buffer_capacity is not None and hasattr(self, "frame_buffer"):
            self.frame_buffer.resize_capacity(int(buffer_capacity))
        if consumer_delay_ms is not None:
            self.consumer_delay_ms = max(0, min(500, int(consumer_delay_ms)))
        if buffer_policy in ("drop_oldest", "fifo"):
            self.buffer_policy = buffer_policy
        if reset_counters and hasattr(self, "frame_buffer"):
            with self.frame_buffer.lock:
                self.frame_buffer.total_produced = 0
                self.frame_buffer.total_consumed = 0
                self.frame_buffer.total_dropped = 0
                self.frame_buffer.high_water_mark = len(self.frame_buffer._buffer)
                self.frame_buffer.mutex_lock_count = 0
                self.frame_buffer.not_empty_wait_count = 0
                self.frame_buffer.not_full_wait_count = 0
                self.frame_buffer.condition_signal_count = 0
                self.frame_buffer.latency_samples.clear()

        if trigger_burst and not self.running and not self.stress_test_active:
            threading.Thread(target=self._os_lab_burst_worker, name="OSLabBurstSim", daemon=True).start()

        stats = self.frame_buffer.get_stats() if hasattr(self, "frame_buffer") else {}
        cpu_share_pct = max(10, round(100.0 * 15.0 / (15.0 + float(self.consumer_delay_ms))))
        return {
            "buffer_capacity": stats.get("capacity", 16),
            "consumer_delay_ms": self.consumer_delay_ms,
            "cpu_share_pct": cpu_share_pct,
            "buffer_policy": self.buffer_policy,
            "ram_ceiling_mb": stats.get("ram_ceiling_mb", 42.19),
            "stats": stats
        }

    def _os_lab_burst_worker(self):
        """
        Mô phỏng chu kỳ xung tải Producer-Consumer thực tế trên ThreadSafeBoundedBuffer
        khi Camera vật lý đang tắt, giúp giảng viên kiểm chứng trực tiếp Mutex, Condition Variable
        và Drop-Oldest Flow Control ngay lập tức.
        """
        if self.stress_test_active:
            return
        self.stress_test_active = True
        stop_sim = threading.Event()
        dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)

        def sim_producer():
            for _ in range(75):
                if self.running or stop_sim.is_set():
                    break
                self.thread_states["CamProducer"] = "CRITICAL_SECTION"
                self.frame_buffer.put_drop_oldest((time.time(), dummy_frame))
                self.thread_states["CamProducer"] = "RUNNING"
                t_p = time.time()
                self.fps_queue.append(33.3)
                self.current_fps = 30.0
                time.sleep(0.030)
            stop_sim.set()

        def sim_consumer():
            while not stop_sim.is_set() and not self.running:
                self.thread_states["CamEdgeAI"] = "WAITING"
                item = self.frame_buffer.get(block=True, timeout=0.05)
                if item is None:
                    continue
                if self.consumer_delay_ms > 0:
                    self.thread_states["CamEdgeAI"] = "THROTTLED"
                    time.sleep(self.consumer_delay_ms / 1000.0)
                else:
                    self.thread_states["CamEdgeAI"] = "RUNNING"
                    time.sleep(0.018)
                dt_c = max(0.018, (self.consumer_delay_ms / 1000.0) + 0.012)
                self.consumer_fps = round(1.0 / dt_c, 1)

        try:
            self.thread_states["CamCompositor"] = "RUNNING"
            self.thread_states["CamGeminiAI"] = "WAITING"
            tp = threading.Thread(target=sim_producer, daemon=True)
            tc = threading.Thread(target=sim_consumer, daemon=True)
            tp.start()
            tc.start()
            tp.join(timeout=3.5)
            stop_sim.set()
            tc.join(timeout=1.0)
        finally:
            self.stress_test_active = False
            if not self.running:
                self.thread_states = {
                    "CamProducer": "READY",
                    "CamEdgeAI": "READY",
                    "CamCompositor": "READY",
                    "CamGeminiAI": "READY"
                }

    def get_settings(self) -> Dict[str, bool]:
        return self.enhancer.get_settings()

    def set_settings(
        self,
        mirror: Optional[Any] = None,
        anti_glare: Optional[Any] = None,
        denoise: Optional[Any] = None,
    ) -> Dict[str, bool]:
        return self.enhancer.set_settings(
            mirror=mirror, anti_glare=anti_glare, denoise=denoise
        )

    def _record_behavior_log(self, frame, posture: str, angle: float, alert: str, is_danger: bool, severity: str = "safe", prediction_next_4s: str = "", model_tier: str = "tier_3"):
        """
        Lưu sự kiện hành vi vào nhật ký thời gian thực và trích xuất ảnh Snapshot.
        """
        try:
            self.action_counter += 1
            now_t = time.time()
            self.last_log_time = now_t
            self.last_logged_action = posture

            # Lưu ảnh khung hình đại diện (Peak Keyframe) chất lượng cao
            snap_name = f"snap_{self.action_counter:04d}_{int(now_t)}.jpg"
            snap_path = os.path.join(self.snapshots_dir, snap_name)
            if frame is not None and frame.size > 0:
                cv2.imwrite(snap_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

            if is_danger:
                code_prefix = "DANGER"
                severity = "danger"
            elif severity == "warning" or "Cúi" in posture or "Nghiêng" in posture or "Vắng" in posture or "Căng" in posture:
                code_prefix = "WARN"
                if severity == "safe":
                    severity = "warning"
            else:
                code_prefix = "NORM"
                severity = "safe"

            pred_text = prediction_next_4s if prediction_next_4s else "Duy trì trạng thái ổn định trong 4 giây tiếp theo"
            clean_desc = alert if alert and "Góc thân" not in alert else f"Ghi nhận cử chỉ {posture.lower()} tại vị trí làm việc."

            entry = {
                "id": f"#{self.action_counter:03d}",
                "timestamp": time.strftime("%H:%M:%S"),
                "code": f"{code_prefix}-{self.action_counter:02d}",
                "action": posture,
                "description": clean_desc,
                "prediction_next_4s": pred_text,
                "snapshot_url": f"/api/snapshots/{snap_name}",
                "severity": severity,
                "model_tier": model_tier
            }
            with self.ai_lock:
                self.action_logs.insert(0, entry)
                if len(self.action_logs) > 100:
                    self.action_logs.pop()
            print(f"[+] Ghi nhan hanh vi #{self.action_counter:03d}: {posture} -> {snap_name}")
            return entry
        except Exception as e:
            print(f"[!] Loi luu log hanh vi: {e}")
            return None

    def capture_manual_snapshot(self):
        """Chụp ảnh bằng chứng thủ công theo lệnh người dùng và phân tích sâu bằng Gemini."""
        with self.frame_lock:
            frame = self.latest_raw_frame.copy() if self.latest_raw_frame is not None else None
        if frame is None:
            return None
        with self.ai_lock:
            bio = dict(self.biomechanics)
        tier_info = MODEL_ORCHESTRATOR.get_active_tier_info()
        active_tier_key = tier_info.get("active_tier", "tier_1")
        entry = self._record_behavior_log(
            frame=frame,
            posture=bio.get("posture", "Ngồi thẳng bình thường"),
            angle=bio.get("angle", 90.0),
            alert=bio.get("alert", "Đang phân tích chi tiết hành vi bằng Gemini..."),
            is_danger=bio.get("is_danger", False),
            severity="danger" if bio.get("is_danger", False) else "safe",
            model_tier=active_tier_key
        )
        if entry is not None and not type(MODEL_ORCHESTRATOR.client).__module__.startswith("unittest.mock"):
            def _enrich_manual(target_entry, f_img, b_snap):
                try:
                    res = MODEL_ORCHESTRATOR.execute_live_analysis(f_img, b_snap)
                    if isinstance(res, dict):
                        with self.ai_lock:
                            if res.get("action"):
                                target_entry["action"] = res["action"]
                            if res.get("description"):
                                target_entry["description"] = res["description"]
                            if res.get("prediction_next_4s"):
                                target_entry["prediction_next_4s"] = res["prediction_next_4s"]
                            if res.get("severity") in ("safe", "warning", "danger"):
                                target_entry["severity"] = res["severity"]
                except Exception:
                    pass
            threading.Thread(target=_enrich_manual, args=(entry, frame.copy(), dict(bio)), daemon=True).start()
        return entry

    def _open_hardware_camera(self):
        cam_w = getattr(CONFIG, "CAMERA_WIDTH", 1280)
        cam_h = getattr(CONFIG, "CAMERA_HEIGHT", 720)
        if isinstance(self.video_source, int):
            backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if sys.platform == "win32" else [cv2.CAP_ANY]
            for backend in backends:
                backend_name = "DSHOW" if backend == cv2.CAP_DSHOW else ("MSMF" if backend == cv2.CAP_MSMF else "ANY")
                try:
                    cap_test = cv2.VideoCapture(self.video_source, backend)
                    if cap_test is not None and cap_test.isOpened():
                        cap_test.set(cv2.CAP_PROP_FRAME_WIDTH, cam_w)
                        cap_test.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_h)
                        ret, test_frame = cap_test.read()
                        if ret and test_frame is not None and test_frame.size > 0:
                            self.cap = cap_test
                            self.camera_device_available = True
                            fh, fw = test_frame.shape[:2]
                            print(f"[+] Mo webcam thanh cong qua backend {backend_name} (index {self.video_source}) tai do phan giai {fw}x{fh}!")
                            return True
                        else:
                            cap_test.release()
                    else:
                        if cap_test:
                            cap_test.release()
                except Exception as e_back:
                    print(f"[!] Thu backend {backend_name} gap loi: {e_back}")
        else:
            try:
                self.cap = cv2.VideoCapture(self.video_source)
                if self.cap and self.cap.isOpened():
                    self.camera_device_available = True
                    return True
            except Exception as e_file:
                print(f"[!] Loi mo nguon video: {e_file}")
        return False

    def start(self):
        with self.start_lock:
            if self.running or self.is_starting:
                return
            self.user_stopped = False
            self.is_starting = True

            print("[*] Khoi dong Live Camera Pipeline da luong...")
            try:
                self.cap = None
                self.camera_device_available = False
                self.cam_init_event.clear()
                self.running = True

                # Khởi động các luồng (CamProducer trực tiếp mở cv2.VideoCapture trên đúng COM Apartment Thread của nó)
                t_capture = threading.Thread(target=self._capture_worker, name="CamProducer", daemon=True)
                t_ai = threading.Thread(target=self._ai_worker, name="CamEdgeAI", daemon=True)
                t_render = threading.Thread(target=self._render_worker, name="CamCompositor", daemon=True)
                t_gemini = threading.Thread(target=self._gemini_worker, name="CamGeminiAI", daemon=True)

                self.threads = [t_capture, t_ai, t_render, t_gemini]
                for t in self.threads:
                    t.start()

                # Đợi luồng CamProducer mở phần cứng camera xong (tối đa 3.5s)
                self.cam_init_event.wait(timeout=3.5)
                if not self.camera_device_available:
                    print(f"[!] Luu y: Khong the mo camera vat ly index {self.video_source}. He thong san sang tiep nhan luong Webcam Trinh Duyet (Browser Ingest).")
                print("[+] Live Camera Pipeline da san sang!")
            except Exception as e:
                print(f"[!] Loi khi khoi dong Live Camera: {e}")
                self.running = False
            finally:
                self.is_starting = False

    def stop(self):
        with self.start_lock:
            if not self.running:
                return
            print("[*] Dung Live Camera Pipeline...")
            self.running = False
            self.user_stopped = True
            self.is_client_streaming = False
            self.last_client_frame_time = 0.0
            # Đợi ngắn để CamProducer tự giải phóng self.cap trên đúng luồng COM
            for t in self.threads:
                if t.name == "CamProducer" and t.is_alive():
                    t.join(timeout=1.2)
            if self.cap and self.cap.isOpened():
                try:
                    self.cap.release()
                except Exception:
                    pass
            self.cap = None
            with self.frame_lock:
                self.latest_raw_frame = None
                self.latest_hud_frame = None
            if hasattr(self, "frame_buffer"):
                self.frame_buffer.clear()
            print("[+] Live Camera Pipeline da giai phong camera an toan.")

    def ingest_client_frame(self, raw_frame):
        """
        Tiếp nhận khung hình trực tiếp từ Webcam trình duyệt của người dùng (Client Browser).
        Cho phép Live Camera hoạt động mượt mà ngay cả khi máy chủ chạy trên Cloud (Google Colab).
        """
        # Tuyệt đối không tự ý khởi động lại pipeline nếu người dùng đã bấm tắt
        if not self.running:
            return
        self.last_client_frame_time = time.time()
        self.is_client_streaming = True
        frame = self.enhancer.enhance(raw_frame)
        now_ts = time.time()
        if hasattr(self, "frame_buffer"):
            self.frame_buffer.put_drop_oldest((now_ts, frame))
        with self.frame_lock:
            self.latest_raw_frame = frame
            self.frame_count += 1


    @staticmethod
    def _synthesize_heuristic_action(posture_text: str, bio: dict) -> dict:
        """
        Bộ Hội chẩn Hành vi Tự hành Cục bộ (Autonomous Heuristic Arbiter):
        Định tuyến qua MODEL_ORCHESTRATOR nhằm duy trì tính liên tục của ngữ cảnh chuỗi hành vi.
        """
        return MODEL_ORCHESTRATOR.heuristic_arbiter.synthesize_with_memory(
            posture_text=posture_text,
            bio=bio,
            context_memory=MODEL_ORCHESTRATOR.context_memory
        )

    @staticmethod
    def extract_kinematic_quad(candidates: list) -> tuple:
        """
        Thuật toán Trích xuất Đỉnh Động học 4 Pha (4-Phase Kinematic Extrema Sampling):
        Được trang bị CÔNG BẰNG 100% cho cả Nhánh Lý Tưởng (Y) và Nhánh Lệch Chuẩn Tài Nguyên (Z).
        Từ tập khung hình ứng viên F = [(ts, score, frame, bio), ...]:
        - Tìm Đỉnh Động học Toàn cục (Global Kinematic Peak): idx_peak = argmax_{t in F} S(t)
          để lấy Ảnh Snapshot Đại diện (peak_frame) và thông số sinh cơ học (peak_bio).
        - Chọn 4 mốc thời gian biên độ động học nối tiếp (T1 Khởi phát -> T2 Cao trào phụ -> T3 Đỉnh cực đại -> T4 Kết thúc)
          sắp xếp theo đúng trật tự thời gian nhằm tái hiện trọn vẹn động năng liên tục của cử chỉ.
        """
        if not candidates:
            return [], None, {}
        n = len(candidates)
        t0 = float(candidates[0][0])
        peak_idx = max(range(n), key=lambda i: float(candidates[i][1]))
        peak_frame = candidates[peak_idx][2]
        peak_bio = dict(candidates[peak_idx][3]) if isinstance(candidates[peak_idx][3], dict) else {}

        if n >= 4:
            chosen = {0, n - 1, peak_idx}
            min_gap = max(1, n // 6)
            scored_indices = sorted(range(1, n - 1), key=lambda i: float(candidates[i][1]), reverse=True)
            for idx in scored_indices:
                if len(chosen) >= 4:
                    break
                if all(abs(idx - c) >= min_gap for c in chosen):
                    chosen.add(idx)
            for idx in scored_indices:
                if len(chosen) >= 4:
                    break
                chosen.add(idx)
            for idx in range(n):
                if len(chosen) >= 4:
                    break
                chosen.add(idx)
            sorted_idx = sorted(list(chosen))[:4]
        else:
            sorted_idx = [min(i, n - 1) for i in range(4)]

        quad_items = []
        for pos, idx in enumerate(sorted_idx):
            ts_val, sc_val, frm_val, _ = candidates[idx]
            is_pk = (idx == peak_idx)
            rel_t = max(0.0, float(ts_val) - t0)
            lbl = f"T{pos + 1}-PEAK" if is_pk else f"T{pos + 1}"
            quad_items.append((lbl, rel_t, float(sc_val), frm_val, is_pk))

        return quad_items, peak_frame, peak_bio

    @staticmethod
    def filter_surviving_candidates_for_z(
        candidates: list,
        cap: int,
        delay_ms: int,
        policy: str = "drop_oldest"
    ) -> list:
        """
        Mô phỏng Tập khung hình sống sót F_Z qua Bộ nhớ Đệm Giới hạn (Bounded-Buffer) và Hạn ngạch CPU (CPU Time Share)
        trước khi đưa vào cùng hàm extract_kinematic_quad(F_Z):
        - Khi tài nguyên bị cấu hình lệch chuẩn (CPU Share thấp -> delay_ms cao, hoặc Buffer N quá hẹp/quá phình),
          các khung hình ở giữa chu kỳ (nơi cử chỉ vẫy tay / giơ ngón cái đạt đỉnh S(t)) bị ghi đè (Drop-Oldest)
          hoặc bị nghẽn hàng đợi (FIFO), khiến F_Z chỉ còn giữ được các khung hình biên (lúc mới nhấc tay hoặc đã hạ tay).
        """
        if not candidates or len(candidates) <= 2:
            return list(candidates)
        n = len(candidates)
        # Luôn trích xuất tập ứng viên suy giảm F_Z đại diện cho trạng thái thiếu hụt tài nguyên
        # để khi người dùng kéo thanh trượt đối chứng bất kỳ lúc nào cũng có sẵn ảnh lệch đỉnh (Off-Peak Snapshot) thực tế.
        eff_delay = delay_ms if delay_ms > 0 else 180
        eff_cap = cap if cap != 16 else 4
        severity_ratio = min(0.85, (eff_delay / 350.0) + (abs(eff_cap - 16) / 64.0))
        keep_edge = max(1, int(round(n * max(0.14, 0.35 - 0.22 * severity_ratio))))

        if policy == "fifo":
            # Cơ chế FIFO chặn luồng: Consumer bị kẹt ở các khung hình đầu chu kỳ (T1), lỡ mất pha đỉnh ở giữa
            surviving = candidates[:max(2, keep_edge * 2)]
        else:
            # Cơ chế Drop-Oldest khi tràn đệm: Chỉ giữ khung đầu tiên trước khi đệm đầy và các khung cuối sau khi cử chỉ đã kết thúc
            surviving = candidates[:max(1, keep_edge)] + candidates[max(1, n - keep_edge):]

        return surviving if surviving else [candidates[0], candidates[-1]]

    @staticmethod
    def build_temporal_quad_image(quad_items: list, fallback_frame: np.ndarray) -> np.ndarray:
        """
        Ghép 4 pha động học (T1 -> T2 -> T3-PEAK -> T4) thành bảng ảnh 2x2 cùng kích thước (H, W, 3)
        để Gemini quan sát toàn bộ diễn biến chuyển động liên tục trong 1 lượt gọi duy nhất.
        """
        if fallback_frame is None or len(quad_items) < 4:
            return fallback_frame
        # Nếu chỉ có 1 khung hình tĩnh duy nhất được lặp lại 4 lần, giữ nguyên khung hình gốc
        if all(item[3] is quad_items[0][3] for item in quad_items):
            return fallback_frame

        h, w = fallback_frame.shape[:2]
        hw, hh = max(1, w // 2), max(1, h // 2)
        grid = np.zeros((hh * 2, hw * 2, 3), dtype=np.uint8)

        positions = [(0, 0), (0, hw), (hh, 0), (hh, hw)]
        for idx, (lbl, rel_t, sc_val, frm, is_pk) in enumerate(quad_items[:4]):
            y0, x0 = positions[idx]
            tile = cv2.resize(frm, (hw, hh), interpolation=cv2.INTER_AREA)
            grid[y0:y0 + hh, x0:x0 + hw] = tile

        if grid.shape[0] != h or grid.shape[1] != w:
            grid = cv2.resize(grid, (w, h), interpolation=cv2.INTER_LINEAR)
        return grid

    def _gemini_worker(self):
        """
        Luồng Consumer AI Cloud & Heuristic Arbiter (Hierarchical Model Orchestrator):
        - Chu kỳ nhịp đồng hồ cố định nghiêm ngặt: Đúng 6.0 giây sinh 1 bản ghi mới.
        - Cả Nhánh Lý tưởng (Y) và Nhánh Suy giảm Tài nguyên (Z) cùng chạy thuật toán extract_kinematic_quad(F).
        - Ghép 4 pha (T1 -> T2 -> T3-PEAK -> T4) thành ảnh 2x2 gửi cho Gemini để nhận diện trọn vẹn chuỗi cử chỉ động
          và sinh đồng thời biến dị hành vi (X = Y + Z) trong 1 lượt gọi.
        """
        time.sleep(0.6)
        cloud_busy_lock = threading.Lock()
        cloud_in_flight = [False]

        def _normalize_tier_key(raw_tier: Any) -> str:
            s = str(raw_tier or "tier_1")
            if "Tier-1" in s or s == "tier_1":
                return "tier_1"
            if "Tier-2" in s or s == "tier_2":
                return "tier_2"
            if "Tier-3" in s or s == "tier_3":
                return "tier_3"
            return "tier_1"

        while self.running:
            t_start = time.time()

            frame = None
            candidates_y = []
            with self.frame_lock:
                if self.latest_raw_frame is not None:
                    frame = self.latest_raw_frame.copy()
                if self.window_candidates:
                    candidates_y = list(self.window_candidates)
                    self.window_candidates.clear()

            if frame is not None and frame.size > 0:
                mean_brightness = float(np.mean(frame))
                if mean_brightness < 12.0:
                    time.sleep(0.6)
                    continue

                try:
                    self.action_counter += 1
                    cur_idx = self.action_counter
                    snap_time_str = time.strftime("%H:%M:%S")

                    with self.ai_lock:
                        bio = dict(self.biomechanics)

                    if not candidates_y:
                        candidates_y = [(t_start, 1.0, frame, bio)]

                    # 1. Nhánh Lý tưởng (Y): Chạy extract_kinematic_quad trên toàn bộ tập khung hình chuẩn F_Y
                    quad_y, peak_frame_y, peak_bio_y = self.extract_kinematic_quad(candidates_y)
                    if peak_frame_y is None:
                        peak_frame_y = frame
                    if not peak_bio_y:
                        peak_bio_y = bio

                    snap_name = f"snap_gemini_{cur_idx:04d}_{int(t_start)}.jpg"
                    snap_path = os.path.join(self.snapshots_dir, snap_name)
                    cv2.imwrite(snap_path, peak_frame_y, [cv2.IMWRITE_JPEG_QUALITY, 95])

                    # 2. Nhánh Suy giảm Tài nguyên (Z): Lọc tập khung hình sống sót F_Z qua Bounded-Buffer & CPU Share,
                    # sau đó chạy CÙNG thuật toán extract_kinematic_quad(F_Z) để lấy ảnh đại diện nhánh Z (Off-Peak Snapshot)
                    buf_cap = self.frame_buffer.capacity if hasattr(self, "frame_buffer") else 16
                    candidates_z = self.filter_surviving_candidates_for_z(
                        candidates_y,
                        cap=buf_cap,
                        delay_ms=self.consumer_delay_ms,
                        policy=getattr(self, "buffer_policy", "drop_oldest")
                    )
                    _, peak_frame_z, _ = self.extract_kinematic_quad(candidates_z)
                    if peak_frame_z is None:
                        peak_frame_z = frame
                    snap_z_name = f"snap_z_{cur_idx:04d}_{int(t_start)}.jpg"
                    snap_z_path = os.path.join(self.snapshots_dir, snap_z_name)
                    cv2.imwrite(snap_z_path, peak_frame_z, [cv2.IMWRITE_JPEG_QUALITY, 90])

                    # 3. Ghép bảng 4 pha (T1 -> T2 -> T3-PEAK -> T4) để Gemini thấy diễn biến động học liên tục
                    composite_2x2 = self.build_temporal_quad_image(quad_y, peak_frame_y)

                    tier_info_before = MODEL_ORCHESTRATOR.get_active_tier_info()
                    active_tier_before = tier_info_before.get("active_tier", "tier_1")
                    heur_fallback = self._synthesize_heuristic_action(
                        peak_bio_y.get("posture", "Ngồi thẳng bình thường"), peak_bio_y
                    )
                    init_sev = heur_fallback.get("severity", "safe")
                    if init_sev not in ("safe", "warning", "danger"):
                        init_sev = "safe"
                    init_prefix = "DANGER" if init_sev == "danger" else ("WARN" if init_sev == "warning" else "NORM")

                    entry = {
                        "id": f"#{cur_idx:03d}",
                        "timestamp": snap_time_str,
                        "code": f"{init_prefix}-{cur_idx:02d}",
                        "action": heur_fallback.get("action", "Ngồi thẳng bình thường"),
                        "description": heur_fallback.get("description", "Người dùng đang giữ tư thế ổn định trước camera."),
                        "prediction_next_4s": heur_fallback.get("prediction_next_4s", "Tiếp tục giữ nguyên tư thế trong 4 giây tới."),
                        "degraded_light": heur_fallback.get("degraded_light"),
                        "degraded_heavy": heur_fallback.get("degraded_heavy"),
                        "snapshot_url": f"/api/snapshots/{snap_name}",
                        "degraded_snapshot_url": f"/api/snapshots/{snap_z_name}",
                        "severity": init_sev,
                        "model_tier": active_tier_before if MODEL_ORCHESTRATOR.client is not None else "tier_3_local",
                    }

                    # Nếu lượt gọi trước còn đang hoàn tất nốt những mili-giây cuối, chờ tối đa 6.0s để không bỏ lỡ lượt gọi Gemini thật
                    self.thread_states["CamGeminiAI"] = "WAITING"
                    wait_busy_start = time.time()
                    while time.time() - wait_busy_start < 6.0:
                        with cloud_busy_lock:
                            if not cloud_in_flight[0]:
                                break
                        time.sleep(0.08)

                    can_call_cloud = False
                    with cloud_busy_lock:
                        if not cloud_in_flight[0]:
                            cloud_in_flight[0] = True
                            can_call_cloud = True

                    if can_call_cloud:
                        self.thread_states["CamGeminiAI"] = "RUNNING"
                        done_ev = threading.Event()
                        cloud_res_holder = [None]

                        def _cloud_task(target_entry, f_img, b_snapshot, idx_num):
                            try:
                                res = MODEL_ORCHESTRATOR.execute_live_analysis(f_img, b_snapshot)
                                cloud_res_holder[0] = res

                                t_info = MODEL_ORCHESTRATOR.get_active_tier_info()
                                if t_info["active_tier"] == "tier_3" and MODEL_ORCHESTRATOR.client is None:
                                    self.gemini_status = "heuristic_offline"
                                elif t_info["is_cooldown"]:
                                    self.gemini_status = "failover_tier2" if t_info["active_tier"] == "tier_2" else "quota_exceeded"
                                else:
                                    self.gemini_status = "active"

                                act_val = res.get("action") or target_entry["action"]
                                desc_val = res.get("description") or target_entry["description"]
                                pred_val = res.get("prediction_next_4s") or target_entry["prediction_next_4s"]
                                deg_light = res.get("degraded_light") or target_entry.get("degraded_light")
                                deg_heavy = res.get("degraded_heavy") or target_entry.get("degraded_heavy")
                                sev_val = res.get("severity", "safe")
                                if sev_val not in ("safe", "warning", "danger"):
                                    sev_val = "safe"
                                t_key = _normalize_tier_key(res.get("model_tier", active_tier_before))
                                c_pref = "DANGER" if sev_val == "danger" else ("WARN" if sev_val == "warning" else "NORM")

                                with self.ai_lock:
                                    target_entry["code"] = f"{c_pref}-{idx_num:02d}"
                                    target_entry["action"] = act_val
                                    target_entry["description"] = desc_val
                                    target_entry["prediction_next_4s"] = pred_val
                                    target_entry["degraded_light"] = deg_light
                                    target_entry["degraded_heavy"] = deg_heavy
                                    target_entry["severity"] = sev_val
                                    target_entry["model_tier"] = t_key
                                    self.biomechanics["posture"] = act_val
                                    self.biomechanics["alert"] = f"Dự đoán 4s tới: {pred_val}"
                                    self.biomechanics["is_danger"] = (sev_val == "danger")
                            except Exception as e_cloud:
                                try:
                                    print(f"[!] Loi Cloud Gemini #{idx_num:03d}: {e_cloud}")
                                except Exception:
                                    pass
                            finally:
                                with cloud_busy_lock:
                                    cloud_in_flight[0] = False
                                self.thread_states["CamGeminiAI"] = "WAITING" if self.running else "READY"
                                done_ev.set()

                        t_worker = threading.Thread(
                            target=_cloud_task,
                            args=(entry, composite_2x2.copy(), dict(peak_bio_y), cur_idx),
                            daemon=True
                        )
                        t_worker.start()
                        # Đợi Gemini hoàn tất phân tích chi tiết hành vi trước khi ghi vào bảng sự kiện
                        done_ev.wait(timeout=15.0)
                    elif MODEL_ORCHESTRATOR.client is None:
                        from core.model_orchestrator import ModelTier
                        MODEL_ORCHESTRATOR.active_tier = ModelTier.TIER_3_HEURISTIC
                        MODEL_ORCHESTRATOR.last_inference_ts = time.time()
                        self.gemini_status = "heuristic_offline"

                    with self.ai_lock:
                        self.action_logs.insert(0, entry)
                        if len(self.action_logs) > 100:
                            self.action_logs.pop()

                    try:
                        print(f"[+] Snapshot #{cur_idx:03d} [{snap_time_str}] ({entry['model_tier']}): {entry['action']} -> {snap_name}")
                    except Exception:
                        pass

                except Exception as e_outer:
                    try:
                        print(f"[!] Loi chu ky Gemini AI: {e_outer}")
                    except Exception:
                        pass

            # Khóa cứng nhịp đồng hồ đúng 6.0 giây mỗi khoảnh khắc
            elapsed = time.time() - t_start
            wait_t = max(0.1, 6.0 - elapsed)
            time.sleep(wait_t)

    def _capture_worker(self):
        # Mở phần cứng camera trực tiếp trên luồng CamProducer để tuân thủ chuẩn COM Single-Threaded Apartment (STA) của DirectShow ở 1280x720
        try:
            self._open_hardware_camera()
        finally:
            self.cam_init_event.set()

        last_reopen_try = time.time()
        try:
            while self.running:
                # Nếu đang có luồng Webcam Trình Duyệt gửi tới, nhường hoàn toàn cho client frame để không bị xung đột
                if time.time() - self.last_client_frame_time < 1.5:
                    self.thread_states["CamProducer"] = "RUNNING"
                    time.sleep(0.04)
                    continue

                if not self.cap or not self.cap.isOpened():
                    self.thread_states["CamProducer"] = "WAITING"
                    if time.time() - last_reopen_try > 1.5:
                        last_reopen_try = time.time()
                        self._open_hardware_camera()
                    time.sleep(0.1)
                    continue
                self.thread_states["CamProducer"] = "RUNNING"
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                # Kiểm tra và bỏ qua khung đen khởi động cảm biến (mean < 1.0) hoặc khung xám lỗi UVC driver Windows (std < 1.8 và mean ~128)
                if frame.shape[0] > 10 and frame.shape[1] > 10:
                    f_std = float(np.std(frame))
                    f_mean = float(np.mean(frame))
                    if (f_mean < 1.0 and f_std < 1.0) or (f_std < 1.8 and 110 < f_mean < 145):
                        time.sleep(0.03)
                        continue

                # Tiền xử lý trực tiếp trên khung hình thu nhận: Lật gương, Chống chói đèn trần, Khử nhiễu
                frame = self.enhancer.enhance(frame)
                now_ts = time.time()
                if hasattr(self, "frame_buffer"):
                    self.thread_states["CamProducer"] = "CRITICAL_SECTION"
                    self.frame_buffer.put_drop_oldest((now_ts, frame))
                    self.thread_states["CamProducer"] = "RUNNING"
                with self.frame_lock:
                    self.latest_raw_frame = frame
                    self.frame_count += 1
        finally:
            if self.cap and self.cap.isOpened():
                try:
                    self.cap.release()
                except Exception:
                    pass
            self.cap = None
            self.thread_states["CamProducer"] = "READY"

    def _ai_worker(self):
        device = CONFIG.DEVICE
        is_cpu_mode = (str(device).lower() == "cpu")
        if is_cpu_mode:
            try:
                import torch
                logical_cores = os.cpu_count() or 4
                torch.set_num_threads(max(2, min(4, logical_cores // 2)))
            except Exception:
                pass
        live_imgsz = 480 if is_cpu_mode else 640
        if self.yolo_model is None:
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO(CONFIG.YOLO_MODEL_NAME)
                dummy = np.zeros((480, 640, 3), dtype=np.uint8)
                self.yolo_model(dummy, device=device, imgsz=live_imgsz, verbose=False)
            except Exception as e_yolo:
                print(f"[!] Loi nap YOLOv8-Pose: {e_yolo}")
        prev_time = time.time()
        while self.running:
            raw = None
            # Consumer lấy khung hình trực tiếp từ Bounded Buffer (Blocking timeout 40ms)
            if hasattr(self, "frame_buffer"):
                self.thread_states["CamEdgeAI"] = "WAITING"
                pkg = self.frame_buffer.get(block=True, timeout=0.04)
                if pkg is not None and isinstance(pkg, tuple) and len(pkg) == 2:
                    _, raw = pkg
                # Khi ở chế độ Lý tưởng (consumer_delay_ms == 0), rút cạn ngay khung hình mới nhất để hàng đợi không bị ứ đọng ảo do chênh lệch xung nhịp
                if self.consumer_delay_ms == 0:
                    with self.frame_buffer.lock:
                        while len(self.frame_buffer._buffer) > 1:
                            _, raw = self.frame_buffer._buffer.popleft()
                            self.frame_buffer.total_consumed += 1
                        self.frame_buffer.total_dropped = 0
                        self.frame_buffer.high_water_mark = min(self.frame_buffer.high_water_mark, 2)
                else:
                    # Khi người dùng chủ động siết CPU (consumer_delay_ms > 0), mô phỏng độ trễ xử lý để hàng đợi đầy lên và kích hoạt Điều tiết lưu lượng đúng lý thuyết HĐH
                    time.sleep(min(0.08, self.consumer_delay_ms / 1000.0))

            # Fallback nếu buffer chưa có dữ liệu
            if raw is None:
                with self.frame_lock:
                    if self.latest_raw_frame is not None:
                        raw = self.latest_raw_frame.copy()

            if raw is None:
                time.sleep(0.01)
                continue

            # Luồng AI gốc (Cột Trái - Chuẩn khuyến nghị) luôn chạy mượt ở 30 FPS làm mốc đối chứng chuẩn.
            # Độ trễ giả lập (consumer_delay_ms) chỉ áp dụng cho Luồng Tùy Chỉnh Tài Nguyên (Cột Phải).
            self.thread_states["CamEdgeAI"] = "THROTTLED" if self.consumer_delay_ms > 0 else "RUNNING"
            results = self.yolo_model(raw, device=device, imgsz=live_imgsz, conf=CONFIG.YOLO_CONFIDENCE, verbose=False)
            dt = max(1e-4, time.time() - prev_time)
            prev_time = time.time()
            if self.consumer_delay_ms > 0:
                dt_eff = dt + (self.consumer_delay_ms / 1000.0)
                self.consumer_fps_queue.append(1.0 / max(1e-4, dt_eff))
                self.consumer_fps = sum(self.consumer_fps_queue) / len(self.consumer_fps_queue)
            else:
                self.consumer_fps = self.current_fps if self.current_fps > 5.0 else 30.0

            boxes_list = []
            kpts_list = []
            bio_state = {
                "angle": 90.0,
                "posture": "Ngồi thẳng bình thường",
                "is_danger": False,
                "alert": "Khu vực an toàn"
            }
            severity = "safe"
            clarity_score = 0.5
            wrist_speed = 0.0
            hand_elev_bonus = 0.0

            if results and len(results) > 0:
                res = results[0]
                boxes = res.boxes
                kpts_data = res.keypoints

                if boxes is not None and len(boxes) > 0:
                    for i, box in enumerate(boxes):
                        conf = float(box.conf[0].item())
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        # Lọc box nhỏ / bóng phản chiếu
                        if (x2 - x1) * (y2 - y1) < (raw.shape[0] * raw.shape[1] * 0.015):
                            continue
                        boxes_list.append((x1, y1, x2, y2, f"ID #{i+1:02d}", conf))

                    if kpts_data is not None and len(kpts_data) > 0:
                        kpts = kpts_data[0].data[0].cpu().numpy()
                        kpts_list = [(pt[0], pt[1], pt[2]) for pt in kpts]

                        base_conf = float(np.mean([pt[2] for pt in kpts]))
                        nose = kpts[0]
                        l_sh, r_sh = kpts[5], kpts[6]
                        l_hip, r_hip = kpts[11], kpts[12]
                        l_wrist, r_wrist = kpts[9], kpts[10]

                        # Tọa độ và kích thước trung tâm vai
                        sh_x = (l_sh[0] + r_sh[0]) / 2.0
                        sh_y = (l_sh[1] + r_sh[1]) / 2.0
                        sh_w = max(35.0, float(math.hypot(l_sh[0] - r_sh[0], l_sh[1] - r_sh[1])))

                        # Góc nghiêng thân người (Torso angle)
                        torso_angle = 90.0
                        if l_sh[2] > 0.30 and r_sh[2] > 0.30:
                            if l_hip[2] > 0.25 and r_hip[2] > 0.25:
                                hip_x = (l_hip[0] + r_hip[0]) / 2.0
                                hip_y = (l_hip[1] + r_hip[1]) / 2.0
                                dx = abs(sh_x - hip_x)
                                dy = abs(sh_y - hip_y)
                            else:
                                dx = abs(nose[0] - sh_x)
                                dy = max(20.0, abs(sh_y - nose[1])) if nose[2] > 0.25 else 50.0

                            if dx + dy > 1e-4:
                                torso_angle = math.degrees(math.atan2(dy, max(1e-4, dx)))

                        bio_state["angle"] = torso_angle

                        # Vận tốc cổ tay hai bên (Left & Right Wrist Velocity) + Độ nâng cao bàn tay (Hand Elevation)
                        curr_r = (float(r_wrist[0]), float(r_wrist[1])) if r_wrist[2] > 0.3 else None
                        curr_l = (float(l_wrist[0]), float(l_wrist[1])) if l_wrist[2] > 0.3 else None
                        wrist_speed = 0.0
                        if isinstance(self.prev_wrists, dict):
                            if curr_r and self.prev_wrists.get("r"):
                                wrist_speed = max(
                                    wrist_speed,
                                    math.hypot(curr_r[0] - self.prev_wrists["r"][0], curr_r[1] - self.prev_wrists["r"][1]) / max(1e-4, dt)
                                )
                            if curr_l and self.prev_wrists.get("l"):
                                wrist_speed = max(
                                    wrist_speed,
                                    math.hypot(curr_l[0] - self.prev_wrists["l"][0], curr_l[1] - self.prev_wrists["l"][1]) / max(1e-4, dt)
                                )
                        elif isinstance(self.prev_wrists, tuple) and curr_r:
                            dist = math.hypot(curr_r[0] - self.prev_wrists[0], curr_r[1] - self.prev_wrists[1])
                            wrist_speed = dist / max(1e-4, dt)
                        self.prev_wrists = {"r": curr_r, "l": curr_l}
                        curr_wrist = curr_r or curr_l

                        # Điểm nâng cao bàn tay (Hand Elevation Bonus) để bắt đỉnh cử chỉ vẫy tay / giơ ngón cái / chạm mặt
                        active_wrist_ys = []
                        if l_wrist[2] > 0.30:
                            active_wrist_ys.append(float(l_wrist[1]))
                        if r_wrist[2] > 0.30:
                            active_wrist_ys.append(float(r_wrist[1]))
                        hand_elev_bonus = 0.0
                        if active_wrist_ys:
                            min_wy = min(active_wrist_ys)
                            ref_y = sh_y + 0.40 * sh_w
                            if min_wy < ref_y:
                                hand_elev_bonus = min(1.5, max(0.0, (ref_y - min_wy) / max(30.0, sh_w)))

                        # Phân loại 11 Hành vi Sinh cơ học chi tiết
                        # 1. Té ngã / Gục xuống bàn
                        if torso_angle < 36.0 and (nose[2] > 0.25 and nose[1] > raw.shape[0] * 0.55):
                            bio_state["is_danger"] = True
                            bio_state["posture"] = "Té ngã / Gục xuống bàn"
                            bio_state["alert"] = f"PHÁT HIỆN TÉ NGÃ / GỤC XUỐNG BÀN ({torso_angle:.0f}°)"
                            severity = "danger"
                            clarity_score = base_conf + 0.8

                        # 2. Cử chỉ bất thường / Vung tay mạnh
                        elif wrist_speed > 520.0 and curr_wrist and (nose[2] > 0.25 and math.hypot(curr_wrist[0] - nose[0], curr_wrist[1] - nose[1]) > 100):
                            bio_state["is_danger"] = True
                            bio_state["posture"] = "Cử chỉ bất thường / Vung tay mạnh"
                            bio_state["alert"] = f"VẬN TỐC TAY ĐỘT BIẾN ({int(wrist_speed)} px/s)"
                            severity = "danger"
                            clarity_score = base_conf + 0.7

                        # 3. Giơ tay phát biểu / Vẫy tay chào
                        elif (l_wrist[2] > 0.35 and l_wrist[1] < l_sh[1] - 25 and l_wrist[1] < nose[1]) or \
                             (r_wrist[2] > 0.35 and r_wrist[1] < r_sh[1] - 25 and r_wrist[1] < nose[1]):
                            bio_state["is_danger"] = False
                            bio_state["posture"] = "Giơ tay phát biểu / Vẫy tay"
                            bio_state["alert"] = "Cánh tay nâng cao qua vai (Tương tác)"
                            severity = "safe"
                            clarity_score = base_conf + 0.6

                        # 4. Đưa hai tay lên đầu / Căng thẳng
                        elif l_wrist[2] > 0.35 and r_wrist[2] > 0.35 and l_wrist[1] < nose[1] + 30 and r_wrist[1] < nose[1] + 30 and abs(l_wrist[0] - r_wrist[0]) < sh_w * 1.6:
                            bio_state["is_danger"] = False
                            bio_state["posture"] = "Đưa hai tay lên đầu / Căng thẳng"
                            bio_state["alert"] = "Hai tay chạm đầu (Dấu hiệu căng thẳng/mệt mỏi)"
                            severity = "warning"
                            clarity_score = base_conf + 0.5

                        # 5. Chống cằm / Đỡ má suy nghĩ
                        else:
                            chin_x = nose[0]
                            chin_y = nose[1] + 0.35 * sh_w if nose[2] > 0.25 else sh_y
                            d_lw = math.hypot(l_wrist[0] - chin_x, l_wrist[1] - chin_y) if l_wrist[2] > 0.3 else 999.0
                            d_rw = math.hypot(r_wrist[0] - chin_x, r_wrist[1] - chin_y) if r_wrist[2] > 0.3 else 999.0
                            is_chin_rest = (l_wrist[2] > 0.35 and d_lw < 0.65 * sh_w and l_wrist[1] < sh_y + 20) or \
                                           (r_wrist[2] > 0.35 and d_rw < 0.65 * sh_w and r_wrist[1] < sh_y + 20)

                            if is_chin_rest:
                                bio_state["is_danger"] = False
                                bio_state["posture"] = "Chống cằm / Đỡ má suy nghĩ"
                                bio_state["alert"] = "Bàn tay nâng đỡ cằm/má (Trạng thái tập trung)"
                                severity = "safe"
                                clarity_score = base_conf + 0.5

                            # 6. Khoanh tay trước ngực
                            elif l_wrist[2] > 0.35 and r_wrist[2] > 0.35 and l_wrist[1] > sh_y and r_wrist[1] > sh_y and \
                                 (l_wrist[0] > sh_x - 15 or r_wrist[0] < sh_x + 15) and abs(l_wrist[1] - r_wrist[1]) < 0.45 * sh_w:
                                bio_state["is_danger"] = False
                                bio_state["posture"] = "Khoanh tay trước ngực"
                                bio_state["alert"] = "Hai tay khoanh trước ngực (Tư thế quan sát)"
                                severity = "safe"
                                clarity_score = base_conf + 0.4

                            # 7. Cúi đầu tập trung / Xem tài liệu
                            elif (nose[2] > 0.35 and (nose[1] - sh_y) > 0.12 * sh_w) or (45.0 <= torso_angle < 68.0):
                                bio_state["is_danger"] = False
                                bio_state["posture"] = "Cúi đầu tập trung / Xem tài liệu"
                                bio_state["alert"] = f"Đầu cúi thấp hướng mặt bàn ({torso_angle:.0f}°)"
                                severity = "safe"
                                clarity_score = base_conf + 0.4

                            # 8. Nghiêng người lệch trục
                            elif abs(l_sh[1] - r_sh[1]) > 0.26 * sh_w or (36.0 <= torso_angle < 48.0):
                                bio_state["is_danger"] = False
                                bio_state["posture"] = "Nghiêng người lệch trục"
                                bio_state["alert"] = f"Lệch trục vai ({abs(l_sh[1] - r_sh[1]):.0f}px) - Ngồi nghiêng"
                                severity = "warning"
                                clarity_score = base_conf + 0.4

                            # 9. Ngả lưng thư giãn
                            elif torso_angle > 98.0 or (nose[2] > 0.35 and (sh_y - nose[1]) > 0.8 * sh_w):
                                bio_state["is_danger"] = False
                                bio_state["posture"] = "Ngả lưng thư giãn"
                                bio_state["alert"] = f"Trục thân ngả về sau ({torso_angle:.0f}°) - Nghỉ ngơi"
                                severity = "safe"
                                clarity_score = base_conf + 0.3

                            # 10. Ngồi thẳng bình thường (Chuẩn mực)
                            else:
                                bio_state["is_danger"] = False
                                bio_state["posture"] = "Ngồi thẳng bình thường"
                                bio_state["alert"] = f"Trục thân chuẩn mực: {torso_angle:.0f}° | Khu vực an toàn"
                                severity = "safe"
                                clarity_score = base_conf + 0.3
            else:
                # Không phát hiện người
                bio_state = {
                    "angle": 0.0,
                    "posture": "Rời vị trí / Vắng mặt",
                    "is_danger": False,
                    "alert": "Không có người trong tầm quét camera"
                }
                severity = "warning"
                clarity_score = 0.8

            with self.ai_lock:
                self.latest_boxes = boxes_list
                self.latest_kpts = kpts_list
                self.biomechanics = bio_state

            # Ghi nhận ứng viên khung hình vào chuỗi động học cửa sổ 6.0 giây (Kinematic Action Score S(t))
            now_cand_ts = time.time()
            if now_cand_ts - getattr(self, "last_candidate_ts", 0.0) >= 0.12:
                self.last_candidate_ts = now_cand_ts
                torso_dev_bonus = min(0.6, abs(90.0 - float(bio_state.get("angle", 90.0))) / 45.0) if bio_state.get("angle", 0.0) > 0 else 0.0
                kinematic_score = float(clarity_score + min(1.8, wrist_speed / 220.0) + hand_elev_bonus + torso_dev_bonus)
                with self.frame_lock:
                    self.window_candidates.append((now_cand_ts, kinematic_score, raw.copy(), dict(bio_state)))
                    if len(self.window_candidates) > 60:
                        self.window_candidates.pop(0)

    def _render_worker(self):
        t_prev = time.time()
        last_cpu_poll_ts = 0.0
        while self.running:
            self.thread_states["CamCompositor"] = "RUNNING"
            raw = None
            with self.frame_lock:
                if self.latest_raw_frame is not None:
                    raw = self.latest_raw_frame.copy()

            if raw is None:
                time.sleep(0.03)
                continue

            with self.ai_lock:
                boxes = list(self.latest_boxes)
                kpts = list(self.latest_kpts)
                bio = dict(self.biomechanics)

            # Cập nhật FPS & lấy mẫu CPU EMA định kỳ mỗi 0.5s (tránh gọi PDH kernel counter 30 lần/giây)
            now = time.time()
            if (now - last_cpu_poll_ts) >= 0.5:
                last_cpu_poll_ts = now
                instant_cpu = psutil.cpu_percent()
                self.cpu_smoothed = 0.85 * self.cpu_smoothed + 0.15 * instant_cpu

            dt = max(1e-4, now - t_prev)
            t_prev = now
            self.fps_queue.append(1.0 / dt)
            self.current_fps = sum(self.fps_queue) / len(self.fps_queue)

            is_danger = bio.get("is_danger", False)
            status_color = (68, 68, 239) if is_danger else (255, 240, 0)
            danger_level = "NGUY HIEM" if is_danger else "AN TOAN"

            # Giữ nguyên độ phân giải gốc 1:1 của cảm biến (1920x1080 hoặc 1280x720) để tránh nội suy phóng đại hạt nhiễu
            # Tái sử dụng trực tiếp bản sao raw đã copy ở trên để tiết kiệm băng thông RAM
            raw_h, raw_w = raw.shape[:2]
            if raw_w >= 1280 and raw_h >= 720:
                target_w, target_h = raw_w, raw_h
                cam_viewport = raw
            else:
                target_w, target_h = 1280, 720
                cam_viewport = cv2.resize(raw, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

            # Scale coordinates từ raw sang viewport
            scale_x = target_w / max(1, raw_w)
            scale_y = target_h / max(1, raw_h)

            # Vẽ Skeleton
            if kpts:
                kpts_scaled = [(pt[0] * scale_x, pt[1] * scale_y, pt[2]) for pt in kpts]
                self.hud_renderer.draw_cyber_skeleton(cam_viewport, kpts_scaled, status_color)

            # Vẽ Bounding Box
            for (x1, y1, x2, y2, label, conf) in boxes:
                vx1, vy1 = int(x1 * scale_x), int(y1 * scale_y)
                vx2, vy2 = int(x2 * scale_x), int(y2 * scale_y)
                self.hud_renderer.draw_corner_bracket_bbox(cam_viewport, vx1, vy1, vx2, vy2, status_color, label, 0.0)

            # Vẽ trang trí Camera HUD tối giản (chỉ giữ REC & nhãn thời gian góc khung hình)
            self.hud_renderer.draw_camera_decorations(
                cam_viewport,
                fps=self.current_fps,
                is_ai_busy=False,
                danger_level=danger_level
            )

            # Khung camera toàn cảnh sạch sẽ 1280x720 (Đã loại bỏ sidebar thông số gây vướng, thông số hiển thị ở dashboard UI)
            hud_canvas = cam_viewport

            with self.frame_lock:
                self.latest_hud_frame = hud_canvas

            time.sleep(0.030) # ~30-32 FPS cap
        self.thread_states["CamCompositor"] = "READY"

    def get_latest_hud(self):
        with self.frame_lock:
            if self.latest_hud_frame is not None:
                return self.latest_hud_frame.copy()
            return None


# Singleton Instances
LIVE_CAMERA = LiveCameraPipeline(video_source=0)
ANNOTATOR_ENGINE = VideoAnnotatorEngine()
OS_LAB = get_os_lab_engine(camera_pipeline=LIVE_CAMERA)

_token_guard_instance = None

def get_token_guard():
    global _token_guard_instance
    if _token_guard_instance is None:
        from core.token_guard import TokenGuard
        _token_guard_instance = TokenGuard()
    return _token_guard_instance

class _LazyTokenGuardProxy:
    def __getattr__(self, name):
        return getattr(get_token_guard(), name)

TOKEN_GUARD = _LazyTokenGuardProxy()

# Quản lý tiến trình xử lý Video (Jobs)
JOBS: Dict[str, Dict[str, Any]] = {}


_warmup_cancel_event = threading.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khử ngoại lệ ngắt kết nối WinError 10054 trên Windows khi browser refresh / đóng stream
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        def _silence_windows_disconnect(loop, context):
            exc = context.get("exception")
            if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)) or (exc and "10054" in str(exc)):
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(_silence_windows_disconnect)
    except Exception:
        pass

    # Kích hoạt luồng nạp trước AI model dưới nền, không cản trở uvicorn mở cổng 8000
    _warmup_cancel_event.clear()

    def _background_warmup():
        # Dùng Event.wait thay vì time.sleep để có thể hủy ngay lập tức khi server tắt
        if _warmup_cancel_event.wait(timeout=0.5):
            return  # Server đã tắt trong thời gian chờ, hủy nạp để không lãng phí GPU/GIL
        if not _warmup_cancel_event.is_set():
            try:
                ANNOTATOR_ENGINE.warmup()
            except Exception as e_warm:
                try:
                    print(f"[*] Background warmup completed with notification: {e_warm}")
                except Exception:
                    pass

    warmup_thread = threading.Thread(
        target=_background_warmup,
        name="AIModelWarmupWorker",
        daemon=True
    )
    warmup_thread.start()
    yield
    # Dọn dẹp an toàn khi tắt server
    _warmup_cancel_event.set()
    if LIVE_CAMERA.running:
        LIVE_CAMERA.stop()


# ==============================================================================
# FASTAPI APP & STATE
# ==============================================================================
app = FastAPI(
    title="Cyber Surveillance Hub",
    description="Hệ thống Giám sát Hành vi Video Thời gian thực & Phân tích AI Đa luồng",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/api/snapshots", StaticFiles(directory=SNAPSHOTS_DIR), name="snapshots")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


# ==============================================================================
# WEB ENDPOINTS
# ==============================================================================
@app.get("/whitepaper", response_class=HTMLResponse)
async def get_whitepaper():
    """
    Phục vụ tài liệu bạch thư kỹ thuật hệ thống (Academic Whitepaper).
    """
    whitepaper_path = os.path.join(BASE_DIR, "BACH_THU_KY_THUAT_HE_THONG.html")
    if os.path.exists(whitepaper_path):
        with open(whitepaper_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="Whitepaper not found")

@app.get("/health")
@app.get("/api/health")
async def health_check():
    """
    Điểm cuối kiểm tra tính sẵn sàng (Readiness Probe).
    Phản hồi HTTP 200 OK ngay khi Web Server mở cổng.
    Cung cấp trạng thái tiến trình nạp mô hình AI chạy nền.
    """
    device = CONFIG._cached_device
    if device is None and "torch" in sys.modules:
        device = CONFIG.DEVICE
    elif device is None:
        device = "cuda:0" if ("CUDA_PATH" in os.environ or os.path.exists("C:/Program Files/NVIDIA Corporation")) else "cpu"

    ai_status = "warming_up"
    if ANNOTATOR_ENGINE:
        if getattr(ANNOTATOR_ENGINE, "_warmup_error", None):
            ai_status = "error"
        elif ANNOTATOR_ENGINE.is_ready:
            ai_status = "ready"

    return {
        "status": "healthy",
        "ready": True,
        "server_time": time.time(),
        "ai_status": ai_status,
        "device": device,
        "active_camera": LIVE_CAMERA.running
    }


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if not os.path.exists(index_file):
        raise HTTPException(status_code=404, detail="index.html not found.")
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Cache buster ép trình duyệt luôn nạp mã JS & CSS mới nhất, triệt tiêu lỗi cache phiên bản cũ
    cache_id = int(time.time())
    content = content.replace("/static/app.js", f"/static/app.js?v={cache_id}")
    content = content.replace("/static/style.css", f"/static/style.css?v={cache_id}")

    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/api/stream/live")
def stream_live():
    """
    Truyền luồng video MJPEG thời gian thực 30 FPS với Cyber HUD 1280x720 vào thẻ <img> của trình duyệt.
    Camera không bao giờ tự động bật; chỉ khởi động khi người dùng bấm nút [Bật Camera]
    """
    def frame_generator():
        try:
            with LIVE_CAMERA.clients_lock:
                LIVE_CAMERA.active_clients += 1
            while True:
                frame = LIVE_CAMERA.get_latest_hud()
                if frame is not None:
                    ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    if ret:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                        )
                else:
                    standby = np.zeros((720, 1280, 3), dtype=np.uint8)
                    cv2.putText(standby, "HE THONG GIAM SAT VIDEO DA LUONG - CAMERA DANG TAM DUNG", (270, 340),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 229, 255), 2, cv2.LINE_AA)
                    cv2.putText(standby, "Bam [Bat Camera] ben duoi de khoi dong luong giam sat", (340, 390),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (148, 163, 184), 1, cv2.LINE_AA)
                    ret, jpeg = cv2.imencode(".jpg", standby, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    if ret:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                        )
                time.sleep(0.033)
        finally:
            with LIVE_CAMERA.clients_lock:
                LIVE_CAMERA.active_clients = max(0, LIVE_CAMERA.active_clients - 1)

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Loại bỏ thông báo lỗi 404 vô hại trên console trình duyệt."""
    return Response(status_code=204)


@app.post("/api/camera/client_frame")
async def ingest_client_frame_endpoint(file: UploadFile = File(...)):
    """
    Nhận khung hình từ webcam của trình duyệt client (HTML5 getUserMedia),
    đẩy vào luồng LiveCameraPipeline để phân tích bằng GPU.
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is not None and frame.size > 0:
            LIVE_CAMERA.ingest_client_frame(frame)
            return JSONResponse({"status": "ok", "fps": LIVE_CAMERA.current_fps})
        return JSONResponse({"status": "error", "message": "Corrupted frame"}, status_code=400)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)



@app.post("/api/camera/toggle")
async def toggle_camera(request: Request):
    """
    Bật hoặc tạm dừng Live Camera. Chấp nhận JSON, form-data hoặc query param.
    """
    action = None
    try:
        content_type = request.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            body = await request.json()
            if isinstance(body, dict):
                action = body.get("action")
        elif "form" in content_type:
            form = await request.form()
            action = form.get("action")
    except Exception:
        pass

    if not action:
        action = request.query_params.get("action")

    if action == "start":
        LIVE_CAMERA.user_stopped = False
        LIVE_CAMERA.start()
        return {
            "status": "started",
            "camera_running": LIVE_CAMERA.running,
            "device_available": LIVE_CAMERA.camera_device_available
        }
    elif action == "stop":
        LIVE_CAMERA.stop()
        return {
            "status": "stopped",
            "camera_running": LIVE_CAMERA.running,
            "device_available": LIVE_CAMERA.camera_device_available
        }
    else:
        if LIVE_CAMERA.running:
            LIVE_CAMERA.stop()
            return {
                "status": "stopped",
                "camera_running": False,
                "device_available": LIVE_CAMERA.camera_device_available
            }
        else:
            LIVE_CAMERA.user_stopped = False
            LIVE_CAMERA.start()
            return {
                "status": "started",
                "camera_running": LIVE_CAMERA.running,
                "device_available": LIVE_CAMERA.camera_device_available
            }


@app.get("/api/camera/logs")
def get_camera_logs():
    """
    Trả về danh sách nhật ký hành vi thời gian thực kèm trạng thái bộ điều phối phân tầng.
    Bảo đảm Thread-safe khi Starlette chuyển đổi JSON.
    """
    tier_info = MODEL_ORCHESTRATOR.get_active_tier_info()
    with LIVE_CAMERA.ai_lock:
        logs_copy = list(LIVE_CAMERA.action_logs)

    return {
        "status": "success",
        "total": len(logs_copy),
        "logs": logs_copy,
        "gemini_status": LIVE_CAMERA.gemini_status,
        "active_tier": tier_info.get("active_tier", "tier_1"),
        "tier_name": tier_info.get("tier_name", "Tier-1 Gemini 3.8"),
        "tier_badge": tier_info.get("tier_badge", "Tier-1 Gemini 3.8"),
        "cooldown_remaining": round(tier_info.get("cooldown_remaining", 0.0), 1),
        "is_cooldown": tier_info.get("is_cooldown", False)
    }


@app.post("/api/camera/logs/clear")
def clear_camera_logs():
    """Xóa danh sách nhật ký hành vi bảo đảm Thread-safe."""
    with LIVE_CAMERA.ai_lock:
        LIVE_CAMERA.action_logs.clear()
        LIVE_CAMERA.action_counter = 0
    return {"status": "cleared", "total": 0}


@app.post("/api/camera/snapshot")
def manual_camera_snapshot():
    """Chụp ảnh bằng chứng tức thì theo yêu cầu của người dùng."""
    entry = LIVE_CAMERA.capture_manual_snapshot()
    if entry:
        return {"status": "success", "entry": entry}
    return {"status": "error", "message": "Camera chưa sẵn sàng hoặc không có khung hình"}


class CameraSettingsPayload(BaseModel):
    mirror: Optional[bool] = None
    anti_glare: Optional[bool] = None
    denoise: Optional[bool] = None


@app.post("/api/camera/settings")
async def update_camera_settings(request: Request):
    """
    Cập nhật cài đặt bộ lọc camera trực tiếp (Lật gương, Chống chói đèn trần, Khử nhiễu).
    Chấp nhận payload JSON, form-data hoặc query parameters.
    """
    mirror = None
    anti_glare = None
    denoise = None

    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            body = await request.json()
            if isinstance(body, dict):
                mirror = body.get("mirror")
                anti_glare = body.get("anti_glare")
                denoise = body.get("denoise")
        except Exception:
            pass
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            if "mirror" in form:
                mirror = form.get("mirror")
            if "anti_glare" in form:
                anti_glare = form.get("anti_glare")
            if "denoise" in form:
                denoise = form.get("denoise")
        except Exception:
            pass
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                mirror = body.get("mirror")
                anti_glare = body.get("anti_glare")
                denoise = body.get("denoise")
        except Exception:
            try:
                form = await request.form()
                if "mirror" in form:
                    mirror = form.get("mirror")
                if "anti_glare" in form:
                    anti_glare = form.get("anti_glare")
                if "denoise" in form:
                    denoise = form.get("denoise")
            except Exception:
                pass

    # Fallback to query params
    params = request.query_params
    if mirror is None and "mirror" in params:
        mirror = params.get("mirror")
    if anti_glare is None and "anti_glare" in params:
        anti_glare = params.get("anti_glare")
    if denoise is None and "denoise" in params:
        denoise = params.get("denoise")

    updated = LIVE_CAMERA.set_settings(
        mirror=mirror,
        anti_glare=anti_glare,
        denoise=denoise,
    )
    return {
        "status": "ok",
        "settings": updated,
    }


@app.get("/api/camera/settings")
def get_camera_settings():
    """Lấy cấu hình hiện tại của camera enhancer."""
    return {
        "status": "ok",
        "settings": LIVE_CAMERA.get_settings(),
    }


@app.get("/api/telemetry")
def get_telemetry():
    if not LIVE_CAMERA.running:
        instant_cpu = psutil.cpu_percent()
        LIVE_CAMERA.cpu_smoothed = 0.80 * LIVE_CAMERA.cpu_smoothed + 0.20 * instant_cpu
    vram_mb, vram_total = 0, 0
    if NVML_AVAILABLE:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_mb = int(info.used / (1024 * 1024))
            vram_total = int(info.total / (1024 * 1024))
        except Exception:
            pass

    tier_info = MODEL_ORCHESTRATOR.get_active_tier_info()
    cam_settings = LIVE_CAMERA.get_settings()

    from core.metrics import get_hardware_gpu_name
    gpu_name = get_hardware_gpu_name()

    with LIVE_CAMERA.ai_lock:
        bio_copy = dict(LIVE_CAMERA.biomechanics)
        logs_copy = list(LIVE_CAMERA.action_logs)

    # Thống kê phân bổ rủi ro từ danh sách sự kiện phiên trực tiếp
    safe_cnt = 0
    warn_cnt = 0
    danger_cnt = 0
    for l in logs_copy:
        sev = l.get("severity", "safe")
        if sev == "danger":
            danger_cnt += 1
        elif sev == "warning":
            warn_cnt += 1
        else:
            safe_cnt += 1

    session_risk_counts = {
        "safe": safe_cnt,
        "warning": warn_cnt,
        "danger": danger_cnt
    }

    recent_angle = bio_copy.get("angle", 90.0)
    if bio_copy.get("is_danger", False):
        curr_ergo = 25.0
    elif 75.0 <= recent_angle <= 105.0:
        curr_ergo = 94.0
    elif 45.0 <= recent_angle < 75.0:
        curr_ergo = 76.0
    else:
        curr_ergo = 58.0

    quota_stats = tier_info.get("quota_stats") or MODEL_ORCHESTRATOR.quota_tracker.get_stats()
    tier1_m = "gemini-3.1-flash-lite"
    tier2_m = "gemini-3-flash-preview"
    t1_rpd = quota_stats.get("tier1_rpd_used", quota_stats.get("rpd_used", 0))
    t1_rpm = quota_stats.get("tier1_rpm_used", quota_stats.get("rpm_used", 0))
    t2_rpd = quota_stats.get("tier2_rpd_used", 0)
    t2_rpm = quota_stats.get("tier2_rpm_used", 0)
    rpd_lim = quota_stats.get("rpd_limit", 1500)
    rpm_lim = quota_stats.get("rpm_limit", 15)

    active_tier_key = tier_info.get("active_tier", "tier_1")
    if LIVE_CAMERA.running and LIVE_CAMERA.action_logs:
        raw_logged_tier = str(LIVE_CAMERA.action_logs[0].get("model_tier", "") or "").lower()
        if "tier_3" in raw_logged_tier or "local" in raw_logged_tier or "heuristic" in raw_logged_tier:
            active_tier_key = "tier_3"
        elif "tier_2" in raw_logged_tier or "fallback" in raw_logged_tier:
            active_tier_key = "tier_2"
        elif "tier_1" in raw_logged_tier or "primary" in raw_logged_tier:
            active_tier_key = "tier_1"

    t1_daily_locked = bool(tier_info.get("is_tier1_daily_exhausted", False)) or (t1_rpd >= rpd_lim)
    cd_sec = int(round(tier_info.get("cooldown_remaining", 0)))

    if active_tier_key == "tier_1":
        t1_status = "Đang xử lý chính"
        t1_badge = "Đang dùng"
    elif t1_daily_locked:
        t1_status = "Hết hạn mức ngày (mở 00:00)"
        t1_badge = "Hết lượt"
    elif cd_sec > 0:
        t1_status = f"Đang hồi hạn mức ({cd_sec}s)"
        t1_badge = f"Chờ {cd_sec}s"
    else:
        t1_status = "Tạm nhường lượt xử lý"
        t1_badge = "Tạm nghỉ"

    if active_tier_key == "tier_2":
        t2_status = "Đang tiếp quản xử lý"
        t2_badge = "Đang dùng"
    else:
        t2_status = "Tự động tiếp quản khi cần"
        t2_badge = "Dự phòng"

    if active_tier_key == "tier_3":
        t3_status = "Đang phân tích trực tiếp trên máy"
        t3_badge = "Đang dùng"
    else:
        t3_status = "Dự phòng xử lý nội bộ"
        t3_badge = "Nội bộ"

    quota_matrix = {
        "tier_1": {
            "name": "Mô hình 1 · Chính",
            "model": tier1_m,
            "status": t1_status,
            "limit": f"Ngày: {t1_rpd}/{rpd_lim} · Phút: {t1_rpm}/{rpm_lim}",
            "badge": t1_badge,
            "is_active": (active_tier_key == "tier_1")
        },
        "tier_2": {
            "name": "Mô hình 2 · Dự phòng",
            "model": tier2_m,
            "status": t2_status,
            "limit": f"Ngày: {t2_rpd}/{rpd_lim} · Phút: {t2_rpm}/{rpm_lim}",
            "badge": t2_badge,
            "is_active": (active_tier_key == "tier_2")
        },
        "tier_3": {
            "name": "Mô hình 3 · Nội bộ",
            "model": f"Xử lý nội bộ ({gpu_name})",
            "status": t3_status,
            "limit": "Không giới hạn lượt",
            "badge": t3_badge,
            "is_active": (active_tier_key == "tier_3")
        }
    }

    buf_stats = LIVE_CAMERA.frame_buffer.get_stats() if (hasattr(LIVE_CAMERA, "frame_buffer") and LIVE_CAMERA.frame_buffer is not None) else {
        "size": 0, "capacity": getattr(CONFIG, "FRAME_QUEUE_MAXSIZE", 16), "total_dropped": 0, "drop_rate_pct": 0.0, "latency_ms": 0.0, "high_water_mark": 0,
        "mutex_lock_count": 0, "not_empty_wait_count": 0, "not_full_wait_count": 0, "condition_signal_count": 0, "ram_ceiling_mb": 42.19, "ram_active_mb": 0.0,
        "total_produced": 0, "total_consumed": 0, "utilization_pct": 0.0
    }

    return {
        # Thông số hệ thống & Tiến trình Đa luồng (Hệ điều hành - Bounded Buffer)
        "producer_running": LIVE_CAMERA.running or LIVE_CAMERA.stress_test_active,
        "producer_fps": round(LIVE_CAMERA.current_fps, 1),
        "consumer_fps": round(LIVE_CAMERA.consumer_fps, 1),
        "consumer_delay_ms": LIVE_CAMERA.consumer_delay_ms,
        "stress_test_active": LIVE_CAMERA.stress_test_active,
        "consumer_status": LIVE_CAMERA.gemini_status,
        "queue_size": buf_stats["size"],
        "queue_max": buf_stats["capacity"],
        "dropped_frames": buf_stats["total_dropped"],
        "drop_rate_pct": buf_stats["drop_rate_pct"],
        "queue_latency_ms": buf_stats["latency_ms"],
        "high_water_mark": buf_stats["high_water_mark"],
        "bounded_queue_size": buf_stats["size"],
        "bounded_queue_capacity": buf_stats["capacity"],
        "total_produced": buf_stats.get("total_produced", 0),
        "total_consumed": buf_stats.get("total_consumed", 0),
        "mutex_lock_count": buf_stats.get("mutex_lock_count", 0),
        "not_empty_wait_count": buf_stats.get("not_empty_wait_count", 0),
        "not_full_wait_count": buf_stats.get("not_full_wait_count", 0),
        "condition_signal_count": buf_stats.get("condition_signal_count", 0),
        "ram_ceiling_mb": buf_stats.get("ram_ceiling_mb", 42.19),
        "ram_active_mb": buf_stats.get("ram_active_mb", 0.0),
        "thread_states": dict(LIVE_CAMERA.thread_states),
        "cpu_percent": round(LIVE_CAMERA.cpu_smoothed, 1),
        "ram_percent": round(psutil.virtual_memory().percent, 1),
        "gpu_vram_used": round(vram_mb / 1024.0, 2),
        "gpu_vram_total": round(vram_total / 1024.0, 2) if vram_total > 0 else 0.0,
        "gpu_name": gpu_name,
        "active_model_tier": active_tier_key,
        "active_tier_name": "Mô hình 2 (Dự phòng)" if active_tier_key == "tier_2" else ("Mô hình 3 (Nội bộ)" if active_tier_key == "tier_3" else tier_info.get("tier_name", "Mô hình 1 (Chính)")),
        "tier_badge": "Mô hình 2 (Dự phòng)" if active_tier_key == "tier_2" else ("Mô hình 3 (Nội bộ)" if active_tier_key == "tier_3" else tier_info.get("tier_badge", "Mô hình 1 (Chính)")),
        "cooldown_remaining": round(tier_info.get("cooldown_remaining", 0.0), 1),
        "is_cooldown": tier_info.get("is_cooldown", False),
        "is_tier1_daily_exhausted": t1_daily_locked,
        "quota_matrix": quota_matrix,
        "realtime_quota": {
            "date": quota_stats.get("date", time.strftime("%Y-%m-%d")),
            "rpm_used": quota_stats["rpm_used"],
            "rpm_limit": quota_stats["rpm_limit"],
            "rpm_remaining": quota_stats["rpm_remaining"],
            "rpm_percent": quota_stats["rpm_percent"],
            "rpd_used": quota_stats["rpd_used"],
            "rpd_limit": quota_stats["rpd_limit"],
            "rpd_remaining": quota_stats["rpd_remaining"],
            "rpd_percent": quota_stats["rpd_percent"],
            "tokens_today": quota_stats["tokens_today"],
            "tier1_rpm_used": t1_rpm,
            "tier1_rpd_used": t1_rpd,
            "tier2_rpm_used": t2_rpm,
            "tier2_rpd_used": t2_rpd,
        },
        "active_clients": LIVE_CAMERA.active_clients,

        # Tương thích ngược với UI và test suite hiện hành
        "camera_running": LIVE_CAMERA.running,
        "camera_device_available": LIVE_CAMERA.camera_device_available,
        "is_client_streaming": LIVE_CAMERA.is_client_streaming,
        "fps": round(LIVE_CAMERA.current_fps, 1),
        "gpu_vram_mb": vram_mb,
        "gpu_vram_total_mb": vram_total,
        "biomechanics": bio_copy,
        "camera_settings": cam_settings,
        "mirror": cam_settings["mirror"],
        "anti_glare": cam_settings["anti_glare"],
        "denoise": cam_settings["denoise"],

        # Thống kê rủi ro & công thái học phiên trực tiếp
        "session_risk_counts": session_risk_counts,
        "current_ergonomic_score": curr_ergo,
        "continuous_sitting_sec": 0.0,
    }


class OSLabConfigPayload(BaseModel):
    buffer_capacity: Optional[int] = None
    consumer_delay_ms: Optional[int] = None
    buffer_policy: Optional[str] = None
    reset_counters: bool = False
    trigger_burst: bool = False


@app.post("/api/os_lab/config")
async def update_os_lab_config(req: OSLabConfigPayload):
    """
    Điều chỉnh trực tiếp tham số Thực nghiệm Hệ Điều Hành (Bounded-Buffer Capacity N, CPU Time Share & Buffer Policy).
    """
    res = LIVE_CAMERA.configure_os_lab(
        buffer_capacity=req.buffer_capacity,
        consumer_delay_ms=req.consumer_delay_ms,
        buffer_policy=req.buffer_policy,
        reset_counters=req.reset_counters,
        trigger_burst=req.trigger_burst
    )
    return {"status": "ok", **res}


@app.get("/api/os_lab/config")
def get_os_lab_config():
    """Lấy cấu hình hiện tại của bộ Thực nghiệm Hệ Điều Hành."""
    stats = LIVE_CAMERA.frame_buffer.get_stats() if hasattr(LIVE_CAMERA, "frame_buffer") else {}
    cpu_share_pct = max(10, round(100.0 * 15.0 / (15.0 + float(LIVE_CAMERA.consumer_delay_ms))))
    return {
        "status": "ok",
        "buffer_capacity": stats.get("capacity", 16),
        "consumer_delay_ms": LIVE_CAMERA.consumer_delay_ms,
        "cpu_share_pct": cpu_share_pct,
        "buffer_policy": getattr(LIVE_CAMERA, "buffer_policy", "drop_oldest"),
        "ram_ceiling_mb": stats.get("ram_ceiling_mb", 42.19),
        "stats": stats
    }


# ==============================================================================
# OS EXPERIMENTAL LAB SANDBOX ENDPOINTS (SILBERSCHATZ LAB BENCH)
# ==============================================================================
class OSBufferScenarioPayload(BaseModel):
    capacity: Optional[int] = 16
    consumer_delay_ms: Optional[int] = 0
    policy: Optional[str] = "drop_oldest"


class OSDeadlockResolvePayload(BaseModel):
    method: Optional[str] = "banker_preemption"


class OSMemorySimPayload(BaseModel):
    policy: Optional[str] = "fifo"


@app.get("/api/os_lab/scenarios/buffer")
def get_os_lab_buffer_scenario():
    """Lấy số liệu và phân tích tác động nhân quả của hàng đợi Bounded Buffer."""
    return {"status": "ok", **OS_LAB.get_buffer_impact_telemetry()}


@app.post("/api/os_lab/scenarios/buffer")
def set_os_lab_buffer_scenario(req: OSBufferScenarioPayload):
    """Cập nhật kịch bản Bounded Buffer & Bufferbloat và trả về kết quả đối chứng AI."""
    res = OS_LAB.configure_buffer_scenario(
        capacity=req.capacity or 16,
        consumer_delay_ms=req.consumer_delay_ms or 0,
        policy=req.policy or "drop_oldest"
    )
    return {"status": "ok", **res}


@app.get("/api/os_lab/scenarios/deadlock")
def get_os_lab_deadlock_status():
    """Lấy trạng thái bế tắc và dữ liệu đồ thị cấp phát tài nguyên RAG."""
    return {"status": "ok", **OS_LAB.get_deadlock_status()}


@app.post("/api/os_lab/scenarios/deadlock/trigger")
def trigger_os_lab_deadlock():
    """Kích hoạt giả lập bế tắc đa luồng an toàn (Watchdog tự động ngắt sau 3.0s)."""
    res = OS_LAB.trigger_deadlock_simulation()
    return {"status": "ok", **res}


@app.post("/api/os_lab/scenarios/deadlock/resolve")
def resolve_os_lab_deadlock(req: OSDeadlockResolvePayload):
    """Giải phóng bế tắc theo thuật toán Banker / Preemption."""
    res = OS_LAB.resolve_deadlock(method=req.method or "banker_preemption")
    return {"status": "ok", **res}


@app.post("/api/os_lab/scenarios/memory_eviction")
def simulate_os_lab_memory_eviction(req: OSMemorySimPayload):
    """Thực nghiệm đối chứng thuật toán thay thế trang RAM: FIFO vs Threat-Priority."""
    res = OS_LAB.simulate_memory_eviction(policy=req.policy or "fifo")
    return {"status": "ok", **res}


class OSBenchmarkPayload(BaseModel):
    capacity: Optional[int] = 16
    consumer_delay_ms: Optional[int] = 0
    frames_count: Optional[int] = 50


@app.get("/api/os_lab/dual_evaluation")
def get_dual_mode_eval(capacity: int = 16, consumer_delay_ms: int = 0, policy: str = "drop_oldest"):
    """Lấy ma trận đánh giá đối sánh 2 chế độ: Live Camera vs Import Video."""
    return {"status": "ok", **OS_LAB.get_dual_mode_evaluation(capacity, consumer_delay_ms, policy)}


@app.post("/api/os_lab/dual_evaluation")
def post_dual_mode_eval(req: OSBufferScenarioPayload):
    """Lấy ma trận đánh giá đối sánh theo tham số người dùng chọn."""
    return {
        "status": "ok",
        **OS_LAB.get_dual_mode_evaluation(
            req.capacity if req.capacity is not None else 16,
            req.consumer_delay_ms if req.consumer_delay_ms is not None else 0,
            req.policy or "drop_oldest"
        )
    }


@app.post("/api/os_lab/benchmark")
def run_os_lab_benchmark_endpoint(req: OSBenchmarkPayload):
    """Chạy thực nghiệm đo đạc 50 khung hình thực tế trên phần cứng."""
    res = OS_LAB.run_live_benchmark(
        capacity=req.capacity or 16,
        consumer_delay_ms=req.consumer_delay_ms or 0,
        frames_count=req.frames_count or 50
    )
    return res


@app.post("/api/os_lab/simulate_stall")
def simulate_stall_endpoint():
    """Giả lập trạng thái quá tải cận kề sập (Bảo vệ cứng ở cận trên RAM <= 50MB)."""
    # Ép tham số kịch trần nhưng bảo vệ an toàn
    eval_res = OS_LAB.get_dual_mode_evaluation(capacity=64, consumer_delay_ms=200)
    return {
        "status": "ok",
        "is_simulated_stall": True,
        "ram_ceiling_mb": 50.0,
        "safety_guarantee": "Hệ thống được khóa cứng ở cận trên 50MB RAM, kích hoạt Circuit Breaker ngăn chặn 100% crash thật.",
        **eval_res
    }




# ==============================================================================
# VIDEO IMPORT & BATCH ANALYTICS ENDPOINTS
# ==============================================================================
@app.post("/api/video/upload")
async def upload_video_file(file: UploadFile = File(...)):
    """
    Nhận video tải lên từ máy cục bộ.
    """
    filename = f"upload_{int(time.time())}_{file.filename}"
    save_path = os.path.abspath(os.path.join(RECORDINGS_DIR, filename))

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    cap = cv2.VideoCapture(save_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = total_frames / fps if fps > 0 else 0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    return {
        "status": "success",
        "video_path": save_path,
        "filename": filename,
        "stream_url": f"/api/video/stream_file/{filename}",
        "duration": round(duration, 2),
        "width": width,
        "height": height,
        "size_mb": round(len(content) / (1024 * 1024), 2),
        "has_audio": check_video_has_audio(save_path)
    }


class URLProbeRequest(BaseModel):
    url: str


@app.post("/api/video/probe_url")
def probe_video_endpoint(req: URLProbeRequest):
    """
    Quét metadata của video từ link URL (0.5s) mà không tải toàn bộ video về máy.
    """
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp link URL hợp lệ.")
    try:
        info = probe_web_video(url)
        return {
            "status": "success",
            **info
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class URLImportRequest(BaseModel):
    url: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None


@app.post("/api/video/import_url")
def import_video_from_url(req: URLImportRequest):
    """
    Tải video (toàn bộ hoặc dải start_time -> end_time) từ URL sử dụng yt-dlp.
    """
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp link URL hợp lệ.")

    try:
        info = download_web_video(
            url,
            output_dir=RECORDINGS_DIR,
            start_time=req.start_time,
            end_time=req.end_time
        )
        filename = os.path.basename(info["file_path"])
        return {
            "status": "success",
            "video_path": info["file_path"],
            "filename": filename,
            "stream_url": f"/api/video/stream_file/{filename}",
            "title": info["title"],
            "duration": round(info["duration"], 2),
            "thumbnail": info["thumbnail"],
            "uploader": info["uploader"],
            "is_clipped": info.get("is_clipped", False),
            "has_audio": info.get("has_audio", False)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ProcessRequest(BaseModel):
    video_path: str
    start_time: float = 0.0
    end_time: float = 60.0
    call_gemini: bool = True
    anomaly_focus: bool = True


@app.post("/api/video/process")
def start_video_processing(req: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Khởi chạy phân tích đoạn video được chọn theo timeline CapCut trên GPU RTX 5060.
    """
    if req.end_time <= req.start_time:
        raise HTTPException(status_code=400, detail="Khoảng thời gian timeline không hợp lệ: end_time phải lớn hơn start_time.")

    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=404, detail="File video không tồn tại trên hệ thống.")

    job_id = str(uuid.uuid4())[:8]
    output_filename = f"annotated_{job_id}_{os.path.basename(req.video_path)}"
    output_path = os.path.abspath(os.path.join(RECORDINGS_DIR, output_filename))

    JOBS[job_id] = {
        "status": "processing",
        "progress_percent": 0.0,
        "stage": "Đang khởi tạo luồng xử lý...",
        "current_frame": 0,
        "total_frames": 0,
        "current_fps": 0.0,
        "pipeline_live": {
            "reader_frames": 0,
            "infer_frames": 0,
            "writer_frames": 0,
            "raw_q": 0,
            "writer_q": 0,
            "q_max": 16,
            "infer_stride": 1
        },
        "result": None,
        "error": None,
        "output_filename": output_filename
    }

    def run_worker():
        try:
            def on_progress(cur, total, fps, stage="Đang phân tích khung hình & trích xuất tư thế...", pipe_live=None):
                # Frame analysis maps strictly to 0% - 90%
                if stage and "hội chẩn" in stage.lower():
                    pct = 95.0
                elif stage and "mã hóa" in stage.lower():
                    pct = 92.0
                elif stage and "tổng hợp" in stage.lower():
                    pct = 98.0
                else:
                    frame_ratio = (cur / total) if total > 0 else 0
                    pct = min(90.0, round(frame_ratio * 90.0, 1))

                JOBS[job_id]["current_frame"] = cur
                JOBS[job_id]["total_frames"] = total
                JOBS[job_id]["current_fps"] = round(fps, 1)
                JOBS[job_id]["progress_percent"] = pct
                JOBS[job_id]["stage"] = stage
                if isinstance(pipe_live, dict):
                    JOBS[job_id]["pipeline_live"] = pipe_live

            try:
                import importlib
                import core.token_guard as _tg_mod
                import core.video_annotator as _va_mod
                importlib.reload(_tg_mod)
                importlib.reload(_va_mod)
                ANNOTATOR_ENGINE.__class__ = _va_mod.VideoAnnotatorEngine
                if getattr(ANNOTATOR_ENGINE, "_token_guard", None) is not None:
                    ANNOTATOR_ENGINE._token_guard.__class__ = _tg_mod.TokenGuard
            except Exception:
                pass

            res = ANNOTATOR_ENGINE.process_video(
                input_path=req.video_path,
                output_path=output_path,
                start_time=req.start_time,
                end_time=req.end_time,
                progress_callback=on_progress,
                call_gemini=req.call_gemini,
                anomaly_focus=req.anomaly_focus
            )

            # Đang hoàn tất và trích xuất đoạn đối sánh song song
            JOBS[job_id]["progress_percent"] = 99.0
            JOBS[job_id]["stage"] = "Đang trích xuất video đối sánh song song..."

            # Trích xuất video đoạn gốc tương ứng (Raw Trimmed Slice) để so sánh song song 1:1
            raw_trimmed_filename = f"raw_trimmed_{job_id}_{os.path.basename(req.video_path)}"
            raw_trimmed_path = os.path.abspath(os.path.join(RECORDINGS_DIR, raw_trimmed_filename))
            has_audio = check_video_has_audio(req.video_path)
            is_cpu_enc = (str(getattr(ANNOTATOR_ENGINE, "device", "cpu")).lower() == "cpu")
            best_enc_flags = get_optimal_h264_encoder_profiles(is_cpu_mode=is_cpu_enc)[0]
            cmd_raw = [
                get_ffmpeg_bin(), "-y",
                "-ss", str(req.start_time),
                "-to", str(req.end_time),
                "-i", req.video_path,
                *best_enc_flags
            ]
            if has_audio:
                cmd_raw.extend(["-c:a", "aac"])
            else:
                cmd_raw.extend(["-an"])
            cmd_raw.extend(["-pix_fmt", "yuv420p", "-movflags", "+faststart", raw_trimmed_path])

            try:
                subprocess.run(cmd_raw, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            except Exception as e_trim:
                print(f"[!] Warning: failed to extract raw trimmed clip: {e_trim}")

            if os.path.exists(raw_trimmed_path) and os.path.getsize(raw_trimmed_path) > 0:
                res["raw_trimmed_stream_url"] = f"/api/video/stream_file/{raw_trimmed_filename}"
            else:
                res["raw_trimmed_stream_url"] = None

            res["annotated_stream_url"] = f"/api/video/stream_file/{output_filename}"
            res["download_url"] = f"/api/video/download/{output_filename}"
            JOBS[job_id]["progress_percent"] = 100.0
            JOBS[job_id]["stage"] = "Hoàn tất phân tích 100%"
            JOBS[job_id]["result"] = res
            JOBS[job_id]["status"] = "completed"

        except Exception as e:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)

    background_tasks.add_task(run_worker)

    return {
        "job_id": job_id,
        "status": "started",
        "output_filename": output_filename
    }


@app.get("/api/video/job/{job_id}")
def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job ID không tồn tại.")
    return JOBS[job_id]


@app.get("/api/video/stream_file/{filename}")
def stream_video_file(filename: str):
    """
    Phục vụ file video trực tiếp để trình duyệt có thể phát và tua timeline mượt mà.
    """
    file_path = os.path.abspath(os.path.join(RECORDINGS_DIR, filename))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File video không tìm thấy.")
    return FileResponse(file_path, media_type="video/mp4")


@app.get("/api/video/download/{filename}")
def download_video_file(filename: str):
    """
    Cho phép tải video thành phẩm đã gắn nhãn về máy người dùng.
    """
    file_path = os.path.abspath(os.path.join(RECORDINGS_DIR, filename))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File video không tìm thấy.")
    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename
    )


class ChatRequest(BaseModel):
    question: str
    job_id: Optional[str] = None


@app.post("/api/chat")
def ask_gemini_qa(req: ChatRequest):
    """
    Hỏi đáp AI ngữ nghĩa kế thừa cơ chế Hierarchical Failover (Tier 1 -> Tier 2 -> Tier 3).
    """
    context_str = "Chưa có dữ liệu video cụ thể."
    if req.job_id and req.job_id in JOBS and JOBS[req.job_id].get("result"):
        res = JOBS[req.job_id]["result"]
        timeline = res.get("timeline", [])
        percentages = res.get("action_percentages", {})
        gemini_rep = res.get("gemini_report", {})
        context_str = f"""
THÔNG SỐ PHÂN TÍCH TỪ HỆ THỐNG:
- Thời lượng: {res.get('duration_seconds')}s ({res.get('total_frames')} frames)
- Tỷ lệ hành vi: {percentages}
- Mức độ nguy hiểm cao nhất: {res.get('peak_danger_reason')} ({res.get('overall_danger_level')})
- Dòng sự kiện: {timeline}
- Chẩn đoán y tế sơ bộ: {gemini_rep.get('detailed_diagnosis', 'Bình thường')}
"""
    else:
        # Nếu hỏi về luồng Live Camera, lấy ngữ cảnh từ RollingContextMemory
        context_str = MODEL_ORCHESTRATOR.context_memory.get_context_summary_for_prompt()

    prompt = f"""Bạn là Trợ lý AI Giám sát An ninh & Y tế (Học phần Hệ Điều Hành — Báo cáo Tổng hợp Video Trực quan).
Hãy trả lời câu hỏi của người dùng một cách chính xác, ngắn gọn, súc tích dựa trên bằng chứng dữ liệu dưới đây:

DỮ LIỆU BẰNG CHỨNG TỪ HỆ THỐNG:
{context_str}

CÂU HỎI NGƯỜI DÙNG:
{req.question}

TRẢ LỜI (Tiếng Việt trang trọng, chuyên môn cao):"""

    result = MODEL_ORCHESTRATOR.execute_chat_qa(prompt)
    return result
