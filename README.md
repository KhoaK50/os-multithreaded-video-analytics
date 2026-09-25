# Cyber Surveillance Command Center: Hệ Thống Giám Sát Hành Vi Video Thời Gian Thực & Kiểm Soát Đa Luồng

> **Học phần**: Hệ Điều Hành  
> **Giảng viên hướng dẫn**: Thầy Nguyễn Tấn Duẩn  
> **Đề tài**: *Hệ thống giám sát hành vi video thời gian thực & Phân tích bằng AI kết hợp kiểm soát đa luồng*

---

## 1. Giới Thiệu & Điểm Đột Phá

Dự án hiện thực hóa trọn vẹn các nguyên lý cốt lõi của môn **Hệ điều hành (Đa luồng, Đồng bộ hóa, Hàng đợi Bounded Buffer, Cơ chế Flow Control Drop-frame, Giám sát tài nguyên)** kết hợp với **Kiến trúc AI Đa Tầng (Edge YOLOv8 trên RTX 5060 + Cloud Gemini 3.5 Flash Lite)**:

1. **Giao diện Cyber Command Center (1280x720 HD Widescreen)**:
   - **Vùng trung tâm (900x720)**: Luồng camera góc rộng sắc nét, loại bỏ hoàn toàn các banner đè lên mặt người.
   - **Bounding Box công nghệ cao**: Khung góc ngoặc Sci-Fi (`┌ ┐ └ ┘`) bám theo người, laptop, điện thoại, chai nước... đổi màu động theo mức độ an toàn (Xanh Cyber $\rightarrow$ Vàng Cảnh báo $\rightarrow$ Đỏ Nguy hiểm).
   - **Bảng Telemetry kính đen (380x720)**: Render font tiếng Việt Unicode chuẩn bằng Pillow (chống vỡ font/hỏi chấm), hiển thị chẩn đoán tự nhiên như người thật, đồng hồ LED rủi ro và biểu đồ tài nguyên CPU, RAM, VRAM GPU RTX 5060.
2. **Kiểm soát đa luồng & Drop-frame (Flow Control HĐH)**: Quản lý hàng đợi `queue.Queue` chống tràn bộ nhớ (Buffer Bloat), chủ động hủy bỏ frame trễ nhất khi tải AI tăng để giữ độ trễ luồng video xấp xỉ 0 ms.
3. **Phân luồng thông minh tiết kiệm 99.8% chi phí API**:
   - Edge AI (YOLOv8) chạy liên tục trên GPU cục bộ (140 FPS, chi phí $0).
   - Cloud AI (Gemini 3.5 Flash Lite) thẩm định ngữ cảnh sâu theo chu kỳ hoặc kích hoạt khi có sự cố, được điều phối tốc độ chống nghẽn và bảo vệ Free-tier tuyệt đối.
4. **Hỏi đáp ngữ nghĩa (Semantic Q&A) & Báo cáo thống kê**: Tự động tổng hợp tỷ lệ hành vi, timeline sự kiện và cho phép trò chuyện tự nhiên với trợ lý AI về an ninh trong khung hình.

---

## 2. Kiến Trúc Đa Luồng (OS Multithreading Model)

