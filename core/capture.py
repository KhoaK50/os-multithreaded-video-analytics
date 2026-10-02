"""
Multi-threaded Camera Capture Producer with Thread-Safe Bounded Buffer & Drop-frame Flow Control.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng Thời Gian Thực.

Nguyên lý HĐH áp dụng:
1. Producer - Consumer Pattern:
   - Luồng Producer đọc frame từ Camera ở tốc độ 30 FPS.
   - Luồng Consumer (YOLOv8 Edge AI / Web Server) lấy frame từ Bounded Buffer để suy luận.
2. Thread-Safe Bounded Buffer với Mutex Lock & Condition Variables:
   - Sử dụng threading.Lock bảo vệ miền găng (Critical Section).
   - Biến điều kiện not_empty đánh thức Consumer khi có frame mới.
   - Biến điều kiện not_full đánh thức Producer khi có vị trí trống.
3. Flow Control / Drop-Oldest Mechanism:
   - Khi hàng đợi Bounded Buffer chạm ngưỡng tối đa (N frames), Producer tự động loại bỏ frame cũ nhất (FIFO eviction).
   - Ngăn chặn triệt để hiện tượng tràn bộ đệm (Buffer Bloat) và đảm bảo độ trễ thời gian thực (Zero Latency).
4. Telemetry Tracking:
   - Theo dõi dung lượng thực tế, số khung hình rơi (dropped frames), tỷ lệ drop rate %,
     độ trễ hàng đợi (Queue Latency ms), và mức tải đỉnh (High-Water Mark).
"""

