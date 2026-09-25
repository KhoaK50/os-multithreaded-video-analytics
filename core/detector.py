"""
X-CLIP Zero-Shot Video Action Recognition Engine.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Mô hình sử dụng: microsoft/xclip-base-patch32-16-frames
Tối ưu hóa:
- Tự động nhận diện GPU NVIDIA RTX và nạp lên CUDA
- Hỗ trợ nửa độ chính xác (FP16) để tăng gấp đôi tốc độ và giảm 50% VRAM
- Xử lý 16 frame trượt (sliding window) theo chuẩn kiến trúc X-CLIP
"""

import logging
import os
import ssl
import time
from typing import List, Dict, Any, Optional
import numpy as np
from PIL import Image
import torch
from transformers import AutoProcessor, AutoModel

# Bỏ qua SSL verification nếu mạng bị proxy/antivirus can thiệp
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

from core.config import CONFIG

logger = logging.getLogger(__name__)


class XCLIPDetector:
    """Bộ nhận diện hành vi video zero-shot sử dụng mô hình X-CLIP."""

    def __init__(
        self,
        model_name: str = CONFIG.MODEL_NAME,
        candidate_labels: Optional[List[str]] = None,
        danger_labels: Optional[List[str]] = None,
        confidence_threshold: float = CONFIG.CONFIDENCE_THRESHOLD,
        device: Optional[str] = None
    ):
        self.model_name = model_name
        self.candidate_labels = candidate_labels if candidate_labels is not None else CONFIG.ACTION_LABELS
        self.danger_labels = set(danger_labels if danger_labels is not None else CONFIG.DANGER_LABELS)
        self.confidence_threshold = confidence_threshold

        # Tự động chọn thiết bị tối ưu
        if device is None:
            self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Sử dụng FP16 nếu chạy trên GPU NVIDIA RTX
        self.dtype = torch.float16 if self.device.type == "cuda" else torch.float32

        logger.info(f"Khởi tạo XCLIPDetector trên thiết bị: {self.device} ({self.dtype})")
        self._load_model()

    def _load_model(self):
        """Nạp weights mô hình và tokenizer processor."""
        t0 = time.time()
        logger.info(f"Đang nạp processor và model từ: {self.model_name}...")
        try:
            self.processor = AutoProcessor.from_pretrained(self.model_name, local_files_only=True)
            self.model = AutoModel.from_pretrained(self.model_name, dtype=self.dtype, local_files_only=True)
        except Exception:
            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name, dtype=self.dtype)

        self.model.to(self.device)
        self.model.eval()
        logger.info(f"Nạp X-CLIP thành công trong {time.time() - t0:.2f}s!")

    def predict(
        self,
        frames: List[Any],
        custom_labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Dự đoán hành vi từ 16 khung hình liên tiếp.
        Args:
            frames: Danh sách 16 ảnh (PIL Image hoặc np.ndarray dạng RGB)
            custom_labels: Tùy biến danh sách nhãn hành vi nếu cần
        """
        if len(frames) != CONFIG.FRAME_SAMPLE_COUNT:
            raise ValueError(
                f"X-CLIP yêu cầu chính xác {CONFIG.FRAME_SAMPLE_COUNT} khung hình, nhưng nhận được {len(frames)}."
            )

        labels = custom_labels if custom_labels is not None else self.candidate_labels

        # Đảm bảo frames là dạng PIL Image RGB
        pil_frames = []
        for f in frames:
            if isinstance(f, np.ndarray):
                pil_frames.append(Image.fromarray(f))
            elif isinstance(f, Image.Image):
                pil_frames.append(f)
            else:
                raise TypeError(f"Kiểu dữ liệu frame không hợp lệ: {type(f)}")

        t0 = time.time()

        # Tiền xử lý dữ liệu
        inputs = self.processor(
            text=labels,
            videos=[pil_frames],
            return_tensors="pt",
            padding=True
        )

        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        if self.device.type == "cuda":
            inputs["pixel_values"] = inputs["pixel_values"].to(self.dtype)

        # Suy luận zero-shot
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits_per_video = outputs.logits_per_video  # shape: (1, num_labels)
            probabilities = logits_per_video.softmax(dim=1).cpu().numpy()[0]

        inference_time_ms = (time.time() - t0) * 1000.0

        # Ghép nhãn và xác suất
        scores = {labels[i]: float(probabilities[i]) for i in range(len(labels))}
        best_idx = int(np.argmax(probabilities))
        best_label = labels[best_idx]
        best_score = float(probabilities[best_idx])

        # Đánh giá ngưỡng tin cậy
        if best_score < self.confidence_threshold:
            display_label = "Chưa rõ hành vi"
            is_confident = False
        else:
            display_label = best_label
            is_confident = True

        # Đánh giá mức độ nguy hiểm
        is_danger = is_confident and (best_label in self.danger_labels)

        return {
            "label": display_label,
            "raw_label": best_label,
            "confidence": best_score,
            "is_confident": is_confident,
            "is_danger": is_danger,
            "all_scores": scores,
            "inference_time_ms": round(inference_time_ms, 1),
            "device": str(self.device),
        }
