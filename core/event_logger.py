"""
Event Logging & Dangerous Incident Alert Engine.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Chức năng:
- Lưu vết toàn bộ sự kiện nhận diện theo thời gian (Event Timeline Log)
- Thống kê tần suất và tỷ lệ phần trăm các hành vi (Biểu đồ %)
- Lưu trữ bộ đệm trượt 3-5 giây khung hình (Rolling Clip Buffer)
- Khi phát hiện hành vi nguy hiểm: Tự động trích xuất clip ngắn (.mp4) và kích hoạt cảnh báo đỏ
"""

import collections
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoEvent:
    id: int
    timestamp: float
    formatted_time: str
    action: str
    confidence: float
    is_danger: bool
    clip_path: Optional[str] = None
    gemini_summary: Optional[str] = None


class EventLogger:
    """Quản lý nhật ký sự kiện, trích xuất clip nguy hiểm và tổng hợp thống kê."""

    def __init__(
        self,
        output_dir: str = "recordings",
        clip_buffer_seconds: int = 4,
        fps: int = 30
    ):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.clip_buffer_seconds = clip_buffer_seconds
        self.fps = fps
        self.max_buffer_frames = clip_buffer_seconds * fps

        # Buffer lưu các frame gần nhất để trích xuất video khi có nguy hiểm
        self._rolling_frames = collections.deque(maxlen=self.max_buffer_frames)
        self._lock = threading.Lock()

        # Danh sách sự kiện đã ghi nhận
        self.events: List[VideoEvent] = []
        self.event_counter = 0

        # Thống kê số lần xuất hiện của từng hành vi
        self.action_counts: Dict[str, int] = collections.defaultdict(int)

        # Chống spam ghi clip liên tục khi hành vi nguy hiểm kéo dài nhiều frame
        self._last_clip_time = 0.0
        self.clip_cooldown_seconds = 5.0

    def add_frame_to_buffer(self, frame: np.ndarray):
        """Lưu frame vào rolling buffer để sẵn sàng trích xuất clip khi cần."""
        with self._lock:
            self._rolling_frames.append(frame.copy())

    def log_inference(
        self,
        action: str,
        confidence: float,
        is_danger: bool
    ) -> VideoEvent:
        """Ghi nhận một kết quả suy luận vào hệ thống nhật ký."""
        now = time.time()
        formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

        self.event_counter += 1
        clip_path = None

        # Cập nhật số liệu thống kê
        self.action_counts[action] += 1

        # Nếu phát hiện hành vi nguy hiểm và hết thời gian giãn cách (cooldown)
        if is_danger and (now - self._last_clip_time >= self.clip_cooldown_seconds):
            clip_path = self._save_danger_clip(now)
            self._last_clip_time = now

        event = VideoEvent(
            id=self.event_counter,
            timestamp=now,
            formatted_time=formatted_time,
            action=action,
            confidence=round(confidence, 3),
            is_danger=is_danger,
            clip_path=clip_path
        )

        with self._lock:
            self.events.append(event)

        logger.info(f"Đã ghi nhận sự kiện [{formatted_time}]: {action} ({confidence*100:.1f}%) | Nguy hiểm: {is_danger}")
        return event

    def _save_danger_clip(self, timestamp: float) -> Optional[str]:
        """Trích xuất các khung hình trong rolling buffer thành file video .mp4."""
        with self._lock:
            frames_to_save = list(self._rolling_frames)

        if not frames_to_save:
            return None

        filename = f"danger_{int(timestamp)}.mp4"
        filepath = os.path.join(self.output_dir, filename)

        height, width = frames_to_save[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(filepath, fourcc, self.fps, (width, height))

        for f in frames_to_save:
            out.write(f)
        out.release()

        logger.warning(f"[CẢNH BÁO NGUY HIỂM] Đã trích xuất đoạn clip 3-5s tại: {filepath}")
        return filepath

    def get_statistics(self) -> Dict[str, Any]:
        """Tổng hợp tỷ lệ % các hành vi và số lượng sự kiện."""
        total_events = sum(self.action_counts.values())
        if total_events == 0:
            return {"total_events": 0, "percentages": {}, "counts": {}}

        percentages = {
            act: round((count / total_events) * 100, 1)
            for act, count in self.action_counts.items()
        }

        return {
            "total_events": total_events,
            "percentages": percentages,
            "counts": dict(self.action_counts),
            "danger_count": sum(1 for e in self.events if e.is_danger)
        }

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lấy danh sách các sự kiện mới nhất phục vụ hiển thị Timeline."""
        with self._lock:
            return [asdict(e) for e in reversed(self.events[-limit:])]
