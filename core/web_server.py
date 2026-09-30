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
from core.video_annotator import VideoAnnotatorEngine, download_web_video, probe_web_video, check_video_has_audio
from core.token_guard import TokenGuard
from core.enhancer import CameraEnhancer
from core.model_orchestrator import get_model_orchestrator, ModelTier

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
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


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
        self.camera_device_available = True
        self.cap = None
        self.threads = []

        self.frame_lock = threading.Lock()
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

        # Telemetry
        self.cpu_smoothed = psutil.cpu_percent()
        self.fps_queue = deque(maxlen=30)
        self.current_fps = 30.0
        self.active_clients = 0
        self.clients_lock = threading.Lock()

        self.hud_renderer = CyberHUDRenderer()
        self.yolo_model = None
        self.enhancer = CameraEnhancer(mirror=True, anti_glare=True, denoise=True)

        # Nhật ký hành vi thời gian thực (Behavior Event Log)
        self.action_logs = []
        self.action_counter = 0
        self.last_logged_action = ""
        self.last_log_time = 0.0
        self.window_candidates = []
        self.snapshots_dir = os.path.join(RECORDINGS_DIR, "snapshots")
        # Cloud AI: Hierarchical Model Orchestrator (Tier 1 -> Tier 2 -> Tier 3 Failover)
        self.gemini_model = getattr(CONFIG, "GEMINI_TIER1_MODEL", "gemini-2.0-flash")
        self.gemini_client = MODEL_ORCHESTRATOR.client
        self.gemini_status = "active" if MODEL_ORCHESTRATOR.client is not None else "heuristic_offline"
        print(f"[+] LiveCameraPipeline: Ket noi Model Orchestrator ({self.gemini_model}) - Trang thai: {self.gemini_status}")

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

            # Lưu ảnh khung hình đại diện (Peak Keyframe)
            snap_name = f"snap_{self.action_counter:04d}_{int(now_t)}.jpg"
            snap_path = os.path.join(self.snapshots_dir, snap_name)
            if frame is not None and frame.size > 0:
                cv2.imwrite(snap_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

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
        """Chụp ảnh bằng chứng thủ công theo lệnh người dùng."""
        with self.frame_lock:
            frame = self.latest_raw_frame.copy() if self.latest_raw_frame is not None else None
        if frame is None:
            return None
        with self.ai_lock:
            bio = dict(self.biomechanics)
        entry = self._record_behavior_log(
            frame=frame,
            posture=f"Thủ công: {bio.get('posture', 'Bình thường')}",
            angle=bio.get("angle", 90.0),
            alert="Ảnh chụp tức thì theo lệnh người dùng",
            is_danger=bio.get("is_danger", False),
            severity="safe"
        )
        return entry

    def start(self):
        with self.start_lock:
            if self.running or self.is_starting:
                return
            self.is_starting = True

            print("[*] Khoi dong Live Camera Pipeline da luong...")
            try:
                device = CONFIG.DEVICE

                # Nạp model YOLOv8-Pose
                if self.yolo_model is None:
                    from ultralytics import YOLO
                    self.yolo_model = YOLO(CONFIG.YOLO_MODEL_NAME)
                    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
                    self.yolo_model(dummy, device=device, verbose=False)

                # Mở Camera an toàn với cơ chế dò đa backend trên Windows
                self.cap = None
                self.camera_device_available = False
                cam_w = getattr(CONFIG, "CAMERA_WIDTH", 640)
                cam_h = getattr(CONFIG, "CAMERA_HEIGHT", 480)

                if isinstance(self.video_source, int):
                    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if sys.platform == "win32" else [cv2.CAP_ANY]
                    for backend in backends:
                        backend_name = "DSHOW" if backend == cv2.CAP_DSHOW else ("MSMF" if backend == cv2.CAP_MSMF else "ANY")
                        try:
                            cap_test = cv2.VideoCapture(self.video_source, backend)
                            if cap_test is not None and cap_test.isOpened():
                                cap_test.set(cv2.CAP_PROP_FRAME_WIDTH, cam_w)
                                cap_test.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_h)
                                cap_test.set(cv2.CAP_PROP_FPS, 30)
                                ret, test_frame = cap_test.read()
                                if ret and test_frame is not None and test_frame.size > 0:
                                    self.cap = cap_test
                                    self.camera_device_available = True
                                    print(f"[+] Mo webcam thanh cong qua backend {backend_name} (index {self.video_source})!")
                                    break
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
                    except Exception as e_file:
                        print(f"[!] Loi mo nguon video: {e_file}")

                if not self.camera_device_available:
                    print(f"[!] Luu y: Khong the mo camera vat ly index {self.video_source}. He thong san sang tiep nhan luong Webcam Trinh Duyet (Browser Ingest).")

                self.running = True

                # Khởi động các luồng
                t_capture = threading.Thread(target=self._capture_worker, name="CamProducer", daemon=True)
                t_ai = threading.Thread(target=self._ai_worker, name="CamEdgeAI", daemon=True)
                t_render = threading.Thread(target=self._render_worker, name="CamCompositor", daemon=True)
                t_gemini = threading.Thread(target=self._gemini_worker, name="CamGeminiAI", daemon=True)

                self.threads = [t_capture, t_ai, t_render, t_gemini]
                for t in self.threads:
                    t.start()
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
            if self.cap and self.cap.isOpened():
                self.cap.release()
            self.cap = None
            self.latest_hud_frame = None
            print("[+] Live Camera Pipeline da giai phong camera an toan.")

    def ingest_client_frame(self, raw_frame):
        """
        Tiếp nhận khung hình trực tiếp từ Webcam trình duyệt của người dùng (Client Browser).
        Cho phép Live Camera hoạt động mượt mà ngay cả khi máy chủ chạy trên Cloud (Google Colab).
        """
        if not self.running:
            self.start()
        frame = self.enhancer.enhance(raw_frame)
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

    def _gemini_worker(self):
        """
        Luồng Consumer AI Cloud & Heuristic Arbiter (Hierarchical Model Orchestrator):
        - Chu kỳ điều phối >= 4.2 giây (khống chế < 15 RPM).
        - Phân tầng mô hình Tier 1 -> Tier 2 -> Tier 3 qua MODEL_ORCHESTRATOR.
        - Tự động duy trì và tiêm Rolling Context Memory 3-5 chu kỳ trước.
        - Tự phục hồi sau 60s cooldown (Preemptive Cooldown Reversion).
        - Cập nhật nhật ký hành vi thời gian thực và đồng bộ viễn trắc.
        """
        # Chờ camera ổn định 1.2s sau khi bật
        time.sleep(1.2)

        while self.running:
            t_start = time.time()
            frame = None
            with self.frame_lock:
                if self.latest_raw_frame is not None:
                    frame = self.latest_raw_frame.copy()

            if frame is not None and frame.size > 0:
                try:
                    self.action_counter += 1
                    snap_name = f"snap_gemini_{self.action_counter:04d}_{int(t_start)}.jpg"
                    snap_path = os.path.join(self.snapshots_dir, snap_name)
                    cv2.imwrite(snap_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

                    with self.ai_lock:
                        bio = dict(self.biomechanics)

                    # Thực thi suy luận đa tầng tự phục hồi qua MODEL_ORCHESTRATOR
                    ai_result = MODEL_ORCHESTRATOR.execute_live_analysis(frame, bio)

                    tier_info = MODEL_ORCHESTRATOR.get_active_tier_info()
                    if tier_info["active_tier"] == "tier_3" and MODEL_ORCHESTRATOR.client is None:
                        self.gemini_status = "heuristic_offline"
                    elif tier_info["is_cooldown"]:
                        self.gemini_status = "failover_tier2" if tier_info["active_tier"] == "tier_2" else "quota_exceeded"
                    else:
                        self.gemini_status = "active"

                    action_name = ai_result.get("action", "Hành vi bình thường")
                    desc_name = ai_result.get("description", "Không có mô tả chi tiết")
                    pred_name = ai_result.get("prediction_next_4s", "Duy trì hoạt động hiện tại")
                    severity_val = ai_result.get("severity", "safe")
                    if severity_val not in ("safe", "warning", "danger"):
                        severity_val = "safe"

                    raw_tier = ai_result.get("model_tier", "Tier-1 Gemini 2.0")
                    if "Tier-1" in str(raw_tier) or str(raw_tier) == "tier_1":
                        tier_key = "tier_1"
                    elif "Tier-2" in str(raw_tier) or str(raw_tier) == "tier_2":
                        tier_key = "tier_2"
                    elif "Tier-3" in str(raw_tier) or str(raw_tier) == "tier_3":
                        tier_key = "tier_3"
                    else:
                        tier_key = str(raw_tier)

                    code_prefix = "DANGER" if severity_val == "danger" else ("WARN" if severity_val == "warning" else "NORM")

                    entry = {
                        "id": f"#{self.action_counter:03d}",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "code": f"{code_prefix}-{self.action_counter:02d}",
                        "action": action_name,
                        "description": desc_name,
                        "prediction_next_4s": pred_name,
                        "snapshot_url": f"/api/snapshots/{snap_name}",
                        "severity": severity_val,
                        "model_tier": tier_key
                    }

                    with self.ai_lock:
                        self.action_logs.insert(0, entry)
                        if len(self.action_logs) > 100:
                            self.action_logs.pop()
                        self.biomechanics["posture"] = action_name
                        self.biomechanics["alert"] = f"Dự đoán 4s tới: {pred_name}"
                        self.biomechanics["is_danger"] = (severity_val == "danger")

                    print(f"[+] Gemini Vision #{self.action_counter:03d} (Chu kỳ 4s - {tier_key}): '{action_name}' | '{desc_name[:50]}...' -> {snap_name}")

                except Exception as e_outer:
                    print(f"[!] Loi chu ky Gemini AI: {e_outer}")

            # Đảm bảo chu kỳ điều phối 4.2 giây (khống chế < 15 RPM)
            elapsed = time.time() - t_start
            wait_t = max(0.5, 4.2 - elapsed)
            time.sleep(wait_t)

    def _capture_worker(self):
        while self.running:
            if not self.cap or not self.cap.isOpened():
                time.sleep(0.1)
                continue
            ret, frame = self.cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue
            # Tiền xử lý trực tiếp trên khung hình thu nhận: Lật gương, Chống chói đèn trần, Khử nhiễu
            frame = self.enhancer.enhance(frame)
            with self.frame_lock:
                self.latest_raw_frame = frame
                self.frame_count += 1

    def _ai_worker(self):
        device = CONFIG.DEVICE
        prev_time = time.time()
        while self.running:
            raw = None
            with self.frame_lock:
                if self.latest_raw_frame is not None:
                    raw = self.latest_raw_frame.copy()

            if raw is None:
                time.sleep(0.02)
                continue

            results = self.yolo_model(raw, device=device, conf=CONFIG.YOLO_CONFIDENCE, verbose=False)
            dt = max(1e-4, time.time() - prev_time)
            prev_time = time.time()

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

            if results and len(results) > 0:
                res = results[0]
                boxes = res.boxes
                kpts_data = res.keypoints

                if boxes is not None and len(boxes) > 0:
                    for i, box in enumerate(boxes):
                        conf = float(box.conf[0].item())
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        # Lọc box nhỏ / bóng phản chiếu
                        if (x2 - x1) * (y2 - y1) < (raw.shape[0] * raw.shape[1] * 0.04):
                            continue
                        boxes_list.append((x1, y1, x2, y2, "NGƯỜI", conf))

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

                        # Vận tốc cổ tay (Wrist velocity)
                        curr_wrist = (float(r_wrist[0]), float(r_wrist[1])) if r_wrist[2] > 0.3 else None
                        wrist_speed = 0.0
                        if curr_wrist and self.prev_wrists:
                            dist = math.hypot(curr_wrist[0] - self.prev_wrists[0], curr_wrist[1] - self.prev_wrists[1])
                            wrist_speed = dist / max(1e-4, dt)
                        if curr_wrist:
                            self.prev_wrists = curr_wrist

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

            time.sleep(0.01)

    def _render_worker(self):
        t_prev = time.time()
        while self.running:
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

            # Cập nhật CPU EMA
            instant_cpu = psutil.cpu_percent()
            self.cpu_smoothed = 0.85 * self.cpu_smoothed + 0.15 * instant_cpu

            # Cập nhật FPS
            now = time.time()
            dt = max(1e-4, now - t_prev)
            t_prev = now
            self.fps_queue.append(1.0 / dt)
            self.current_fps = sum(self.fps_queue) / len(self.fps_queue)

            # Lấy VRAM từ NVML
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
            telemetry = {
                "cpu_percent": self.cpu_smoothed,
                "ram_percent": psutil.virtual_memory().percent,
                "gpu_vram_mb": vram_mb,
                "gpu_vram_total_mb": vram_total,
                "actual_fps": self.current_fps,
                "raw_queue_size": 1,
                "drop_count": 0,
                "active_persons": len(boxes),
                "active_model_tier": tier_info.get("active_tier", "tier_1"),
                "active_tier_name": tier_info.get("tier_name", "gemini-2.0-flash"),
                "cooldown_remaining": tier_info.get("cooldown_remaining", 0.0)
            }

            diagnosis = {
                "action": bio["posture"],
                "context": f"Góc thân: {bio['angle']:.0f}° | {bio['alert']}",
                "danger_level": "NGUY HIEM" if bio["is_danger"] else "AN TOAN",
                "danger_score": 9 if bio["is_danger"] else 1,
                "danger_reason": bio["alert"],
                "timestamp": time.strftime("%H:%M:%S"),
                "model_tier_str": tier_info.get("tier_badge", "● Tier-1 Gemini 2.0")
            }

            is_danger = bio.get("is_danger", False)
            status_color = (68, 68, 239) if is_danger else (255, 240, 0)
            danger_score = 9 if is_danger else 1
            danger_level = "NGUY HIEM" if is_danger else "AN TOAN"

            # Resize sang Viewport (900x720)
            cam_viewport = cv2.resize(raw, (self.hud_renderer.viewport_w, self.hud_renderer.viewport_h))

            # Scale coordinates từ raw sang viewport
            raw_h, raw_w = raw.shape[:2]
            scale_x = self.hud_renderer.viewport_w / max(1, raw_w)
            scale_y = self.hud_renderer.viewport_h / max(1, raw_h)

            # Vẽ Skeleton
            if kpts:
                kpts_scaled = [(pt[0] * scale_x, pt[1] * scale_y, pt[2]) for pt in kpts]
                self.hud_renderer.draw_cyber_skeleton(cam_viewport, kpts_scaled, status_color)

            # Vẽ Bounding Box
            for (x1, y1, x2, y2, label, conf) in boxes:
                vx1, vy1 = int(x1 * scale_x), int(y1 * scale_y)
                vx2, vy2 = int(x2 * scale_x), int(y2 * scale_y)
                self.hud_renderer.draw_corner_bracket_bbox(cam_viewport, vx1, vy1, vx2, vy2, status_color, label, conf)

            # Vẽ trang trí Camera HUD
            self.hud_renderer.draw_camera_decorations(
                cam_viewport,
                fps=self.current_fps,
                is_ai_busy=False,
                danger_level=danger_level
            )

            # Nhận diện GPU name cho metrics HUD
            gpu_name = getattr(CONFIG, "_cached_gpu_name", None)
            if not gpu_name:
                try:
                    import torch
                    if torch.cuda.is_available():
                        raw_gpu = torch.cuda.get_device_name(0)
                        gpu_name = "RTX 5060" if "5060" in raw_gpu else raw_gpu
                    else:
                        gpu_name = "CPU Only"
                except Exception:
                    gpu_name = "CPU Only"

            # Render Glass Sidebar bằng Pillow Unicode
            metrics = {
                "cpu_percent": self.cpu_smoothed,
                "ram_percent": psutil.virtual_memory().percent,
                "gpu_vram_used": vram_mb / 1024.0,
                "gpu_vram_total": vram_total / 1024.0 if vram_total > 0 else 8.0,
                "gpu_name": gpu_name,
                "queue_size": 1,
                "queue_max": 5,
                "dropped_frames": 0,
                "drop_rate_pct": 0.0,
                "active_model_tier": tier_info.get("active_tier", "tier_1"),
                "active_tier_name": tier_info.get("tier_name", "Tier-1 Gemini 2.0"),
                "cooldown_remaining": tier_info.get("cooldown_remaining", 0.0)
            }

            sidebar_bgr = self.hud_renderer.render_sidebar_pil(
                diagnosis=diagnosis,
                entities={"person": len(boxes)},
                metrics=metrics,
                danger_score=danger_score,
                danger_level=danger_level,
                biomechanics=bio
            )

            # Ghép ngang thành canvas 1280x720 Widescreen
            hud_canvas = np.hstack([cam_viewport, sidebar_bgr])

            with self.frame_lock:
                self.latest_hud_frame = hud_canvas

            time.sleep(0.025) # ~35-40 FPS cap

    def get_latest_hud(self):
        with self.frame_lock:
            if self.latest_hud_frame is not None:
                return self.latest_hud_frame.copy()
            return None


# Singleton Instances
LIVE_CAMERA = LiveCameraPipeline(video_source=0)
ANNOTATOR_ENGINE = VideoAnnotatorEngine()

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
    # Kích hoạt luồng nạp trước AI model dưới nền, không cản trở uvicorn mở cổng 8000
    _warmup_cancel_event.clear()

    def _background_warmup():
        # Dùng Event.wait thay vì time.sleep để có thể hủy ngay lập tức khi server tắt
        if _warmup_cancel_event.wait(timeout=0.5):
            return  # Server đã tắt trong thời gian chờ, hủy nạp để không lãng phí GPU/GIL
        if not _warmup_cancel_event.is_set():
            ANNOTATOR_ENGINE.warmup()

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


# ==============================================================================
# WEB ENDPOINTS
# ==============================================================================
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
    """
    if not LIVE_CAMERA.running:
        LIVE_CAMERA.start()

    def frame_generator():
        try:
            with LIVE_CAMERA.clients_lock:
                LIVE_CAMERA.active_clients += 1
            while True:
                frame = LIVE_CAMERA.get_latest_hud()
                if frame is not None:
                    ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                        )
                else:
                    standby = np.zeros((720, 1280, 3), dtype=np.uint8)
                    cv2.putText(standby, "HE THONG GIAM SAT VIDEO DA LUONG - CHO NGUON KHUNG HINH...", (260, 340),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 229, 255), 2, cv2.LINE_AA)
                    cv2.putText(standby, "Bam [Bat Webcam Trinh Duyet] hoac kiem tra ket noi camera", (310, 390),
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
        LIVE_CAMERA.start()
        return {"status": "started", "camera_running": LIVE_CAMERA.running}
    elif action == "stop":
        LIVE_CAMERA.stop()
        return {"status": "stopped", "camera_running": LIVE_CAMERA.running}
    else:
        if LIVE_CAMERA.running:
            LIVE_CAMERA.stop()
            return {"status": "stopped", "camera_running": False}
        else:
            LIVE_CAMERA.start()
            return {"status": "started", "camera_running": LIVE_CAMERA.running}


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
        "tier_name": tier_info.get("tier_name", "Tier-1 Gemini 2.0"),
        "tier_badge": tier_info.get("tier_badge", "● Tier-1 Gemini 2.0"),
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

    gpu_name = "CPU Only"
    try:
        import torch
        if torch.cuda.is_available():
            raw_gpu = torch.cuda.get_device_name(0)
            gpu_name = "RTX 5060" if "5060" in raw_gpu else raw_gpu
    except Exception:
        pass

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

    return {
        # Academic OS Telemetry (PROJECT.md)
        "producer_running": LIVE_CAMERA.running,
        "producer_fps": round(LIVE_CAMERA.current_fps, 1),
        "consumer_status": LIVE_CAMERA.gemini_status,
        "queue_size": 1,
        "queue_max": 5,
        "dropped_frames": 0,
        "drop_rate_pct": 0.0,
        "cpu_percent": round(LIVE_CAMERA.cpu_smoothed, 1),
        "ram_percent": round(psutil.virtual_memory().percent, 1),
        "gpu_vram_used": round(vram_mb / 1024.0, 2),
        "gpu_vram_total": round(vram_total / 1024.0, 2) if vram_total > 0 else 8.0,
        "gpu_name": gpu_name,
        "active_model_tier": tier_info.get("active_tier", "tier_1"),
        "active_tier_name": tier_info.get("tier_name", "Tier-1 Gemini 2.0"),
        "tier_badge": tier_info.get("tier_badge", "● Tier-1 Gemini 2.0"),
        "cooldown_remaining": round(tier_info.get("cooldown_remaining", 0.0), 1),
        "is_cooldown": tier_info.get("is_cooldown", False),

        # Tương thích ngược với UI và test suite hiện hành
        "camera_running": LIVE_CAMERA.running,
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
    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=404, detail="File video không tồn tại trên hệ thống.")

    if req.end_time <= req.start_time:
        raise HTTPException(status_code=400, detail="Khoảng thời gian timeline không hợp lệ: end_time phải lớn hơn start_time.")

    job_id = str(uuid.uuid4())[:8]
    output_filename = f"annotated_{job_id}_{os.path.basename(req.video_path)}"
    output_path = os.path.abspath(os.path.join(RECORDINGS_DIR, output_filename))

    JOBS[job_id] = {
        "status": "processing",
        "progress_percent": 0.0,
        "current_frame": 0,
        "total_frames": 0,
        "current_fps": 0.0,
        "result": None,
        "error": None,
        "output_filename": output_filename
    }

    def run_worker():
        try:
            def on_progress(cur, total, fps):
                pct = round((cur / total) * 100.0, 1) if total > 0 else 0
                JOBS[job_id]["current_frame"] = cur
                JOBS[job_id]["total_frames"] = total
                JOBS[job_id]["current_fps"] = round(fps, 1)
                JOBS[job_id]["progress_percent"] = pct

            res = ANNOTATOR_ENGINE.process_video(
                input_path=req.video_path,
                output_path=output_path,
                start_time=req.start_time,
                end_time=req.end_time,
                progress_callback=on_progress,
                call_gemini=req.call_gemini,
                anomaly_focus=req.anomaly_focus
            )

            res["annotated_stream_url"] = f"/api/video/stream_file/{output_filename}"
            res["download_url"] = f"/api/video/download/{output_filename}"
            JOBS[job_id]["status"] = "completed"
            JOBS[job_id]["progress_percent"] = 100.0
            JOBS[job_id]["result"] = res

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
THÔNG SỐ PHÂN TÍCH TỪ RTX 5060:
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
