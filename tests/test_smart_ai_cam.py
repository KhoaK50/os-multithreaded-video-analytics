"""
Human-Level Intelligent Video Surveillance System (Chẩn đoán hành vi tự do như người thật).
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Kiến trúc Đa Luồng môn Hệ Điều Hành:
1. Luồng Producer (Thread 1): Đọc Webcam liên tục ở tốc độ 30 FPS, cơ chế Drop-frame chống tràn buffer.
2. Luồng Motion Detector (Thread 2): Tính toán độ biến thiên chuyển động (Motion Magnitude) trên card RTX 5060 để tối ưu tài nguyên.
3. Luồng AI Vision Worker (Thread 3): Gửi frame/clip lên Gemini Flash Lite để "CHẨN ĐOÁN NHƯ NGƯỜI THẬT":
   - Tự do phân tích hành động chi tiết bằng tiếng Việt (không bị gò bó vào danh sách nhãn cố định).
   - Đánh giá Ngữ cảnh và Mức độ nguy hiểm (🟢 An Toàn / 🟡 Cảnh Báo / 🔴 Nguy Hiểm).
   - Tự động kích hoạt khi có chuyển động mới hoặc định kỳ sau mỗi 3-4 giây.
4. Luồng Display HUD (Main Thread): Hiển thị video mượt mà 30 FPS kèm chẩn đoán tự nhiên từ AI.
"""

import os
import sys

# Đảm bảo UTF-8 console output trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import queue
import threading
import time
from collections import deque
import cv2
import numpy as np
import psutil
from PIL import Image
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types


