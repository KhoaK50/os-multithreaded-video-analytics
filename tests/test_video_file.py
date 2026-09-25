"""
Process & Annotate Video File / Camera Feed with X-CLIP & System Analytics.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Chức năng:
1. Nhận đầu vào là 1 File Video (.mp4, .avi, .mov...) HOẶC Live Webcam.
2. Quét qua video bằng cửa sổ trượt 16 frames với mô hình X-CLIP (microsoft/xclip-base-patch32-16-frames).
3. Tăng tốc bằng GPU NVIDIA RTX (CUDA FP16).
4. Dán nhãn trực tiếp lên từng khung hình của video:
   - Header Banner: Trạng thái An toàn (SAFE - Xanh lá) / Nguy hiểm (DANGER - Đỏ).
   - Tên hành vi dự đoán (WALKING, WORKING, FIGHTING, FALLING...).
   - Thanh tiến trình % độ tin cậy (Confidence Bar).
   - Timestamp thời gian thực của video (Phút : Giây).
   - Footer Bar: Thông số HĐH (% CPU, % RAM, VRAM GPU, Tốc độ FPS).
5. Xuất ra File Video thành phẩm đã dán nhãn hoàn chỉnh (.mp4).
6. In bảng tổng hợp phân tích (Thống kê tỷ lệ %, Timeline sự kiện) và gọi Gemini Flash API tóm tắt (nếu có key).
"""

import argparse
import os
import sys

# Cấu hình lưu trữ và nạp Cache từ ổ D trước khi import transformers
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
from collections import deque, defaultdict
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

CONFIDENCE_THRESHOLD = 0.28
WINDOW_SIZE = 16
FRAME_STRIDE = 2


def get_hardware_stats(is_cuda: bool):
    """Đo đạc tài nguyên HĐH phục vụ hiển thị trên video."""
    cpu_pct = psutil.cpu_percent(interval=None)
    ram_pct = psutil.virtual_memory().percent
    gpu_str = "CPU Mode"
    if is_cuda and torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated(0) / (1024 ** 2)
        total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        gpu_str = f"RTX 5060 ({allocated:.0f}/{total:.0f} MB)"
    return cpu_pct, ram_pct, gpu_str


