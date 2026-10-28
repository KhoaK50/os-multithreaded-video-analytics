# HỆ THỐNG PHÂN TÍCH HÀNH VI VIDEO ĐA LUỒNG & ĐIỀU PHỐI TÀI NGUYÊN HỆ ĐIỀU HÀNH

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-1E3A8A.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Asynchronous_Web_Core-0F766E.svg)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-CUDA_%7C_CPU_Adaptive-B91C1C.svg)](https://pytorch.org/)
[![YOLOv8-Pose](https://img.shields.io/badge/YOLOv8--Pose-17_Keypoints-4338CA.svg)](https://github.com/ultralytics/ultralytics)
[![License: MIT](https://img.shields.io/badge/License-MIT-374151.svg)](LICENSE)

Hệ thống giám sát thị giác máy tính thời gian thực và phân tích hành vi bất thường trên luồng video, được thiết kế chuyên sâu để minh họa và kiểm chứng các nguyên lý **Lập trình Đa luồng (Multithreading)**, **Đồng bộ hóa Tiến trình (Process/Thread Synchronization)**, **Quản lý Bộ đệm Hữu hạn (Bounded-Buffer Producer–Consumer)** và **Điều phối Tài nguyên Phần cứng Thích ứng (Hardware-Adaptive Resource Scheduling)** trong Hệ điều hành hiện đại.

---

## Mục Lục

1. [Tổng Quan Kiến Trúc & Năng Lực Cốt Lõi](#1-tổng-quan-kiến-trúc--năng-lực-cốt-lõi)
2. [Kiến Trúc Đa Luồng & Đồng Bộ Hóa Hệ Điều Hành](#2-kiến-trúc-đa-luồng--đồng-bộ-hóa-hệ-điều-hành)
3. [Cơ Chế Thích Ứng Phần Cứng (NVIDIA GPU & Card Đồ Họa Tích Hợp)](#3-cơ-chế-thích-ứng-phần-cứng-nvidia-gpu--card-đồ-họa-tích-hợp)
4. [Điều Phối AI Phân Tầng 3 Cấp Độ & Kiểm Soát Ngân Sách Token](#4-điều-phối-ai-phân-tầng-3-cấp-độ--kiểm-soát-ngân-sách-token)
5. [Cấu Trúc Mã Nguồn Hệ Thống](#5-cấu-trúc-mã-nguồn-hệ-thống)
6. [Yêu Cầu Hệ Thống & Hướng Dẫn Cài Đặt](#6-yêu-cầu-hệ-thống--hướng-dẫn-cài-đặt)
7. [Hướng Dẫn Vận Hành](#7-hướng-dẫn-vận-hành)
8. [Đặc Tả Giao Thức API Nội Bộ](#8-đặc-tả-giao-thức-api-nội-bộ)

---

## 1. Tổng Quan Kiến Trúc & Năng Lực Cốt Lõi

Hệ thống hợp nhất toàn bộ quy trình thu thập, suy luận thị giác máy tính, đối chiếu ngữ nghĩa đám mây và đo lường tài nguyên Hệ điều hành trên một giao diện điều hành Web duy nhất (`http://127.0.0.1:8000`), bao gồm ba phân hệ vận hành chính:

* **Phân hệ Giám Sát Camera Trực Tiếp (Live Camera Surveillance — 30 FPS):**
  * Tách biệt hoàn toàn luồng thu nhận khung hình phần cứng (`DirectShow` / `V4L2`) và luồng kết xuất luồng MJPEG khỏi luồng suy luận nặng (`YOLOv8n-Pose` 17 khớp xương + động học tư thế).
  * Duy trì tốc độ hiển thị ổn định **30 FPS** ngay cả khi mô hình AI xử lý ở tần số thấp hơn hoặc khi xảy ra nghẽn cổ chai cục bộ trên CPU.
* **Phân hệ Phân Tích Video Tải Lên & Luồng Trực Tuyến (Import Video & Stream Analytics):**
  * Hỗ trợ tải lên tệp video cục bộ (`.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`) hoặc trích xuất trực tiếp từ liên kết đa nền tảng (YouTube, TikTok, Facebook, Vimeo) thông qua `yt-dlp`.
  * Tích hợp trình cắt đoạn trực quan theo dải băng thời gian (**Timeline Trimmer**), cho phép giới hạn chính xác khoảng thời gian `[start_sec, end_sec]` cần phân tích để tối ưu hóa tài nguyên tính toán.
  * Tự động thực hiện tiền xử lý khử suy giảm chất lượng thị giác (cân bằng sáng tự động **CLAHE** trên không gian màu LAB cho cảnh thiếu sáng, khử lóa ngược sáng Gamma, và lọc nhiễu sương mù/mưa).
* **Phân hệ Thực Nghiệm & So Sánh Tài Nguyên Song Song ($Y \parallel Z$ OS Resource Lab):**
  * Cho phép khởi chạy đồng thời hai đường ống xử lý độc lập (**Luồng Y** và **Luồng Z**) trên cùng một nguồn video đầu vào với hai cấu hình tham số Hệ điều hành khác nhau:
    * Dung lượng bộ đệm hữu hạn (`Buffer Capacity`: từ `2` đến `64` khung hình).
    * Tỷ lệ phân bổ thời gian CPU (`CPU Time Share`: từ `10%` đến `100%`, cưỡng bức ngủ định kỳ ở mức độ hạt nhân luồng).
    * Chính sách giải quyết tràn bộ đệm (`Drop-Oldest / Real-time` so với `Block-Producer / FIFO Lossless`).
  * Cung cấp số liệu thực nghiệm định lượng về thông lượng (`Throughput FPS`), tổng thời gian hoàn thành, tỷ lệ đánh rơi khung hình (`Drop Rate`) và hiện tượng nghẽn cổ chai (`Starvation` / `Backpressure`).

---

## 2. Kiến Trúc Đa Luồng & Đồng Bộ Hóa Hệ Điều Hành

Hệ thống giải quyết bài toán kinh điển **Producer–Consumer với Bộ đệm Hữu hạn (Bounded-Buffer Problem)** thông qua cấu trúc `ThreadSafeBoundedBuffer` được cài đặt tường minh bằng khóa loại trừ tương hỗ (`threading.Lock` / `Mutex`) kết hợp với hai biến điều kiện (`threading.Condition`: `not_empty` và `not_full`).

### 2.1. Sơ Đồ Đường Ống 4 Luồng Giám Sát Thời Gian Thực (Live Camera Pipeline)

```text
+---------------------------------------------------------------------------------------------------+
|                        TRUNG TÂM ĐIỀU HÀNH WEB (FASTAPI ASYNCIO EVENT LOOP)                       |
+---------------------------------------------------------------------------------------------------+
         ^                                       ^                                      ^
         | (MJPEG Stream 30 FPS)                 | (SSE / REST Telemetry 2Hz)           | (JSON Eventos)
         |                                       |                                      |
+--------+--------------------+     +------------+----------------+     +---------------+-----------+
|  [Luồng Kết xuất Hình ảnh]  |     |  [Luồng Nhận diện Khung xương] |   | [Luồng Phân tích Ngữ cảnh] |
|  _render_worker (30 FPS)    |<----|  _ai_worker (Consumer #1)   |---->| _gemini_worker (Async)    |
|  - Ghép lớp phủ HUD Vector  |     |  - YOLOv8n-Pose 17 Keypoints|     | - Điều phối 3 Tầng Mô hình|
|  - Mã hóa JPEG bất đồng bộ  |     |  - Động học Ngã / Xô xát    |     | - Xoay vòng đa khóa API   |
+-----------------------------+     +--------------+--------------+     +---------------------------+
         ^                                         ^
         | (Đọc khóa _state_lock O(1))             | (Lấy mẫu khung hình mới nhất)
         +--------------------+--------------------+
                              |
                 +------------+------------+
                 |   Bộ Đệm Khung Hình     |
                 |   _state_lock (Mutex)   |
                 +------------+------------+
                              ^
                              | (Ghi đè khung hình mới nhất - Zero Queuing Delay)
                 +------------+------------+
                 | [Luồng Thu hình Camera] |
                 | _capture_worker         |
                 | - DirectShow / V4L2     |
                 | - Chuẩn hóa 1280x720    |
                 +-------------------------+
```

### 2.2. Sơ Đồ Đường Ống 3 Giai Đoạn Gối Đầu Xử Lý Video (3-Stage Overlapped Video Pipeline)

Khi phân tích tệp video trong `core/video_annotator.py`, quá trình Giải mã (Decode) — Suy luận AI (Inference) — Mã hóa H.264 (Encode) được tách thành 3 luồng chạy gối đầu nhau qua 2 bộ đệm hữu hạn `ThreadSafeBoundedBuffer`:

```text
+---------------------+       +------------------------+       +-------------------------+
|   VideoPipeReader   |       |      raw_buffer        |       |   VideoPipeInference    |
|   (Producer Thread) | ====> | ThreadSafeBoundedBuffer| ====> |  (Consumer / Producer)  |
| - Giải mã cv2.read  |       | - Mutex: Lock()        |       | - YOLOv8-Pose + ByteTrack|
| - Tiền xử lý CLAHE  |       | - Cond: not_full       |       | - Luồng quang học Farneback|
+---------------------+       | - Cond: not_empty      |       | - Nội suy Động học      |
                              +------------------------+       +------------+------------+
                                                                            |
                                                                            v
+---------------------+       +------------------------+                    |
|   VideoPipeWriter   |       |     writer_buffer      |                    |
|  (Consumer Thread)  | <==== | ThreadSafeBoundedBuffer| <==================+
| - Ống dẫn FFmpeg    |       | - Chính sách FIFO bảo  |
| - NVENC / QSV / AMF |       |   toàn 100% khung hình |
|   hoặc libx264      |       +------------------------+
+---------------------+
```

* **Ngăn chặn Tranh chấp Dữ liệu (Race Condition Prevention):** Mọi thao tác đọc/ghi vào cấu trúc hàng đợi vòng (`collections.deque`) và các biến thống kê trạng thái (`total_pushed`, `total_dropped`, `ema_wait_ms`, `lock_contention_count`) đều nằm trong vùng găng (`Critical Section`) được bảo vệ bởi `Mutex`.
* **Cơ chế Ngủ và Đánh thức (Sleep & Wakeup):** Khi bộ đệm đầy ở chế độ `FIFO`, luồng sinh (`Producer`) gọi `not_full.wait()` để giải phóng CPU về trạng thái `Blocked` thay vì sử dụng vòng lặp bận (`Busy-Waiting`), giúp tiết kiệm chu kỳ xung nhịp cho luồng suy luận AI.

---

## 3. Cơ Chế Thích Ứng Phần Cứng (NVIDIA GPU & Card Đồ Họa Tích Hợp)

Hệ thống tự động thăm dò năng lực tính toán của thiết bị đích khi khởi động (`core/config.py` và `core/video_annotator.py`) để lựa chọn cấu hình thực thi tối ưu mà không làm suy giảm độ chính xác phát hiện sự kiện:

| Tiêu chí Kỹ thuật | Máy Trạm có GPU Rời (`NVIDIA CUDA`) | Máy Tính Xách Tay Card Tích Hợp (`Intel Iris Xe / UHD`, `AMD Radeon iGPU`, `CPU`) |
| :--- | :--- | :--- |
| **Phép thử Khởi tạo Thiết bị** | Kiểm tra trực tiếp nhân `conv2d` trên `cuda:0` trong tiến trình (`< 0.15 giây`) | Tự động chuyển sang chế độ thực thi đa nhân CPU tối ưu hóa tập lệnh `AVX2` / `VNNI` |
| **Độ chính xác Suy luận** | Bán chính xác `FP16 Half-Precision` trên nhân Tensor Core | `FP32` kết hợp giới hạn luồng tính toán vật lý (`torch.set_num_threads`) chống tranh chấp Lock |
| **Chiến lược Lấy mẫu Thời gian** | Suy luận toàn phần trên từng khung hình (`infer_stride = 1`, `imgsz = 640`) | Suy luận cách nhịp (`infer_stride = 2`, `imgsz = 512/480`) kết hợp **Nội suy Tuyến tính Quỹ đạo Khớp xương** ở các khung hình xen kẽ |
| **Chuẩn hóa Luồng Quang học** | Tính toán vận tốc tương đối theo bước khung hình tiêu chuẩn | Tự động chuẩn hóa vận tốc Farneback và hệ số phân rã MHI theo khoảng thời gian thực $\Delta t$ (`step_norm`), bảo toàn bất biến ngưỡng cảnh báo |
| **Bộ Mã hóa Video Đầu ra** | Ưu tiên phần cứng chuyên dụng `h264_nvenc` | Tự động dò tìm và kích hoạt phần cứng `h264_qsv` (Intel QuickSync) $\rightarrow$ `h264_amf` (AMD) $\rightarrow$ `libx264 -preset ultrafast` |

---

## 4. Điều Phối AI Phân Tầng 3 Cấp Độ & Kiểm Soát Ngân Sách Token

Để đảm bảo tính sẵn sàng cao (`High Availability`) và tuân thủ nghiêm ngặt giới hạn tần suất gọi API (`Rate Limit`), mô-đun `core/model_orchestrator.py` cùng `core/token_guard.py` triển khai kiến trúc phân tầng tự phục hồi:

1. **Mô hình 1 — Chính (`GEMINI_TIER1_MODEL`):** Đảm nhiệm phân tích ngữ nghĩa đa phương thức chuyên sâu cho các cảnh huống phức tạp (nhiều đối tượng tương tác, góc quay khuất, ánh sáng yếu).
2. **Mô hình 2 — Dự phòng (`GEMINI_TIER2_MODEL`):** Tự động tiếp quản tức thời (`Zero-Downtime Failover`) khi Mô hình 1 gặp giới hạn hạn ngạch `HTTP 429 RESOURCE_EXHAUSTED` hoặc quá tải máy chủ `HTTP 503`.
3. **Mô hình 3 — Nội bộ (`Local Heuristic & Optical Flow Fallback`):** Khi toàn bộ khóa API đám mây đang trong chu kỳ nghỉ (`Cooldown`) hoặc hệ thống vận hành ngoại tuyến (không cấu hình `GEMINI_API_KEY`), hệ thống tự động tổng hợp báo cáo chẩn đoán từ dữ liệu động học cục bộ (góc nghiêng cột sống, vận tốc cổ tay, năng lượng luồng quang học Farneback và lịch sử chuyển động MHI).
4. **Kiểm soát Ngân sách Token (`TokenGuard`):** Nén khung hình JPEG kích thước chuẩn `512x288` và gộp các sự kiện bạo lực/té ngã liên tiếp thành các cụm tình huống (`Situational Clusters`), giới hạn mức tiêu thụ dưới **1.500 Tokens / video**.

---

## 5. Cấu Trúc Mã Nguồn Hệ Thống

```text
os-multithreaded-video-analytics/
├── core/
│   ├── __init__.py
│   ├── config.py                  # Cấu hình hệ thống, thăm dò CUDA nhanh & biến môi trường
│   ├── os_lab_engine.py           # Cài đặt ThreadSafeBoundedBuffer (Mutex + Condition Variables)
│   ├── web_server.py              # Máy chủ FastAPI, 4 luồng Live Camera & luồng so sánh song song Y || Z
│   ├── video_annotator.py         # Đường ống 3 giai đoạn xử lý video, ByteTrack, nội suy iGPU & FFmpeg H.264
│   ├── optical_motion_engine.py   # Động cơ Luồng quang học Gunnar Farneback & Motion History Image (MHI)
│   ├── enhancer.py                # Tiền xử lý thị giác thích ứng (CLAHE, Gamma, Dehaze)
│   ├── model_orchestrator.py      # Điều phối viên AI 3 tầng, xoay vòng đa khóa API & Cooldown FSM
│   ├── gemini_analyzer.py         # Giao tiếp Google GenAI SDK & phân tích ngữ nghĩa cảnh huống
│   ├── token_guard.py             # Bộ lọc trùng lặp khung hình & kiểm soát ngân sách Token
│   ├── cyber_hud.py               # Bộ kết xuất đồ họa lớp phủ вектор (Bounding Box, Skeleton 17 khớp)
│   ├── capture.py                 # Trình thu nhận khung hình luồng độc lập
│   ├── detector.py                # Mô-đun suy luận hành vi cơ sở
│   ├── event_logger.py            # Ghi nhận nhật ký sự kiện bất thường có đồng bộ khóa
│   └── metrics.py                 # Thu thập thông số tài nguyên hệ thống (CPU, RAM, VRAM, FPS)
├── ui/
│   ├── templates/
│   │   └── index.html             # Giao diện điều hành Web hợp nhất (Bố cục thích ứng Sáng/Tối)
│   └── static/
│       ├── style.css              # Hệ thống kiểu dáng chuẩn công nghiệp, hỗ trợ Dark/Light Mode
│       └── app.js                 # Điều khiển thời gian thực, biểu đồ Telemetry, Timeline Trimmer & Lab Y||Z
├── main.py                        # Điểm khởi chạy trung tâm, Readiness Probe & tự động giải phóng cổng
├── requirements.txt               # Danh sách thư viện phụ thuộc của hệ thống
├── .env.example                   # Tệp mẫu cấu hình khóa API và tham số mô hình
├── run_web.bat                    # Kịch bản khởi chạy nhanh Giao diện Web trên Windows
├── run_camera.bat                 # Kịch bản khởi chạy nhanh chế độ Camera trực tiếp trên Windows
├── run_on_colab.ipynb             # Sổ tay triển khai hệ thống trên hạ tầng GPU Google Colab
└── LICENSE                        # Giấy phép mã nguồn mở MIT
```

---

## 6. Yêu Cầu Hệ Thống & Hướng Dẫn Cài Đặt

### 6.1. Yêu Cầu Phần Mềm & Phần Cứng
* **Hệ điều hành:** Windows 10/11 (64-bit), Linux (Ubuntu 20.04+), hoặc macOS.
* **Trình thông dịch:** Python `3.10` trở lên.
* **Phần cứng hỗ trợ:**
  * *Cấu hình Khuyến nghị:* GPU rời NVIDIA hỗ trợ CUDA (RTX 20-series / 30-series / 40-series / 50-series) để kích hoạt suy luận `FP16` và bộ mã hóa phần cứng `h264_nvenc`.
  * *Cấu hình Tiêu chuẩn:* Máy tính xách tay sử dụng bộ vi xử lý đa nhân kèm đồ họa tích hợp (`Intel UHD / Iris Xe` hoặc `AMD Radeon Graphics`) — hệ thống sẽ tự động kích hoạt chế độ nội suy động học và mã hóa phần cứng `h264_qsv` / `h264_amf`.

### 6.2. Các Bước Cài Đặt Chi Tiết

**Bước 1: Sao chép kho mã nguồn và khởi tạo môi trường ảo**
```bash
git clone https://github.com/dinhhuy22062006/os-multithreaded-video-analytics.git
cd os-multithreaded-video-analytics

# Khởi tạo môi trường ảo Python
python -m venv .venv

# Kích hoạt môi trường ảo (trên Windows PowerShell)
.\.venv\Scripts\Activate.ps1
# Hoặc trên Windows CMD: .\.venv\Scripts\activate.bat
# Hoặc trên Linux/macOS: source .venv/bin/activate
```

**Bước 2: Cài đặt PyTorch phù hợp với phần cứng máy tính**
* *Trường hợp 1 — Máy tính có card đồ họa rời NVIDIA (Khuyến nghị):*
  ```bash
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
  ```
* *Trường hợp 2 — Máy tính chỉ có card đồ họa tích hợp (Intel / AMD iGPU) hoặc CPU:*
  ```bash
  pip install torch torchvision
  ```

**Bước 3: Cài đặt các thư viện phụ thuộc của hệ thống**
```bash
pip install -r requirements.txt
```

**Bước 4: Cấu hình biến môi trường (`.env`)**
Sao chép tệp `.env.example` thành `.env` tại thư mục gốc của dự án:
```bash
copy .env.example .env   # Trên Windows
# cp .env.example .env   # Trên Linux/macOS
```
Mở tệp `.env` và điền khóa API Google Gemini (lấy miễn phí tại [Google AI Studio](https://aistudio.google.com/app/apikey)). Hệ thống hỗ trợ khai báo một hoặc nhiều khóa API phân tách bằng dấu phẩy để xoay vòng tự động:
```env
GEMINI_API_KEYS=AIzaSyYourFirstKeyHere,AIzaSyYourSecondKeyHere
```
*(Lưu ý: Nếu không cấu hình khóa API, hệ thống vẫn hoạt động đầy đủ ở chế độ tự hành nội bộ thông qua Mô hình 3 — Phân tích Động học Khung xương & Luồng Quang học Cục bộ).*

---

## 7. Hướng Dẫn Vận Hành

### Cách 1: Khởi chạy trực tiếp qua Giao diện Dòng lệnh (Khuyên dùng)
```bash
python main.py
```
* Ngay khi khởi chạy, hệ thống sẽ tự động kiểm tra và giải phóng cổng `8000` nếu có tiến trình cũ còn tồn đọng, khởi tạo máy chủ FastAPI, thực hiện thăm dò trạng thái sẵn sàng (`Readiness Probe` tại `/health`) và tự động mở trình duyệt mặc định tới địa chỉ `http://127.0.0.1:8000`.
* Các tùy chọn dòng lệnh bổ sung:
  * `python main.py --port 8080`: Thay đổi cổng lắng nghe của máy chủ Web.
  * `python main.py --source 1`: Chỉ định chỉ số phần cứng Webcam ngoài (mặc định là `0`).
  * `python main.py --no-browser`: Khởi chạy máy chủ ngầm mà không tự động bật cửa sổ trình duyệt.

### Cách 2: Khởi chạy nhanh trên Windows bằng Tập tin Kịch bản (`.bat`)
* Sau khi đã hoàn tất **Bước 2** và **Bước 3** ở mục Cài đặt, người dùng trên Windows có thể nhấp đúp trực tiếp vào tệp **`run_web.bat`** (hoặc **`run_camera.bat`**) để khởi động toàn bộ hệ thống và mở giao diện điều hành trên trình duyệt.

### Cách 3: Triển khai trên Hạ tầng Đám mây Google Colab (GPU Tesla T4)
* Tải tệp `run_on_colab.ipynb` lên [Google Colab](https://colab.research.google.com/), chuyển đổi Runtime sang **T4 GPU**, và thực thi tuần tự các ô lệnh để khởi tạo đường hầm công khai kết nối trực tiếp tới giao diện điều hành của hệ thống.

---

## 8. Đặc Tả Giao Thức API Nội Bộ

| Phương thức | Đường dẫn Endpoint | Mô tả Chức năng Kỹ thuật |
| :--- | :--- | :--- |
| `GET` | `/health` | Kiểm tra trạng thái sẵn sàng của máy chủ (`Readiness Probe`) và thiết bị suy luận (`CUDA` / `CPU`). |
| `GET` | `/api/video_feed` | Luồng truyền phát hình ảnh thời gian thực `multipart/x-mixed-replace` ở tốc độ mục tiêu 30 FPS. |
| `GET` | `/api/telemetry` | Trả về thông số phần cứng thời gian thực (FPS, CPU, RAM, VRAM, trạng thái hàng đợi Bounded-Buffer và cấu hình 3 tầng AI). |
| `POST` | `/api/camera/toggle` | Khởi động hoặc dừng cụm 4 luồng giám sát Camera trực tiếp một cách an toàn (`Graceful Thread Termination`). |
| `POST` | `/api/video/upload` | Tải lên tệp video cục bộ, trích xuất siêu dữ liệu và trả về luồng xem trước cho thanh cắt đoạn Timeline. |
| `POST` | `/api/video/fetch_url` | Tải và chuẩn hóa luồng video từ URL trực tuyến thông qua `yt-dlp`. |
| `POST` | `/api/video/process` | Khởi chạy đường ống 3 giai đoạn phân tích video đơn luồng hoặc chế độ so sánh tài nguyên song song $Y \parallel Z$. |
| `GET` | `/api/video/status/{job_id}` | Truy vấn tiến độ xử lý, nhật ký cảnh báo theo mốc thời gian và số liệu đối chiếu hiệu năng Hệ điều hành. |

---

## Giấy Phép Bản Quyền

Dự án được phân phối dưới giấy phép **MIT License**. Xem chi tiết tại tệp [LICENSE](LICENSE).
