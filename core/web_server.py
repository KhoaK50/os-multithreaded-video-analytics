"""
FastAPI Cyber Web Server: Trung tâm Giám sát Điều hành & Phân tích Hành vi Video Đa Luồng.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.

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
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.config import CONFIG
from core.cyber_hud import CyberHUDRenderer
from core.video_annotator import VideoAnnotatorEngine, download_web_video, probe_web_video, check_video_has_audio
from core.token_guard import TokenGuard
from core.enhancer import CameraEnhancer

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
        # Cloud AI: Google Gemini Multimodal Vision (Chu kỳ 4s điều phối Free Quota)
        self.gemini_client = None
        self.gemini_model = getattr(CONFIG, "GEMINI_MODEL", "gemini-3.5-flash-lite")
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=api_key)
                print(f"[+] Khoi tao Gemini Client ({self.gemini_model}) cho chu ky 4s thanh cong!")
            except Exception as e_init:
                print(f"[!] Khong the khoi tao Gemini Client: {e_init}")

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

    def _record_behavior_log(self, frame, posture: str, angle: float, alert: str, is_danger: bool, severity: str = "safe", prediction_next_4s: str = ""):
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
                "severity": severity
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
        if self.running:
            return
        print("[*] Khoi dong Live Camera Pipeline da luong...")
        try:
            device = CONFIG.DEVICE

            # Nạp model YOLOv8-Pose
            if self.yolo_model is None:
                from ultralytics import YOLO
                self.yolo_model = YOLO(CONFIG.YOLO_MODEL_NAME)
                dummy = np.zeros((480, 640, 3), dtype=np.uint8)
                self.yolo_model(dummy, device=device, verbose=False)

            # Mở Camera
            self.cap = cv2.VideoCapture(self.video_source, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
            cam_w = getattr(CONFIG, "CAMERA_WIDTH", 640)
            cam_h = getattr(CONFIG, "CAMERA_HEIGHT", 480)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_w)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_h)
            self.cap.set(cv2.CAP_PROP_FPS, 30)

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

    def stop(self):
        if not self.running:
            return
        print("[*] Dung Live Camera Pipeline...")
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.latest_hud_frame = None
        print("[+] Live Camera Pipeline da giai phong camera an toan.")

    def _gemini_worker(self):
        """
        Luồng Consumer AI Cloud (Google Gemini 3.5 Flash Lite):
        - Chu kỳ điều phối 4.0 - 4.5 giây / lần (Tối ưu hóa tuyệt đối Free Tier 15 RPM).
        - Phân tích sâu ngữ cảnh thực tế của người trong lát cắt 4 giây.
        - Đưa ra DỰ ĐOÁN XU HƯỚNG HÀNH VI TRONG 4 GIÂY TIẾP THEO.
        - Tự động trích xuất snapshot và cập nhật vào bảng nhật ký thời gian thực.
        """
        from PIL import Image
        from google.genai import types

        # Chờ camera ổn định 1.2s sau khi bật
        time.sleep(1.2)

        prompt = """Bạn là Hệ thống Giám sát & Phân tích Hành vi Thông minh (Học phần Hệ Điều Hành - GVHD: Thầy Nguyễn Tấn Duẩn).
Hãy quan sát bức ảnh khung hình camera vừa chụp được và phân tích thật chi tiết, khách quan, sâu sắc:
1. "action": Tên hành vi / cử chỉ tóm tắt ngắn gọn người đó đang làm gì (ví dụ: "Giơ 4 ngón tay ra hiệu", "Gõ bàn phím làm việc", "Cầm điện thoại nhắn tin", "Chống cằm suy nghĩ", "Che miệng tập trung", "Chụm tay làm ống nhòm mô phỏng", "Uống nước", "Vắng mặt / Rời vị trí").
2. "description": Miêu tả chi tiết, tường tận ngữ cảnh: người đó đang làm gì, ở đâu, làm như thế nào (tư thế đầu, vai, cử chỉ bàn tay, ngón tay cử động cụ thể ra sao, mắt nhìn đi đâu, hành động biểu cảm cụ thể, vật thể tương tác).
   - Phong cách diễn đạt: Dùng ngôn ngữ tiếng Việt phổ thông chuẩn mực, mang tính khoa học / học thuật, lịch sự, khách quan. Tuyệt đối KHÔNG dùng từ lóng, khẩu ngữ địa phương hoặc từ ngữ gây tối nghĩa (ví dụ: không dùng 'kính lợn' mà gọi chuẩn xác là 'ống nhòm mô phỏng bằng tay' hoặc 'kính ngắm giả định').
   - TUYỆT ĐỐI KHÔNG đưa các thông số góc thân đo đạc khô khan hay số liệu kỹ thuật vào đây, mà tập trung hoàn toàn vào miêu tả sinh động hành vi con người.