```
                     [Webcam / Video 30 FPS]
                                │
                                ▼
                   ┌───────────────────────────┐
                   │ Luồng 1: Producer Thread  │
                   │ (cv2.VideoCapture 30 FPS) │
                   └─────────────┬─────────────┘
                                 │
                     [Kiểm tra Queue đầy?]
                     ├── Có: HỦY FRAME CŨ NHẤT (Drop-frame)
                     └── Không: ĐẨY VÀO QUEUE
                                 │
                                 ▼
                 [RawFrameQueue: queue.Queue(maxsize=5)]
                                 │
        ┌────────────────────────┴────────────────────────┐
        ▼                                                 ▼
┌───────────────────────────────┐         ┌───────────────────────────────┐
│ Luồng 2: Edge AI Consumer     │         │ Luồng 3: Cloud AI Worker      │
│ - YOLOv8 trên RTX 5060 GPU    │         │ - Gemini 3.5 Flash Lite       │
│ - Tốc độ: 140 FPS (7ms/frame) │         │ - Chẩn đoán tự do người thật  │
│ - Bounding Box & Target Track │         │ - Đánh giá rủi ro (0-10 điểm) │
└───────────────┬───────────────┘         └───────────────┬───────────────┘
                │                                         │
                └────────────────┬────────────────────────┘
                                 ▼
                 ┌───────────────────────────────┐
                 │ Luồng 4: Main UI Compositor   │
                 │ - Left: 900x720 Cyber Camera  │
                 │ - Right: 380x720 Glass HUD    │
                 │ - Đo % CPU, RAM, VRAM GPU     │
                 └───────────────┬───────────────┘
                                 ▼
               [CYBER COMMAND CENTER 1280x720 HUD]
```

---

## 3. Cấu Trúc Thư Mục Dự Án

```
os-multithreaded-video-analytics/
├── core/                           # [CORE ENGINE] Nhân đa luồng & AI
│   ├── __init__.py
│   ├── config.py                   # Cấu hình kích thước HUD, ngưỡng YOLO, nhãn, FPS
│   ├── cyber_hud.py                # Renderer Cyber HUD 1280x720 & Font tiếng Việt Unicode
│   ├── capture.py                  # Producer Thread: Đọc Camera & Drop-Frame Flow Control
│   ├── detector.py                 # Consumer Thread: X-CLIP 16-frame trên CUDA GPU
│   ├── metrics.py                  # Resource Monitor: Đo % CPU, % RAM, VRAM, FPS (psutil)
│   ├── event_logger.py             # Event Engine: Nhật ký sự kiện, trích xuất clip cảnh báo
│   └── gemini_analyzer.py          # Cloud AI: Google GenAI SDK (Semantic Q&A & Video Diagnosis)
├── ui/                             # [GIAO DIỆN WEB] Dashboard người dùng
│   ├── __init__.py
│   └── app.py                      # Giao diện Web Streamlit (Video upload, Biểu đồ %, Chatbot)
├── tests/                          # [KIỂM THỬ & BENCHMARK HĐH]
│   ├── __init__.py
│   ├── test_command_center.py      # Script chạy trực tiếp Cyber Command Center 1280x720
│   ├── test_producer_consumer.py   # Benchmark chứng minh cơ chế Drop-frame của HĐH
│   ├── test_video_file.py          # Nhập file video -> Xuất video dán nhãn thành phẩm
│   ├── test_smart_ai_cam.py        # Camera AI chẩn đoán tự nhiên cơ bản
│   └── test_gemini_video.py        # Kiểm thử phân tích video với Gemini Flash Lite
├── recordings/                     # Lưu trữ video xuất bản và ảnh snapshot cảnh báo
├── requirements.txt                # Danh sách thư viện Python
├── .env.example                    # File mẫu cấu hình Gemini API Key
├── run_camera.bat                  # File 1-Click mở Camera Cyber Command Center cho Windows
├── run_web.bat                     # File 1-Click mở Giao diện Web Streamlit cho Windows
├── main.py                         # Điểm khởi chạy chính toàn hệ thống
└── README.md                       # Tài liệu hướng dẫn đồ án
```

---

## 4. Hướng Dẫn Cài Đặt (Dành Cho Thành Viên Nhóm)

Dự án tương thích cả máy có card rời NVIDIA và máy laptop văn phòng thông thường (CPU-only).

### Bước 1: Clone repository và tạo môi trường ảo (Khuyên dùng)
```powershell
git clone <URL_REPO_CUA_NHOM>
cd os-multithreaded-video-analytics

# Tạo môi trường ảo Python (khuyên dùng Python 3.10 - 3.12)
python -m venv venv
.\venv\Scripts\activate
```

### Bước 2: Cài đặt PyTorch
- **Nếu máy có card rời NVIDIA RTX (CUDA)**:
  ```powershell
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu132
  # Hoặc CUDA 12.1/12.4 tùy phiên bản driver của bạn:
  # pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
  ```