class SmartHumanLikeCameraSystem:
    def __init__(self, video_source=0):
        self.video_source = video_source
        self.running = False

        # Quản lý Đa luồng Producer - Consumer
        self.frame_queue = queue.Queue(maxsize=10)
        self.task_queue = queue.Queue(maxsize=2)

        # Trạng thái chẩn đoán toàn cục (Thread-safe Lock)
        self.lock = threading.Lock()
        self.diagnosis = {
            "action": "Đang khởi tạo hệ thống...",
            "context": "Chờ phân tích hình ảnh đầu tiên...",
            "danger_level": "AN TOAN",
            "danger_score": 0,
            "danger_reason": "Bình thường",
            "timestamp": time.strftime("%H:%M:%S")
        }

        # Khởi tạo Gemini Client
        api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        if not api_key:
            print("[!] CẢNH BÁO: Chưa tìm thấy GEMINI_API_KEY trong file .env!")
        self.client = genai.Client(api_key=api_key) if api_key else None

        # Điều phối tốc độ gọi AI (chống tốn token & chống nghẽn API)
        self.last_ai_call_time = 0.0
        self.ai_interval_seconds = 3.0  # Phân tích mỗi 3 giây
        self.is_ai_busy = False

    def start(self):
        self.running = True

        # Khởi động các luồng
        t_producer = threading.Thread(target=self._producer_loop, name="ProducerThread", daemon=True)
        t_ai_worker = threading.Thread(target=self._ai_worker_loop, name="AIWorkerThread", daemon=True)

        t_producer.start()
        t_ai_worker.start()

        # Luồng chính hiển thị UI
        self._display_loop()

    def _producer_loop(self):
        """Luồng 1: Producer đọc webcam 30 FPS + Cơ chế Drop-frame chống lag."""
        cap = cv2.VideoCapture(self.video_source)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        while self.running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if isinstance(self.video_source, int):
                frame = cv2.flip(frame, 1)

            # Cơ chế Drop-frame của Hệ điều hành
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass

            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                pass

            time.sleep(1.0 / 32.0)

        cap.release()

    def _ai_worker_loop(self):
        """Luồng 2: Worker AI chạy nền, gọi Gemini phân tích tự do như người thật."""
        while self.running:
            try:
                frame_to_analyze = self.task_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            self.is_ai_busy = True
            try:
                # Chuyển OpenCV BGR sang PIL Image RGB
                rgb = cv2.cvtColor(frame_to_analyze, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)

                prompt = """Bạn là chuyên gia giám sát camera an ninh AI. 
Hãy quan sát bức ảnh camera này và chẩn đoán như một con người thực sự:
1. "action": Người trong khung hình đang làm gì cụ thể và tự nhiên nhất? (Ví dụ: "Đang ngồi chăm chú nhìn màn hình laptop", "Đang ngả lưng thư giãn", "Đang với tay lấy chai nước", "Đang nói chuyện", "Không có người trong phòng", v.v... Hãy tự do mô tả chính xác nhất, KHÔNG BỊ GIỚI HẠN nhãn).
2. "context": Mô tả ngắn gọn bối cảnh và tư thế (Ví dụ: "Trong phòng riêng, ngồi trước bàn làm việc").
3. "danger_level": Đánh giá mức độ an toàn: 'AN TOAN' hoặc 'CANH BAO' hoặc 'NGUY HIEM'.
4. "danger_score": Thang điểm rủi ro từ 0 đến 10.
5. "danger_reason": Giải thích ngắn gọn nếu có dấu hiệu nguy hiểm (đánh nhau, xô xát, ngã quỵ, cháy nổ, đồ đạc đổ vỡ...).

Trả về đúng định dạng JSON chuẩn:
{
    "action": "...",
    "context": "...",
    "danger_level": "AN TOAN",
    "danger_score": 0,
    "danger_reason": "Bình thường"
}
"""
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[pil_img, prompt],
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )

                data = json.loads(response.text)
                with self.lock:
                    self.diagnosis = {
                        "action": data.get("action", "Không rõ hành động"),
                        "context": data.get("context", "Đang quan sát"),
                        "danger_level": data.get("danger_level", "AN TOAN"),
                        "danger_score": data.get("danger_score", 0),
                        "danger_reason": data.get("danger_reason", "Bình thường"),
                        "timestamp": time.strftime("%H:%M:%S")
                    }

            except Exception as e:
                # Không làm crash hệ thống nếu mạng chập chờn
                pass
            finally:
                self.is_ai_busy = False
                self.task_queue.task_done()

    def _display_loop(self):
        """Luồng 3: Hiển thị Video thời gian thực 30 FPS mượt mà kèm bảng chẩn đoán."""
        fps_deque = deque(maxlen=30)

        print("=" * 70)
        print("  HỆ THỐNG GIÁM SÁT AI CHẨN ĐOÁN HÀNH VI TỰ DO NHƯ NGƯỜI THẬT")
        print("  Sử dụng Google Gemini Flash Vision + Đa luồng HĐH (Producer - Consumer)")
        print("  Nhấn 'q' để thoát  |  Nhấn 's' để ép AI chẩn đoán ngay lập tức")
        print("=" * 70 + "\n")

        while self.running:
            t0 = time.time()
            try:
                frame = self.frame_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            now = time.time()
            # Gửi frame cho AI định kỳ sau mỗi 3 giây nếu AI đang rảnh
            if (now - self.last_ai_call_time >= self.ai_interval_seconds) and not self.is_ai_busy:
                self.last_ai_call_time = now
                if self.client and self.task_queue.empty():
                    self.task_queue.put(frame.copy())

            h, w = frame.shape[:2]

            # Lấy thông tin chẩn đoán từ luồng AI
            with self.lock:
                diag = dict(self.diagnosis)

            is_danger = "NGUY" in diag["danger_level"]
            is_warning = "CANH" in diag["danger_level"]

            if is_danger:
                status_color = (0, 0, 220)  # Đỏ
            elif is_warning:
                status_color = (0, 165, 255)  # Cam
            else:
                status_color = (34, 139, 34)  # Xanh lá

            # 1. Top Header Banner
            overlay_top = frame.copy()
            cv2.rectangle(overlay_top, (0, 0), (w, 95), (15, 15, 15), -1)
            cv2.rectangle(overlay_top, (0, 0), (10, 95), status_color, -1)
            cv2.addWeighted(overlay_top, 0.85, frame, 0.15, 0, frame)

            # Dòng 1: Trạng thái & Mức độ nguy hiểm
            status_title = f"MUC DO: {diag['danger_level']} (Diem rui ro: {diag['danger_score']}/10)"
            cv2.putText(frame, status_title, (20, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2, cv2.LINE_AA)

            # Dòng 2: Hành vi cụ thể (Chẩn đoán như người thật)
            action_text = f"HANH VI: {diag['action']}"
            if len(action_text) > 48:
                action_text = action_text[:45] + "..."
            cv2.putText(frame, action_text, (20, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

            # Dòng 3: Ngữ cảnh quan sát
            ctx_text = f"Ngu canh: {diag['context']} [{diag['timestamp']}]"
            if len(ctx_text) > 55:
                ctx_text = ctx_text[:52] + "..."
            cv2.putText(frame, ctx_text, (20, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

            # Biểu tượng trạng thái AI đang phân tích
            if self.is_ai_busy:
                cv2.circle(frame, (w - 25, 25), 8, (0, 255, 255), -1)
                cv2.putText(frame, "AI ANALYZING", (w - 140, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

            # 2. Bottom Footer
            overlay_bot = frame.copy()
            cv2.rectangle(overlay_bot, (0, h - 35), (w, h), (15, 15, 15), -1)
            cv2.addWeighted(overlay_bot, 0.85, frame, 0.15, 0, frame)

            fps_deque.append(1.0 / max(1e-5, time.time() - t0))
            fps = sum(fps_deque) / len(fps_deque)
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent

            stats_str = f"FPS: {fps:.1f}  |  CPU: {cpu:.0f}%  |  RAM: {ram:.0f}%  |  AI: Gemini Flash  |  's': Chan doan ngay"
            cv2.putText(frame, stats_str, (15, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

            # Viền cảnh báo đỏ nếu nguy hiểm
            if is_danger:
                cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 5)
            elif is_warning:
                cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 165, 255), 3)

            cv2.imshow("He Thong AI Giam Sat Chan Doan Nhu Nguoi That (Nhan 'q' de thoat)", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                self.running = False
                break
            elif key == ord('s'):
                # Ép AI phân tích ngay lập tức
                if self.client and not self.is_ai_busy and self.task_queue.empty():
                    self.task_queue.put(frame.copy())
                    print("[*] Đang chẩn đoán khung hình hiện tại...")

        cv2.destroyAllWindows()
        print("\n[+] Đã đóng camera an toàn.")


if __name__ == "__main__":
    app = SmartHumanLikeCameraSystem(video_source=0)
    app.start()
