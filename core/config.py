"""
Global Configuration for Video Behavior Analytics & OS Multithreading System.
"""
import os

from dotenv import load_dotenv

# Đảm bảo biến môi trường từ .env luôn được nạp đầy đủ
load_dotenv()

# Cấu hình lưu trữ Cache Hugging Face sang ổ D nếu có để tiết kiệm dung lượng ổ C
if os.path.exists("D:/huggingface_cache") or (os.name == "nt" and os.path.exists("D:/")):
    HF_CACHE_DIR = "D:/huggingface_cache"
    os.environ["HF_HOME"] = HF_CACHE_DIR
    os.environ["TRANSFORMERS_CACHE"] = os.path.join(HF_CACHE_DIR, "hub")


from dataclasses import dataclass, field
from typing import List, Optional


def parse_gemini_api_keys(raw_keys: Optional[str] = None) -> List[str]:
    """
    Phân tích chuỗi API Keys phân tách bằng dấu phẩy thành danh sách khóa.
    Ưu tiên biến GEMINI_API_KEYS, tự động fallback về GEMINI_API_KEY đơn lẻ.
    """
    keys_str = raw_keys if raw_keys is not None else os.getenv("GEMINI_API_KEYS", "")
    if keys_str and keys_str.strip():
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if keys:
            return keys
    single_key = os.getenv("GEMINI_API_KEY", "").strip()
    return [single_key] if single_key else []


@dataclass
class SystemConfig:
    # --- Model Configuration ---
    MODEL_NAME: str = "microsoft/xclip-base-patch32-16-frames"
    FRAME_SAMPLE_COUNT: int = 16  # X-CLIP requires 16 frames per window
    CONFIDENCE_THRESHOLD: float = 0.60  # Minimum confidence (60%)
    
    # --- Action Labels (Zero-Shot) ---
    ACTION_LABELS: List[str] = field(default_factory=lambda: [
        "walking",
        "working on computer",
        "sitting still",
        "standing",
        "waving hands",
        "fighting or punching",
        "falling down",
        "running in a hurry"
    ])
    
    # Dangerous actions that trigger Danger Alert
    DANGER_LABELS: List[str] = field(default_factory=lambda: [
        "fighting or punching",
        "falling down"
    ])
    
    # --- Operating System & Queue Parameters ---
    FRAME_QUEUE_MAXSIZE: int = 32  # Bounded buffer to prevent memory bloat
    CAPTURE_FPS: int = 30           # Standard camera rate
    INFERENCE_INTERVAL_FRAMES: int = 8  # Step size for sliding window
    CAMERA_WIDTH: int = 640
    CAMERA_HEIGHT: int = 480
    _cached_device: Optional[str] = field(default=None, init=False, repr=False)

    @property
    def DEVICE(self) -> str:
        if self._cached_device is None:
            import torch
            self._cached_device = "cuda:0" if torch.cuda.is_available() else "cpu"
        return self._cached_device

    @DEVICE.setter
    def DEVICE(self, value: str):
        self._cached_device = value
    
    # --- Resource Monitoring ---
    METRICS_POLL_INTERVAL: float = 0.5  # Seconds between psutil readings

    # --- YOLOv8 Edge Detection & Pose Estimation ---
    YOLO_MODEL_NAME: str = "yolov8n-pose.pt"
    YOLO_CONFIDENCE: float = 0.45
    FALL_ANGLE_THRESHOLD: float = 38.0   # Góc nghiêng thân người dưới 38 độ = Té ngã / Gục xuống
    STRIKE_VELOCITY_THRESHOLD: float = 45.0 # Vận tốc vung tay nhanh bất thường = Bạo lực / Vung đấm

    # --- Cyber Surveillance Command Center HUD (1280x720 Widescreen) ---
    HUD_WIDTH: int = 1280
    HUD_HEIGHT: int = 720
    VIEWPORT_WIDTH: int = 900
    VIEWPORT_HEIGHT: int = 720
    SIDEBAR_WIDTH: int = 380

    # --- Cloud LLM Hierarchical Tiers & Rate Limiting (R1 Specification) ---
    GEMINI_TIER1_MODEL: str = field(default_factory=lambda: os.getenv("GEMINI_TIER1_MODEL", "gemini-2.0-flash"))
    GEMINI_TIER2_MODEL: str = field(default_factory=lambda: os.getenv("GEMINI_TIER2_MODEL", "gemini-1.5-flash"))
    GEMINI_COOLDOWN_SECONDS: float = field(default_factory=lambda: float(os.getenv("GEMINI_COOLDOWN_SECONDS", "60.0")))
    GEMINI_API_KEYS: List[str] = field(default_factory=parse_gemini_api_keys)
    GEMINI_API_KEY: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))

    # Tương thích ngược với mã nguồn cũ
    GEMINI_MODEL: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", os.getenv("GEMINI_TIER1_MODEL", "gemini-2.0-flash")))
    GEMINI_INTERVAL_SECONDS: float = field(default_factory=lambda: float(os.getenv("GEMINI_INTERVAL_SECONDS", "4.2")))
    API_PACE_SECONDS: float = 4.2  # Nhịp độ khống chế >= 4.2s giữa Live Camera và Video Upload (< 15 RPM)


# Global instance
CONFIG = SystemConfig()