- **Nếu máy chỉ dùng CPU**:
  ```powershell
  pip install torch torchvision
  ```

### Bước 3: Cài đặt các thư viện cần thiết
```powershell
pip install -r requirements.txt
```

### Bước 4: Cấu hình Gemini API Key (Tùy chọn - Chạy Offline 100% nếu không có Key)
- Hệ thống hỗ trợ chế độ **Edge AI Offline 100%**: YOLOv8-Pose và bộ lọc động học vẫn tự động chạy cục bộ trên GPU/CPU, vẽ khung xương 17 điểm và dán nhãn tư thế mà không cần kết nối mạng hay API Key.
- Nếu muốn kích hoạt tính năng **Hội chẩn đa phương thức Cloud AI (Gemini 3.5 Flash Lite)**:
  1. Lấy API Key miễn phí tại [Google AI Studio](https://aistudio.google.com/app/apikey).
  2. Sao chép `.env.example` thành `.env`:
     ```powershell
     copy .env.example .env
     ```
  3. Điền API Key của bạn vào biến `GEMINI_API_KEY` trong `.env`.

---

## 5. Hướng Dẫn Vận Hành (Các Chế Độ Chạy)

### 🚀 Cách 1: Chạy 1-Click (Dành cho thành viên nhóm trên Windows)
- **Mở Giao Diện Web Hợp Nhất (FastAPI + CapCut Timeline + Live Camera)**: Click đúp chuột vào file `run_web.bat`.
  *(Hệ thống có cơ chế Readiness Probe tự động kiểm tra cổng 8000 đạt HTTP 200 OK rồi mới mở trình duyệt, không bao giờ gặp lỗi ERR_CONNECTION_REFUSED).*
- **Mở Camera Cyber Command Center OpenCV (1280x720 HUD)**: Click đúp chuột vào file `run_camera.bat`.

---

### 🌐 Cách 2: Khởi Chạy Từ Terminal / PowerShell
```powershell
# Chạy Giao diện Web Cyber Surveillance Hub (Mặc định: http://127.0.0.1:8000):
python main.py

# Hoặc khởi chạy cửa sổ OpenCV Desktop Cyber HUD:
python main.py --mode hud

# Chạy với nguồn camera hoặc file video cụ thể:
python main.py --source 0
python main.py --source recordings/video_mau.mp4
```

---

### 🧪 Cách 3: Chạy Toàn Bộ Bộ Kiểm Thử Tự Động (50+ Unit Tests)
Kiểm tra tính toàn vẹn của hệ thống, cơ chế ổn định ID diễn viên 4 người, trích xuất video YouTube, pipeline đa luồng và chống tràn token:
```powershell
python -m unittest discover tests
```

---

### 📊 Cách 4: Kiểm Thử Cơ Chế Drop-Frame Đa Luồng (Báo Cáo Môn HĐH)
Chạy kịch bản mô phỏng chứng minh thuật toán Producer - Consumer điều phối luồng và loại bỏ frame cũ khi hàng đợi buffer bị nghẽn:
```powershell
python tests/test_producer_consumer.py
```

---

## 6. Hướng Dẫn Chia Sẻ Cho Nhóm & Nộp Bài

1. **Đưa lên GitHub**:
   - Kho lưu trữ đã có sẵn file `.gitignore` chặt chẽ (đã chặn tuyệt đối `.env`, cache model `*.pt`, file video nặng `*.mp4`, và các file tạm).
   - Đảm bảo không bao giờ commit nhầm file chứa API Key cá nhân.
2. **Chạy lần đầu trên máy mới**:
   - Khi chạy lần đầu, Ultralytics sẽ tự động tải trọng số nhẹ `yolov8n-pose.pt` về máy.
   - Quá trình nạp mô hình chạy bất đồng bộ ở chế độ nền (background warmup), đảm bảo Web Server mở tức thì trong < 1 giây.

