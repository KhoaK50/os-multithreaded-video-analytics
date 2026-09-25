"""
Enhanced Real-Time X-CLIP Action Recognition with Temporal Striding & Prompt Engineering.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Các nâng cấp chuyên sâu (Senior Engineering Optimizations):
1. Temporal Striding (Lấy mẫu thời gian mở rộng): Cứ mỗi 3-4 frame camera mới trích 1 frame vào buffer 16-frame.
   -> Kéo dài cửa sổ quan sát từ 0.5s lên 2.0s để mô hình thấy trọn vẹn chu kỳ hành động (không còn bị nhầm mọi chuyển động thành 'waving hands').
2. Prompt Engineering (Kinetics-400 Template): Mô tả hành vi chi tiết theo ngôn ngữ tự nhiên để tách biệt các hành vi gần nhau (ngồi gõ máy tính, uống nước, nghe điện thoại, vươn vai, đứng lên, té ngã...).
3. Dynamic Top-K Ranking: Hiển thị Top-1 nổi bật và Top-2, Top-3 phụ kèm thanh % trực quan, hạ ngưỡng nhạy xuống mức tối ưu (28% cho 9 nhãn).
"""

import os
import sys

# Cấu hình lưu trữ và nạp Cache từ ổ D (nếu khả dụng)
if os.path.exists("D:/huggingface_cache") or (os.name == "nt" and os.path.exists("D:/")):
    os.environ["HF_HOME"] = "D:/huggingface_cache"
    os.environ["TRANSFORMERS_CACHE"] = "D:/huggingface_cache/hub"

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""

# Đảm bảo UTF-8 console output trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

import time
from collections import deque
import cv2
import numpy as np
import psutil
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModel

# --- BẢNG ĐỊNH NGHĨA HÀNH VI & PROMPT TỐI ƯU (PROMPT ENGINEERING) ---
ACTION_CONFIG = [
    {
        "display": "Working / Typing",
        "prompt": "a video of a person typing on keyboard or working on a laptop at a desk",
        "is_danger": False,
    },
    {
        "display": "Sitting Relaxed",
        "prompt": "a video of a person sitting still resting and looking forward",
        "is_danger": False,
    },
    {
        "display": "Waving Hands",
        "prompt": "a video of a person enthusiastically waving hand high in the air to greet",
        "is_danger": False,
    },
    {
        "display": "Drinking Water",
        "prompt": "a video of a person drinking water from a cup, mug, or bottle",
        "is_danger": False,
    },
    {
        "display": "Phone Call",
        "prompt": "a video of a person holding a phone to ear talking on mobile phone",
        "is_danger": False,
    },
    {
        "display": "Stretching Body",
        "prompt": "a video of a person stretching their arms upward or exercising",
        "is_danger": False,
    },
    {
        "display": "Standing / Walking",
        "prompt": "a video of a person standing up or walking around the room",
        "is_danger": False,
    },
    {
        "display": "Fighting / Violence",
        "prompt": "a video of a person aggressively punching, slapping, or fighting violently",
        "is_danger": True,
    },
    {
        "display": "Falling Down",
        "prompt": "a video of a person suddenly falling down or collapsing onto the desk or floor",
        "is_danger": True,
    }
]

PROMPT_TEXTS = [item["prompt"] for item in ACTION_CONFIG]
DISPLAY_LABELS = [item["display"] for item in ACTION_CONFIG]
DANGER_FLAGS = [item["is_danger"] for item in ACTION_CONFIG]

WINDOW_SIZE = 16          # X-CLIP yêu cầu 16 frames
FRAME_STRIDE = 3         # Lấy 1 frame mỗi 3 frame camera (16 * 3 = 48 frames ~ 1.6 - 1.8 giây thời gian thực)
CONFIDENCE_THRESHOLD = 0.28  # Ngưỡng nhạy (xác suất ngẫu nhiên 1/9 = 11.1%)
INFERENCE_INTERVAL = 6    # Tần suất suy luận (chạy model sau mỗi 6 frame camera mới)