3. "prediction_next_4s": Dự đoán hợp lý xu hướng hành vi trong 4 giây tiếp theo dựa trên cử chỉ, hướng nhìn và biểu cảm hiện tại.
4. "severity":
   - "safe": Hoạt động học tập, làm việc, ra hiệu cử chỉ bình thường, an toàn.
   - "warning": Có dấu hiệu mệt mỏi, mất tập trung, dùng điện thoại nhiều hoặc sai tư thế công thái học.
   - "danger": Té ngã, gục xỉu, bất tỉnh hoặc cử chỉ nguy hiểm bất thường.

Trả về định dạng JSON thuần:
{
    "action": "Tên hành vi tóm tắt chuẩn mực",
    "description": "Miêu tả chi tiết ngữ cảnh người đó đang làm gì, ở đâu, làm như thế nào (chuẩn mực học thuật)",
    "prediction_next_4s": "Dự đoán xu hướng trong 4 giây tiếp theo",
    "severity": "safe" | "warning" | "danger"
}
"""

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

                    # Lazy reload Gemini Client nếu ban đầu chưa khởi tạo được
                    if self.gemini_client is None:
                        api_key = os.getenv("GEMINI_API_KEY")
                        if api_key:
                            try:
                                from google import genai
                                self.gemini_client = genai.Client(api_key=api_key)
                                print(f"[+] [Gemini 4s Consumer] Khoi tao thanh cong Gemini Client ({self.gemini_model})")
                            except Exception as e_cl:
                                print(f"[!] [Gemini 4s Consumer] Khong the khoi tao Gemini Client: {e_cl}")

                    ai_result = None
                    if self.gemini_client is not None:
                        try:
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            pil_img = Image.fromarray(rgb_frame)

                            response = self.gemini_client.models.generate_content(
                                model=self.gemini_model,
                                contents=[prompt, pil_img],
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json"
                                )
                            )
                            raw_text = response.text or "{}"
                            if "```json" in raw_text:
                                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                            elif "```" in raw_text:
                                raw_text = raw_text.split("```")[1].split("```")[0].strip()
                            ai_result = json.loads(raw_text)
                            if isinstance(ai_result, list) and len(ai_result) > 0:
                                ai_result = ai_result[0]
                        except Exception as e_api:
                            err_str = str(e_api)
                            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                print("[!] Gemini Rate Limit (15 RPM) - Tam nghi 10s de doi lam moi han muc phut...")
                                time.sleep(10.0)
                            else:
                                print(f"[!] Loi goi Gemini Vision: {e_api}")

                    # Fallback thông minh nếu không có kết quả từ Gemini API (hoặc mất mạng)
                    if not ai_result or not isinstance(ai_result, dict):
                        with self.ai_lock:
                            bio = dict(self.biomechanics)
                        posture_text = bio.get("posture", "Ngồi làm việc trước màn hình")
                        ai_result = {
                            "action": posture_text,
                            "description": f"Người dùng đang trong tư thế {posture_text.lower()} tại vị trí làm việc (Đang đồng bộ phân tích thị giác AI).",
                            "prediction_next_4s": "Duy trì trạng thái hoạt động trong 4 giây tiếp theo.",
                            "severity": "safe" if not bio.get("is_danger", False) else "danger"
                        }

                    action_name = ai_result.get("action", "Hành vi bình thường")
                    desc_name = ai_result.get("description", "Không có mô tả chi tiết")
                    pred_name = ai_result.get("prediction_next_4s", "Duy trì hoạt động hiện tại")
                    severity_val = ai_result.get("severity", "safe")
                    if severity_val not in ("safe", "warning", "danger"):
                        severity_val = "safe"

                    code_prefix = "DANGER" if severity_val == "danger" else ("WARN" if severity_val == "warning" else "NORM")

                    entry = {
                        "id": f"#{self.action_counter:03d}",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "code": f"{code_prefix}-{self.action_counter:02d}",
                        "action": action_name,
                        "description": desc_name,
                        "prediction_next_4s": pred_name,
                        "snapshot_url": f"/api/snapshots/{snap_name}",
                        "severity": severity_val
                    }

                    with self.ai_lock:
                        self.action_logs.insert(0, entry)
                        if len(self.action_logs) > 100:
                            self.action_logs.pop()
                        self.biomechanics["posture"] = action_name
                        self.biomechanics["alert"] = f"Dự đoán 4s tới: {pred_name}"
                        self.biomechanics["is_danger"] = (severity_val == "danger")

                    print(f"[+] Gemini Vision #{self.action_counter:03d} (Chu kỳ 4s): '{action_name}' | '{desc_name[:50]}...' -> {snap_name}")

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

            telemetry = {
                "cpu_percent": self.cpu_smoothed,
                "ram_percent": psutil.virtual_memory().percent,
                "gpu_vram_mb": vram_mb,
                "gpu_vram_total_mb": vram_total,
                "actual_fps": self.current_fps,
                "raw_queue_size": 1,
                "drop_count": 0,
                "active_persons": len(boxes)
            }

            diagnosis = {
                "action": bio["posture"],
                "context": f"Góc thân: {bio['angle']:.0f}° | {bio['alert']}",
                "danger_level": "NGUY HIEM" if bio["is_danger"] else "AN TOAN",
                "danger_score": 9 if bio["is_danger"] else 1,
                "danger_reason": bio["alert"],
                "timestamp": time.strftime("%H:%M:%S")
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

            # Render Glass Sidebar bằng Pillow Unicode
            metrics = {
                "cpu_percent": self.cpu_smoothed,
                "ram_percent": psutil.virtual_memory().percent,
                "gpu_vram_used": vram_mb / 1024.0,
                "gpu_vram_total": vram_total / 1024.0 if vram_total > 0 else 8.0,
                "queue_size": 1,
                "queue_max": 5,
                "dropped_frames": 0
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
                    cv2.putText(standby, "CYBER COMMAND CENTER - DANG KHOI DONG CAMERA...", (300, 360),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 229, 255), 2, cv2.LINE_AA)
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
    Trả về danh sách nhật ký hành vi thời gian thực kèm URL ảnh Snapshot (0 Token, 0 API).
    """
    return {
        "status": "success",
        "total": len(LIVE_CAMERA.action_logs),
        "logs": LIVE_CAMERA.action_logs
    }


