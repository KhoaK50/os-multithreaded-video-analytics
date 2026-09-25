"""
Multi-threaded Camera Capture Producer with Drop-frame Flow Control.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Nguyên lý HĐH áp dụng:
1. Producer - Consumer Pattern: Luồng Producer liên tục đọc frame từ Camera ở tốc độ 30 FPS.
2. Flow Control / Drop-frame Mechanism: Khi hàng đợi FrameQueue bị đầy (do AI Consumer xử lý không kịp),
   Producer chủ động drop (loại bỏ) frame cũ nhất để nạp frame mới nhất.
   Điều này ngăn chặn hiện tượng tràn bộ đệm (Buffer Bloat) và đảm bảo độ trễ thời gian thực (Zero Latency).
"""

import logging
import queue
import threading
import time
from typing import Optional, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class VideoCaptureProducer(threading.Thread):
    """
    Luồng Producer đọc video từ Webcam hoặc File và nạp vào hàng đợi an toàn đa luồng (thread-safe Queue).
    Tích hợp cơ chế Drop-frame của Hệ điều hành.
    """

    def __init__(
        self,
        video_source: int | str = 0,
        frame_queue: Optional[queue.Queue] = None,
        max_queue_size: int = 32,
        target_fps: int = 30,
        width: int = 640,
        height: int = 480
    ):
        super().__init__(name="VideoCaptureProducerThread", daemon=True)
        self.video_source = video_source
        self.frame_queue = frame_queue if frame_queue is not None else queue.Queue(maxsize=max_queue_size)
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
                # Nếu queue đã đầy, loại bỏ 1 frame cũ nhất để nhường chỗ cho frame mới
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                        self.total_frames_dropped += 1
                    except queue.Empty:
                        pass

                try:
                    self.frame_queue.put_nowait(frame_package)
                except queue.Full:
                    # Trường hợp luồng khác tranh chấp đẩy vào cùng lúc
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
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None

    def get_stats(self) -> dict:
        """Trả về số liệu thống kê luồng phục vụ báo cáo HĐH."""
        return {
            "is_running": self._is_running,
            "queue_size": self.frame_queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "total_read": self.total_frames_read,
            "total_dropped": self.total_frames_dropped,
            "fps": round(self.actual_fps, 1),
            "drop_rate_pct": round(
                (self.total_frames_dropped / max(1, self.total_frames_read)) * 100, 2
            ),
        }