import logging
import queue
import collections
import threading
import time
from typing import Optional, Tuple, Any, List
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ThreadSafeBoundedBuffer:
    """
    Hàng đợi đệm có giới hạn an toàn đa luồng (Thread-Safe Bounded Buffer).
    Áp dụng nguyên ngữ đồng bộ hóa Hệ Điều Hành:
    - Mutex Lock cho miền găng.
    - Condition Variables: not_empty, not_full.
    - Cơ chế Flow Control: Drop-Oldest khi đầy.
    - Viễn trắc hàng đợi: Queue Latency, High-Water Mark, Drop Rate %.
    """

    def __init__(self, capacity: int = 16):
        self.capacity = max(1, capacity)
        self._buffer = collections.deque()
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock)
        self.not_full = threading.Condition(self.lock)

        # Viễn trắc Hệ điều hành
        self.total_produced = 0
        self.total_consumed = 0
        self.total_dropped = 0
        self.high_water_mark = 0
        self.latency_samples = collections.deque(maxlen=60)

    def put_drop_oldest(self, item: Any) -> bool:
        """
        Nạp phần tử vào hàng đợi đệm theo cơ chế Drop-Oldest Flow Control.
        Nếu hàng đợi đầy, loại bỏ phần tử cũ nhất (FIFO eviction) để nhường chỗ cho phần tử mới nhất.
        Đảm bảo không bao giờ chặn luồng Producer (Non-blocking Producer).
        """
        with self.lock:
            dropped = False
            if len(self._buffer) >= self.capacity:
                self._buffer.popleft()
                self.total_dropped += 1
                dropped = True

            self._buffer.append(item)
            self.total_produced += 1
            if len(self._buffer) > self.high_water_mark:
                self.high_water_mark = len(self._buffer)

            # Báo hiệu cho các Consumer đang chờ dữ liệu
            self.not_empty.notify()
            return dropped

    def put(self, item: Any, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Nạp phần tử có cơ chế chặn (Blocking Put) khi buffer đầy theo chuẩn Dijkstra.
        """
        with self.lock:
            if not block:
                if len(self._buffer) >= self.capacity:
                    raise queue.Full("Bounded buffer is full")
            else:
                end_time = time.time() + timeout if timeout is not None else None
                while len(self._buffer) >= self.capacity:
                    if timeout is not None:
                        remaining = end_time - time.time()
                        if remaining <= 0:
                            raise queue.Full("Bounded buffer put timeout")
                        self.not_full.wait(remaining)
                    else:
                        self.not_full.wait()

            self._buffer.append(item)
            self.total_produced += 1
            if len(self._buffer) > self.high_water_mark:
                self.high_water_mark = len(self._buffer)

            self.not_empty.notify()
            return True

    def put_nowait(self, item: Any) -> None:
        """Nạp phần tử không chặn (Non-blocking Put), ném queue.Full nếu hàng đợi đầy."""
        self.put(item, block=False)

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Any]:
        """
        Lấy phần tử ra khỏi hàng đợi đệm (Consumer Operation).
        Hỗ trợ chặn có thời hạn (Blocking Get with timeout) qua Condition Variable.
        Tự động đo Queue Latency nếu phần tử là tuple dạng (timestamp, data).
        """
        with self.lock:
            if not block:
                if len(self._buffer) == 0:
                    return None
            else:
                end_time = time.time() + timeout if timeout is not None else None
                while len(self._buffer) == 0:
                    if timeout is not None:
                        remaining = end_time - time.time()
                        if remaining <= 0:
                            return None
                        self.not_empty.wait(remaining)
                    else:
                        self.not_empty.wait()

            item = self._buffer.popleft()
            self.total_consumed += 1

            # Đo độ trễ thời gian thực của frame trong hàng đợi
            if isinstance(item, tuple) and len(item) >= 1 and isinstance(item[0], (int, float)):
                t_put = item[0]
                latency_ms = (time.time() - t_put) * 1000.0
                if latency_ms >= 0:
                    self.latency_samples.append(latency_ms)

            # Đánh thức Producer nếu đang bị chặn
            self.not_full.notify()
            return item

    def get_nowait(self) -> Any:
        """Lấy phần tử không chặn (Non-blocking Get), ném queue.Empty nếu rỗng."""
        item = self.get(block=False)
        if item is None:
            raise queue.Empty("Bounded buffer is empty")
        return item

    def peek_latest(self) -> Optional[Any]:
        """Xem phần tử mới nhất trong hàng đợi mà không lấy ra."""
        with self.lock:
            if len(self._buffer) > 0:
                return self._buffer[-1]
            return None

    def qsize(self) -> int:
        """Trả về kích thước hiện tại của hàng đợi đệm."""
        with self.lock:
            return len(self._buffer)

    def full(self) -> bool:
        """Kiểm tra hàng đợi đã đầy dung lượng chưa."""
        with self.lock:
            return len(self._buffer) >= self.capacity

    def empty(self) -> bool:
        """Kiểm tra hàng đợi có rỗng không."""
        with self.lock:
            return len(self._buffer) == 0

    def clear(self):
        """Xóa sạch hàng đợi và giải phóng các luồng đang chờ."""
        with self.lock:
            self._buffer.clear()
            self.not_full.notify_all()

    def get_stats(self) -> dict:
        """
        Trả về bức tranh viễn trắc toàn diện của Bounded Buffer phục vụ báo cáo HĐH.
        """
        with self.lock:
            cur_size = len(self._buffer)
            avg_lat = round(float(np.mean(self.latency_samples)), 2) if self.latency_samples else 0.0
            drop_rate = round((self.total_dropped / max(1, self.total_produced)) * 100.0, 2)
            utilization = round((cur_size / max(1, self.capacity)) * 100.0, 1)

            return {
                "size": cur_size,
                "capacity": self.capacity,
                "total_produced": self.total_produced,
                "total_consumed": self.total_consumed,
                "total_dropped": self.total_dropped,
                "drop_rate_pct": drop_rate,
                "latency_ms": avg_lat,
                "high_water_mark": self.high_water_mark,
                "utilization_pct": utilization,
            }


class VideoCaptureProducer(threading.Thread):
    """
    Luồng Producer đọc video từ Webcam hoặc File và nạp vào ThreadSafeBoundedBuffer.
    Tích hợp cơ chế Drop-frame của Hệ điều hành.
    """

    def __init__(
        self,
        video_source: int | str = 0,
        frame_queue: Optional[Any] = None,
        max_queue_size: int = 32,
        target_fps: int = 30,
        width: int = 640,
        height: int = 480
    ):
        super().__init__(name="VideoCaptureProducerThread", daemon=True)
        self.video_source = video_source

        # Nếu truyền vào queue.Queue hoặc ThreadSafeBoundedBuffer thì tái sử dụng, ngược lại khởi tạo mới
        if frame_queue is not None:
            self.frame_queue = frame_queue
            self.bounded_buffer = frame_queue if isinstance(frame_queue, ThreadSafeBoundedBuffer) else None
        else:
            self.bounded_buffer = ThreadSafeBoundedBuffer(capacity=max_queue_size)
            self.frame_queue = self.bounded_buffer

        self.max_queue_size = max_queue_size
        self.target_fps = target_fps
        self.frame_delay = 1.0 / target_fps if target_fps > 0 else 0.0
        self.width = width
        self.height = height

        # Trạng thái điều khiển luồng
        self._stop_event = threading.Event()
        self._is_running = False

        # Thống kê hiệu năng HĐH
        self.total_frames_read = 0
        self.total_frames_dropped = 0
        self.actual_fps = 0.0
        self._last_fps_calc_time = time.time()
        self._fps_frame_counter = 0

    def run(self):
        """Vòng lặp chính của Luồng Producer."""
        logger.info(f"Khởi động Producer đọc từ nguồn: {self.video_source}")
        cap = cv2.VideoCapture(self.video_source)

        if not cap.isOpened():
            logger.error(f"Không thể mở nguồn video: {self.video_source}")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        self._is_running = True
        self._last_fps_calc_time = time.time()

        try:
            while not self._stop_event.is_set():
                loop_start = time.time()

                ret, frame = cap.read()
                if not ret:
                    logger.warning("Không đọc được frame hoặc video đã kết thúc.")
                    break

                self.total_frames_read += 1
                self._fps_frame_counter += 1

                # Lật gương nếu là webcam trực tiếp
                if isinstance(self.video_source, int):
                    frame = cv2.flip(frame, 1)

                timestamp = time.time()
                frame_package = (timestamp, frame)

                # --- [CƠ CHẾ HỆ ĐIỀU HÀNH: DROP-FRAME CHỐNG TRÀN BUFFER] ---
                if self.bounded_buffer is not None:
                    was_dropped = self.bounded_buffer.put_drop_oldest(frame_package)
                    if was_dropped:
                        self.total_frames_dropped += 1
                else:
                    # Fallback cho queue.Queue chuẩn
                    if hasattr(self.frame_queue, "full") and self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                            self.total_frames_dropped += 1
                        except Exception:
                            pass
                    try:
                        self.frame_queue.put_nowait(frame_package)
                    except Exception:
                        self.total_frames_dropped += 1

                # Tính toán FPS thực tế của camera
                now = time.time()
                elapsed = now - self._last_fps_calc_time
                if elapsed >= 1.0:
                    self.actual_fps = self._fps_frame_counter / elapsed
                    self._fps_frame_counter = 0
                    self._last_fps_calc_time = now

                # Điều tiết tốc độ khung hình (nếu đọc từ file video)
                processing_time = time.time() - loop_start
                sleep_time = self.frame_delay - processing_time
                if sleep_time > 0 and not isinstance(self.video_source, int):
                    time.sleep(sleep_time)

        finally:
            cap.release()
            self._is_running = False
            logger.info("Đã đóng luồng VideoCaptureProducer an toàn.")

    def stop(self):
        """Dừng luồng Producer an toàn."""
        self._stop_event.set()
        self._is_running = False

    def get_latest_frame(self) -> Optional[Tuple[float, np.ndarray]]:
        """Lấy frame mới nhất từ queue (non-blocking)."""
        if self.bounded_buffer is not None:
            return self.bounded_buffer.get_nowait()
        try:
            return self.frame_queue.get_nowait()
        except Exception:
            return None

    def get_stats(self) -> dict:
        """Trả về số liệu thống kê luồng phục vụ báo cáo HĐH."""
        if self.bounded_buffer is not None:
            buf_stats = self.bounded_buffer.get_stats()
            return {
                "is_running": self._is_running,
                "queue_size": buf_stats["size"],
                "max_queue_size": buf_stats["capacity"],
                "total_read": self.total_frames_read,
                "total_dropped": buf_stats["total_dropped"],
                "fps": round(self.actual_fps, 1),
                "drop_rate_pct": buf_stats["drop_rate_pct"],
                "latency_ms": buf_stats["latency_ms"],
                "high_water_mark": buf_stats["high_water_mark"]
            }

        qsize = self.frame_queue.qsize() if hasattr(self.frame_queue, "qsize") else 0
        return {
            "is_running": self._is_running,
            "queue_size": qsize,
            "max_queue_size": self.max_queue_size,
            "total_read": self.total_frames_read,
            "total_dropped": self.total_frames_dropped,
            "fps": round(self.actual_fps, 1),
            "drop_rate_pct": round(
                (self.total_frames_dropped / max(1, self.total_frames_read)) * 100, 2
            ),
        }