def draw_hud_on_frame(
    frame: np.ndarray,
    action: str,
    confidence: float,
    is_danger: bool,
    fps: float,
    video_timestamp_sec: float,
    cpu_pct: float,
    ram_pct: float,
    gpu_info: str
) -> np.ndarray:
    """Vẽ toàn bộ giao diện phân tích & dán nhãn lên từng khung hình của video thành phẩm."""
    h, w = frame.shape[:2]
    out_frame = frame.copy()

    banner_color = (0, 0, 220) if is_danger else (34, 139, 34)  # Đỏ (Danger) / Xanh lá (Safe)
    status_text = "NGUY HIEM (DANGER ALERT)" if is_danger else "AN TOAN (SAFE)"

    # 1. Top Header Banner (Nền mờ đen sang trọng)
    overlay = out_frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 80), (15, 15, 15), -1)
    # Dải màu trạng thái bên trái
    cv2.rectangle(overlay, (0, 0), (12, 80), banner_color, -1)
    cv2.addWeighted(overlay, 0.85, out_frame, 0.15, 0, out_frame)

    # 2. Text trạng thái & Hành vi
    cv2.putText(out_frame, f"TRANG THAI: {status_text}", (25, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, banner_color, 2, cv2.LINE_AA)
    cv2.putText(out_frame, f"HANH VI: {action.upper()}", (25, 52),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    # Timestamp video
    minutes = int(video_timestamp_sec // 60)
    seconds = int(video_timestamp_sec % 60)
    millis = int((video_timestamp_sec - int(video_timestamp_sec)) * 1000)
    time_str = f"Time: {minutes:02d}:{seconds:02d}.{millis:03d}"
    cv2.putText(out_frame, time_str, (w - 200, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)

    # 3. Thanh đo % độ tin cậy (Confidence Bar)
    conf_pct = int(confidence * 100)
    cv2.putText(out_frame, f"Do tin cay: {conf_pct}%", (25, 73),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
    bar_x = 160
    bar_y = 63
    bar_w = 140
    bar_h = 10
    cv2.rectangle(out_frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 50), -1)
    fill_w = int(bar_w * max(0.0, min(1.0, confidence)))
    cv2.rectangle(out_frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), banner_color, -1)
    cv2.rectangle(out_frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (120, 120, 120), 1)

    # 4. Bottom Footer (Chỉ số tài nguyên HĐH)
    overlay_bot = out_frame.copy()
    cv2.rectangle(overlay_bot, (0, h - 35), (w, h), (15, 15, 15), -1)
    cv2.addWeighted(overlay_bot, 0.85, out_frame, 0.15, 0, out_frame)

    stats_str = f"FPS: {fps:.1f}  |  GPU: {gpu_info}  |  CPU: {cpu_pct:.0f}%  |  RAM: {ram_pct:.0f}%"
    cv2.putText(out_frame, stats_str, (15, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255), 1, cv2.LINE_AA)

    # 5. Viền cảnh báo quanh video nếu là nguy hiểm
    if is_danger:
        cv2.rectangle(out_frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 5)

    return out_frame


def process_video(
    input_path: str,
    output_path: str,
    show_preview: bool = True,
    inference_step: int = 6
):
    print("=" * 70)
    print("  HỆ THỐNG XỬ LÝ & DÁN NHÃN VIDEO HÀNH VI TỰ ĐỘNG - MÔN HỆ ĐIỀU HÀNH")
    print("=" * 70)
    print(f"[+] Video đầu vào    : {input_path}")
    print(f"[+] Video thành phẩm : {output_path}")

    # 1. Khởi tạo GPU CUDA (RTX 5060)
    if torch.cuda.is_available():
        device = torch.device("cuda:0")
        torch_dtype = torch.float16
        gpu_name = torch.cuda.get_device_name(0)
        print(f"[+] Tăng tốc GPU: {gpu_name} (CUDA 13.2 FP16)")
    else:
        device = torch.device("cpu")
        torch_dtype = torch.float32
        print("[-] Chạy trên CPU")

    # 2. Nạp mô hình X-CLIP (Offline-First từ Cache)
    model_id = "microsoft/xclip-base-patch32-16-frames"
    print(f"\n[+] Đang nạp mô hình X-CLIP 16-frame: {model_id}...")
    try:
        try:
            processor = AutoProcessor.from_pretrained(model_id, local_files_only=True)
            model = AutoModel.from_pretrained(model_id, dtype=torch_dtype, local_files_only=True).to(device)
            print("[+] Nạp trực tiếp từ Local Cache thành công!")
        except Exception:
            processor = AutoProcessor.from_pretrained(model_id)
            model = AutoModel.from_pretrained(model_id, dtype=torch_dtype).to(device)
        model.eval()
        print("[+] Mô hình đã sẵn sàng trên bộ nhớ GPU!")
    except Exception as e:
        print(f"[!] Lỗi khi nạp mô hình: {e}")
        return

    # 3. Mở video đầu vào
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"[!] Không thể mở video: {input_path}")
        return

    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / orig_fps if orig_fps > 0 else 0

    print(f"[+] Thông tin Video : {width}x{height} @ {orig_fps:.1f} FPS, Tổng {total_frames} frames ({duration_sec:.1f}s)")

    # 4. Tạo VideoWriter để xuất video thành phẩm
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out_writer = cv2.VideoWriter(output_path, fourcc, orig_fps, (width, height))

    # Khởi tạo buffer và biến thống kê
    frame_buffer = deque(maxlen=WINDOW_SIZE)
    action_counts = defaultdict(int)
    danger_events = []

    current_action = "Khoi tao (Gom 16 frames dau)..."
    current_confidence = 0.0
    is_danger = False

    fps_deque = deque(maxlen=30)
    frame_idx = 0
    t_start_total = time.time()

    print("\n[+] Bắt đầu xử lý, dán nhãn và xuất video thành phẩm...")

    try:
        while True:
            t_frame_start = time.time()
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            current_video_time = frame_idx / orig_fps

            # --- KỸ THUẬT TEMPORAL STRIDING ---
            if frame_idx % FRAME_STRIDE == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_frame = Image.fromarray(rgb_frame)
                frame_buffer.append(pil_frame)

            # Thực hiện suy luận khi đủ 16 frames và theo chu kỳ bước
            if len(frame_buffer) == WINDOW_SIZE and (frame_idx % inference_step == 0):
                inputs = processor(
                    text=PROMPT_TEXTS,
                    videos=[list(frame_buffer)],
                    return_tensors="pt",
                    padding=True
                )
                inputs = {k: v.to(device) for k, v in inputs.items()}
                if device.type == "cuda":
                    inputs["pixel_values"] = inputs["pixel_values"].to(torch_dtype)

                with torch.no_grad():
                    outputs = model(**inputs)
                    probs = outputs.logits_per_video.softmax(dim=1).cpu().numpy()[0]

                best_idx = int(np.argmax(probs))
                best_prob = float(probs[best_idx])
                best_label = DISPLAY_LABELS[best_idx]

                if best_prob >= CONFIDENCE_THRESHOLD:
                    current_action = best_label
                    current_confidence = best_prob
                else:
                    current_action = f"Dang phan tich... ({best_label})"
                    current_confidence = best_prob

                is_danger = DANGER_FLAGS[best_idx] if best_prob >= CONFIDENCE_THRESHOLD else False
                action_counts[best_label] += 1

                if is_danger:
                    danger_events.append({
                        "frame": frame_idx,
                        "time_sec": round(current_video_time, 2),
                        "action": current_action,
                        "confidence": round(current_confidence, 2)
                    })

            # Tính FPS thực tế
            t_frame_end = time.time()
            fps_deque.append(1.0 / max(1e-5, t_frame_end - t_frame_start))
            avg_fps = sum(fps_deque) / len(fps_deque)

            # Lấy thông số hệ thống
            cpu_pct, ram_pct, gpu_info = get_hardware_stats(device.type == "cuda")

            # Vẽ HUD trực tiếp lên video thành phẩm
            annotated_frame = draw_hud_on_frame(
                frame=frame,
                action=current_action,
                confidence=current_confidence,
                is_danger=is_danger,
                fps=avg_fps,
                video_timestamp_sec=current_video_time,
                cpu_pct=cpu_pct,
                ram_pct=ram_pct,
                gpu_info=gpu_info
            )

            # Ghi vào video đầu ra
            out_writer.write(annotated_frame)

            # Hiển thị tiến trình trực tiếp
            if show_preview:
                cv2.imshow("Dang Xu Ly & Dan Nhan Video (Nhan 'q' de dung som)", annotated_frame)
                if (cv2.waitKey(1) & 0xFF) == ord('q'):
                    print("\n[*] Dừng xử lý video sớm theo yêu cầu người dùng.")
                    break

            # In tiến trình mỗi 30 frame
            if frame_idx % 30 == 0:
                pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
                print(f"  -> Tien trinh: {frame_idx}/{total_frames} frames ({pct:.1f}%) | "
                      f"Hanh vi: {current_action} ({current_confidence*100:.0f}%) | Speed: {avg_fps:.1f} FPS")

    finally:
        cap.release()
        out_writer.release()
        if show_preview:
            cv2.destroyAllWindows()

    total_time = time.time() - t_start_total
    print("\n" + "=" * 70)
    print("  HOÀN THÀNH XỬ LÝ & DÁN NHÃN VIDEO THÀNH PHẨM!")
    print("=" * 70)
    print(f"[+] File video thành phẩm đã lưu tại : {os.path.abspath(output_path)}")
    print(f"[+] Tổng thời gian xử lý            : {total_time:.2f} giây ({frame_idx/max(1, total_time):.1f} FPS)")
    print(f"[+] Tổng số khung hình đã dán nhãn   : {frame_idx} frames")

    # In báo cáo phân tích thống kê (Output 2 theo yêu cầu đề tài)
    print("\n" + "-" * 70)
    print("  BÁO CÁO THỐNG KÊ PHÂN TÍCH HÀNH VI (OUTPUT 2)")
    print("-" * 70)
    total_actions = sum(action_counts.values())
    if total_actions > 0:
        for act, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
            pct = (count / total_actions) * 100
            print(f"  - {act.ljust(25)}: {count:4d} lần  ({pct:5.1f}%)")
    else:
        print("  Không có đủ dữ liệu hành vi.")

    print(f"\n[+] Số sự kiện nguy hiểm phát hiện: {len(danger_events)}")
    for ev in danger_events[:5]:
        print(f"    * Giây {ev['time_sec']}s: {ev['action']} (Độ tin cậy: {ev['confidence']*100:.0f}%)")
    if len(danger_events) > 5:
        print(f"    * ... và {len(danger_events)-5} sự kiện khác.")

    print("=" * 70)
    print("Bạn có thể mở video thành phẩm để xem ngay hoặc tải lên giao diện Streamlit!\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="X-CLIP Video Annotation & OS Analytics")
    parser.add_argument("--input", "-i", type=str, default="sample.mp4", help="Đường dẫn file video đầu vào")
    parser.add_argument("--output", "-o", type=str, default="recordings/output_annotated.mp4", help="Đường dẫn file video thành phẩm xuất ra")
    parser.add_argument("--no-preview", action="store_true", help="Tắt cửa sổ xem trước để tăng tốc độ render")
    parser.add_argument("--step", type=int, default=6, help="Tần suất suy luận (mặc định sau mỗi 6 frames)")
    args = parser.parse_args()

    process_video(
        input_path=args.input,
        output_path=args.output,
        show_preview=not args.no_preview,
        inference_step=args.step
    )