@app.post("/api/camera/logs/clear")
def clear_camera_logs():
    """Xóa danh sách nhật ký hành vi."""
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

    cam_settings = LIVE_CAMERA.get_settings()
    return {
        "camera_running": LIVE_CAMERA.running,
        "cpu_percent": round(LIVE_CAMERA.cpu_smoothed, 1),
        "ram_percent": round(psutil.virtual_memory().percent, 1),
        "gpu_vram_mb": vram_mb,
        "gpu_vram_total_mb": vram_total,
        "fps": round(LIVE_CAMERA.current_fps, 1),
        "biomechanics": LIVE_CAMERA.biomechanics,
        "camera_settings": cam_settings,
        "mirror": cam_settings["mirror"],
        "anti_glare": cam_settings["anti_glare"],
        "denoise": cam_settings["denoise"],
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


@app.post("/api/video/process")
def start_video_processing(req: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Khởi chạy phân tích đoạn video được chọn theo timeline CapCut trên GPU RTX 5060.
    """
    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=404, detail="File video không tồn tại trên hệ thống.")

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
                call_gemini=req.call_gemini
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
    Hỏi đáp AI ngữ nghĩa về video đã phân tích.
    """
    if not TOKEN_GUARD.client:
        return {"answer": "Chưa cấu hình API Key Gemini trong hệ thống."}

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

    prompt = f"""Bạn là Trợ lý AI Giám sát An ninh & Y tế của hệ thống Cyber Command Center.
Hãy trả lời câu hỏi của người dùng một cách chính xác, ngắn gọn, súc tích dựa trên bằng chứng dữ liệu dưới đây:

DỮ LIỆU BẰNG CHỨNG TỪ VIDEO:
{context_str}

CÂU HỎI NGƯỜI DÙNG:
{req.question}

TRẢ LỜI (Tiếng Việt trang trọng, chuyên môn cao):"""

    try:
        resp = TOKEN_GUARD.client.models.generate_content(
            model=TOKEN_GUARD.model_name,
            contents=[prompt]
        )
        return {"answer": resp.text.strip()}
    except Exception as e:
        return {"answer": f"Lỗi gọi Gemini: {str(e)}"}