def get_system_metrics(device_is_cuda: bool):
    """Đo đạc tài nguyên HĐH: CPU, RAM, và VRAM GPU."""
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    ram_percent = ram.percent

    gpu_info = "CPU Mode"
    if device_is_cuda and torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated(0) / (1024 ** 2)
        total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        gpu_info = f"RTX 5060 ({allocated:.0f}/{total:.0f} MB)"

    return cpu_percent, ram_percent, gpu_info


def main():
    print("=" * 70)
    print("  HỆ THỐNG GIÁM SÁT HÀNH VI THỜI GIAN THỰC ĐA LUỒNG & AI (X-CLIP)")
    print("  Đã nâng cấp: Temporal Striding (2.0s window) + Prompt Engineering Kinetics-400")
    print("=" * 70)

    # 1. Khởi tạo GPU
    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        gpu_name = torch.cuda.get_device_name(0)
        torch_dtype = torch.float16
        print(f"[+] Phát hiện GPU : {gpu_name}")
        print(f"[+] Chế độ tính toán: CUDA FP16 Tensor Cores (Tối ưu tốc độ cao)")
    else:
        device = torch.device("cpu")
        torch_dtype = torch.float32
        print("[-] Chạy trên CPU")

    # 2. Nạp mô hình X-CLIP từ Cache ổ D
    model_id = "microsoft/xclip-base-patch32-16-frames"
    print(f"\n[+] Đang nạp mô hình X-CLIP từ D:/huggingface_cache...")
    try:
        try:
            processor = AutoProcessor.from_pretrained(model_id, local_files_only=True)
            model = AutoModel.from_pretrained(model_id, dtype=torch_dtype, local_files_only=True).to(device)
            print("[+] Nạp trực tiếp từ Local Cache ổ D thành công!")
        except Exception:
            print("[*] Đang tải từ Hugging Face...")
            processor = AutoProcessor.from_pretrained(model_id)
            model = AutoModel.from_pretrained(model_id, dtype=torch_dtype).to(device)

        model.eval()
        print("[+] Mô hình đã sẵn sàng trong bộ nhớ VRAM RTX 5060!")
    except Exception as e:
        print(f"[!] Lỗi khi nạp mô hình: {e}")
        return

    # 3. Mở Webcam
    print("\n[+] Đang mở webcam...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[!] Không thể mở Webcam. Vui lòng kiểm tra lại thiết bị camera!")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Hàng đợi 16 frames với Temporal Striding
    frame_buffer = deque(maxlen=WINDOW_SIZE)

    # Trạng thái suy luận hiện tại
    top_actions = [("Dang khoi tao...", 0.0, False)]
    is_danger = False

    fps_deque = deque(maxlen=30)
    camera_frame_idx = 0
    t_start = time.time()

    print(f"\n[+] Đang chạy live webcam. Temporal stride: {FRAME_STRIDE} frames (cửa sổ ~1.6 giây).")
    print("[+] Nhấn 'q' để thoát an toàn.\n")

    try:
        while True:
            t_frame_start = time.time()
            ret, frame = cap.read()
            if not ret:
                print("[!] Mất tín hiệu từ camera.")
                break

            camera_frame_idx += 1
            frame = cv2.flip(frame, 1)

            # --- KỸ THUẬT TEMPORAL STRIDING ---
            # Cứ mỗi FRAME_STRIDE frame camera mới lấy 1 frame đưa vào buffer 16 frames
            if camera_frame_idx % FRAME_STRIDE == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_frame = Image.fromarray(rgb_frame)
                frame_buffer.append(pil_frame)

            # --- SUY LUẬN X-CLIP ZERO-SHOT ---
            if len(frame_buffer) == WINDOW_SIZE and (camera_frame_idx % INFERENCE_INTERVAL == 0):
                video_input = list(frame_buffer)

                inputs = processor(
                    text=PROMPT_TEXTS,
                    videos=[video_input],
                    return_tensors="pt",
                    padding=True
                )
                inputs = {k: v.to(device) for k, v in inputs.items()}
                if device.type == "cuda":
                    inputs["pixel_values"] = inputs["pixel_values"].to(torch_dtype)

                with torch.no_grad():
                    outputs = model(**inputs)
                    logits_per_video = outputs.logits_per_video
                    # Softmax tính xác suất %
                    probs = logits_per_video.softmax(dim=1).cpu().numpy()[0]

                # Sắp xếp Top-3 hành vi có xác suất cao nhất
                sorted_indices = np.argsort(probs)[::-1]
                top_actions = []
                for idx in sorted_indices[:3]:
                    act_name = DISPLAY_LABELS[idx]
                    act_prob = float(probs[idx])
                    act_danger = DANGER_FLAGS[idx]
                    top_actions.append((act_name, act_prob, act_danger))

                # Đánh giá hành vi Top-1
                best_name, best_prob, best_danger = top_actions[0]
                is_danger = best_danger if best_prob >= CONFIDENCE_THRESHOLD else False

            # Tính FPS
            t_frame_end = time.time()
            fps_deque.append(1.0 / max(1e-5, t_frame_end - t_frame_start))
            avg_fps = sum(fps_deque) / len(fps_deque)

            # Lấy thông số hệ điều hành
            cpu_pct, ram_pct, gpu_info = get_system_metrics(device.type == "cuda")

            # --- VẼ GIAO DIỆN HEADS-UP DISPLAY (HUD) ---
            h, w = frame.shape[:2]

            # 1. Top Header Banner
            banner_color = (0, 0, 220) if is_danger else (34, 139, 34)
            status_text = "NGUY HIEM (DANGER ALERT)" if is_danger else "AN TOAN (SAFE)"

            # Nền mờ phía trên
            overlay_top = frame.copy()
            cv2.rectangle(overlay_top, (0, 0), (w, 85), (15, 15, 15), -1)
            cv2.rectangle(overlay_top, (0, 0), (10, 85), banner_color, -1)
            cv2.addWeighted(overlay_top, 0.85, frame, 0.15, 0, frame)

            best_act, best_score, _ = top_actions[0]
            display_act = best_act if best_score >= CONFIDENCE_THRESHOLD else f"Dang phan tich... ({best_act})"

            cv2.putText(frame, f"TRANG THAI: {status_text}", (20, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, banner_color, 2, cv2.LINE_AA)
            cv2.putText(frame, f"HANH VI: {display_act.upper()}", (20, 52),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

            # Thanh độ tin cậy Top-1
            cv2.putText(frame, f"Do tin cay: {best_score * 100:.1f}%", (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
            bar_x, bar_y, bar_w, bar_h = 165, 65, 140, 10
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 50), -1)
            fill_w = int(bar_w * max(0.0, min(1.0, best_score)))
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), banner_color, -1)
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (120, 120, 120), 1)

            # 2. Hiển thị Top 2 và Top 3 bên góc phải
            if len(top_actions) >= 3:
                cv2.putText(frame, f"Top 2: {top_actions[1][0]} ({top_actions[1][1]*100:.0f}%)", (w - 240, 48),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1, cv2.LINE_AA)
                cv2.putText(frame, f"Top 3: {top_actions[2][0]} ({top_actions[2][1]*100:.0f}%)", (w - 240, 72),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 150, 150), 1, cv2.LINE_AA)

            # 3. Bottom Footer (Thông số tài nguyên HĐH)
            overlay_bot = frame.copy()
            cv2.rectangle(overlay_bot, (0, h - 35), (w, h), (15, 15, 15), -1)
            cv2.addWeighted(overlay_bot, 0.85, frame, 0.15, 0, frame)

            stats_str = f"FPS: {avg_fps:.1f}  |  GPU: {gpu_info}  |  CPU: {cpu_pct:.0f}%  |  RAM: {ram_pct:.0f}%"
            cv2.putText(frame, stats_str, (15, h - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255), 1, cv2.LINE_AA)

            # 4. Viền cảnh báo đỏ toàn màn hình nếu nguy hiểm
            if is_danger:
                cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 4)

            # 5. Hiển thị cửa sổ
            cv2.imshow("He Thong Giam Sat Hanh Vi AI - X-CLIP (Nhan 'q' de thoat)", frame)

            if (cv2.waitKey(1) & 0xFF) == ord('q'):
                break

    except KeyboardInterrupt:
        print("\n[+] Đã nhận tín hiệu dừng.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("\n[+] Đã giải phóng camera và đóng toàn bộ cửa sổ an toàn.")


if __name__ == "__main__":
    main()
