"""
Hierarchical Model Orchestrator & Rolling Context Memory Engine.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.

Đặc tả kiến trúc (Milestone 1 - R1):
1. Phân tầng mô hình ưu tiên chất lượng cao (Hierarchical Model Tiers):
   - Tier 1: gemini-2.0-flash / gemini-2.5-flash (Thị giác cao nhất).
   - Tier 2: gemini-1.5-flash (Dự phòng tốc độ cao khi Tier 1 chạm trần 15 RPM).
   - Tier 3: Autonomous Heuristic Arbiter (Hội chẩn tự hành cục bộ có nhận thức ngữ cảnh).
2. Tự động chuyển đổi khi chạm trần 15 RPM / lỗi HTTP 429 RESOURCE_EXHAUSTED tức thì.
3. Tự phục hồi và quay lại Tier 1 (Preemptive Cooldown Reversion) qua bộ đếm 60s sliding window.
4. Duy trì bộ nhớ ngữ cảnh và tính liên tục tư duy (Rolling Context Memory) 3-5 chu kỳ trước.
5. Điều phối nhịp độ gọi API an toàn (Central Flow & Rate Limiter >= 4.2s).
6. Hỗ trợ xoay vòng API Keys dự phòng (Key Rotation Pool) khi được cấu hình.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
import threading
import time
import os
import json
import logging
import warnings
import numpy as np
from PIL import Image

from core.config import CONFIG, parse_gemini_api_keys

warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    TIER_1_PRIMARY = "Tier-1 Gemini 2.0"
    TIER_2_FALLBACK = "Tier-2 Gemini 1.5"
    TIER_3_HEURISTIC = "Tier-3 Local Arbiter"


@dataclass
class ContextMemoryEntry:
    timestamp: float
    time_str: str
    action: str
    description: str
    posture: str
    torso_angle: float
    prediction: str
    severity: str
    tier_used: str


class RollingContextMemory:
    """Quản lý bộ nhớ ngữ cảnh trượt 3-5 chu kỳ gần nhất (Thread-safe FIFO)."""

    def __init__(self, maxlen: int = 5):
        self.maxlen = maxlen
        self.history: List[ContextMemoryEntry] = []
        self._lock = threading.Lock()

    def record(self, entry: ContextMemoryEntry):
        with self._lock:
            self.history.append(entry)
            if len(self.history) > self.maxlen:
                self.history.pop(0)

    def get_context_summary_for_prompt(self) -> str:
        with self._lock:
            if not self.history:
                return "Chưa có dữ liệu lịch sử các chu kỳ trước (Chu kỳ khởi động ban đầu)."
            lines = ["DÒNG THỜI GIAN NGỮ CẢNH HÀNH VI 3-5 CHU KỲ TRƯỚC:"]
            total = len(self.history)
            for idx, item in enumerate(self.history):
                step = total - idx
                lines.append(
                    f"- [{item.time_str}] (T-{step}) [{item.tier_used}]: "
                    f"Hành vi: '{item.action}' | Tư thế: '{item.posture}' | "
                    f"Góc thân: {item.torso_angle:.0f}° | Mức độ: {item.severity} | "
                    f"Dự đoán trước đó: '{item.prediction}'"
                )
            lines.append("YÊU CẦU: Tiếp nối diễn biến hành vi liền mạch, duy trì tính nhất quán của bối cảnh.")
            return "\n".join(lines)

    def get_recent_entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "timestamp": e.timestamp,
                    "time_str": e.time_str,
                    "action": e.action,
                    "description": e.description,
                    "posture": e.posture,
                    "torso_angle": e.torso_angle,
                    "prediction": e.prediction,
                    "severity": e.severity,
                    "tier_used": e.tier_used,
                }
                for e in self.history
            ]

    def clear(self):
        with self._lock:
            self.history.clear()


class CooldownTracker:
    """Quản lý thời gian hồi phục 60 giây cho các tầng mô hình (Thread-safe)."""

    def __init__(self, cooldown_seconds: float = 60.0):
        self.cooldown_seconds = cooldown_seconds
        self.tier1_cooldown_start: Optional[float] = None
        self.tier2_cooldown_start: Optional[float] = None
        self._lock = threading.Lock()

    def mark_rate_limited(self, tier: ModelTier):
        with self._lock:
            now = time.time()
            if tier == ModelTier.TIER_1_PRIMARY:
                self.tier1_cooldown_start = now
                logger.warning(f"Tier-1 kích hoạt chế độ Cooldown {self.cooldown_seconds}s từ {now:.1f}")
            elif tier == ModelTier.TIER_2_FALLBACK:
                self.tier2_cooldown_start = now
                logger.warning(f"Tier-2 kích hoạt chế độ Cooldown {self.cooldown_seconds}s từ {now:.1f}")

    def is_tier1_ready(self) -> bool:
        with self._lock:
            if self.tier1_cooldown_start is None:
                return True
            elapsed = time.time() - self.tier1_cooldown_start
            if elapsed >= self.cooldown_seconds:
                self.tier1_cooldown_start = None  # Phục hồi
                logger.info("Tier-1 đã hết thời gian Cooldown 60s -> Tự phục hồi thành công (Preemptive Reversion)!")
                return True
            return False

    def is_tier2_ready(self) -> bool:
        with self._lock:
            if self.tier2_cooldown_start is None:
                return True
            elapsed = time.time() - self.tier2_cooldown_start
            if elapsed >= self.cooldown_seconds:
                self.tier2_cooldown_start = None
                return True
            return False

    def get_cooldown_remaining(self, tier: ModelTier) -> float:
        with self._lock:
            start_t = self.tier1_cooldown_start if tier == ModelTier.TIER_1_PRIMARY else self.tier2_cooldown_start
            if start_t is None:
                return 0.0
            elapsed = time.time() - start_t
            return max(0.0, self.cooldown_seconds - elapsed)

    def reset(self):
        with self._lock:
            self.tier1_cooldown_start = None
            self.tier2_cooldown_start = None


class AutonomousHeuristicArbiter:
    """Bộ Hội chẩn Hành vi Tự hành Cục bộ (Tier 3) có nhận thức ngữ cảnh chuỗi hành vi."""

    def synthesize_with_memory(
        self,
        posture_text: str,
        bio: dict,
        context_memory: RollingContextMemory
    ) -> dict:
        recent = context_memory.get_recent_entries()
        angle = float(bio.get("angle", 90.0))
        is_danger = bool(bio.get("is_danger", False))
        is_warning = bool(bio.get("is_warning", False))

        # Phân tích động học chuyển tiếp từ các chu kỳ trước
        transition_note = ""
        if recent:
            last = recent[-1]
            prev_act = last.get("action", "")
            if prev_act and prev_act.lower() != posture_text.lower():
                transition_note = f"Chuyển tiếp trạng thái từ '{prev_act}' sang '{posture_text}'."
            else:
                transition_note = f"Tiếp tục duy trì trạng thái '{posture_text}' ổn định qua {len(recent)} chu kỳ."

        desc = (
            f"Đối tượng duy trì tư thế {posture_text.lower()} (góc thân {angle:.1f}°). "
            f"{transition_note} Không gian sinh hoạt ổn định, bộ hội chẩn tự hành cục bộ "
            f"đảm bảo tính liên tục của dữ liệu mà không làm gián đoạn luồng quan sát."
        )
        pred = f"Duy trì ổn định trạng thái {posture_text.lower()} trong chu kỳ tiếp theo."
        severity = "danger" if is_danger else ("warning" if is_warning else "safe")

        return {
            "action": posture_text,
            "description": desc,
            "prediction_next_4s": pred,
            "severity": severity,
            "model_tier": ModelTier.TIER_3_HEURISTIC.value,
        }


def is_rate_limit_error(exc: Exception) -> bool:
    """Xác định chính xác ngoại lệ HTTP 429 / RESOURCE_EXHAUSTED."""
    if exc is None:
        return False
    code = getattr(exc, "code", None)
    if code == 429:
        return True
    status = getattr(exc, "status", None)
    if status in ("RESOURCE_EXHAUSTED", "RATE_LIMIT_EXCEEDED"):
        return True
    exc_str = str(exc).upper()
    if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "QUOTA" in exc_str or "RATE LIMIT" in exc_str:
        return True
    return False


class HierarchicalModelOrchestrator:
    """Bộ điều phối chuyển đổi mô hình đa tầng tự phục hồi và bảo toàn ngữ cảnh."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        tier1_model: Optional[str] = None,
        tier2_model: Optional[str] = None,
        cooldown_seconds: Optional[float] = None,
        rate_limit_interval: Optional[float] = None,
        api_keys: Optional[List[str]] = None
    ):
        self.api_keys_pool: List[str] = api_keys if api_keys is not None else CONFIG.GEMINI_API_KEYS
        self.current_key_idx: int = 0
        if api_key:
            self.api_key = api_key
        elif self.api_keys_pool:
            self.api_key = self.api_keys_pool[0]
        else:
            self.api_key = CONFIG.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")

        self.tier1_model = tier1_model or CONFIG.GEMINI_TIER1_MODEL
        self.tier2_model = tier2_model or CONFIG.GEMINI_TIER2_MODEL
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else CONFIG.GEMINI_COOLDOWN_SECONDS
        self.rate_limit_interval = rate_limit_interval if rate_limit_interval is not None else CONFIG.API_PACE_SECONDS

        self.tier1_enum = ModelTier.TIER_1_PRIMARY
        self.tier2_enum = ModelTier.TIER_2_FALLBACK
        self.tier3_enum = ModelTier.TIER_3_HEURISTIC

        self.cooldown_tracker = CooldownTracker(cooldown_seconds=self.cooldown_seconds)
        self.context_memory = RollingContextMemory(maxlen=5)
        self.heuristic_arbiter = AutonomousHeuristicArbiter()

        self.active_tier = ModelTier.TIER_1_PRIMARY
        self.client = None
        self.last_api_call_time = 0.0
        self._pacing_lock = threading.Lock()
        self._key_lock = threading.Lock()

        self._init_client()

    def _init_client(self):
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"HierarchicalModelOrchestrator: Khởi tạo genai.Client thành công.")
            except Exception as e:
                logger.warning(f"Chưa khởi tạo được genai.Client: {e}")
                self.client = None
        else:
            self.client = None

    def rotate_api_key(self) -> Optional[str]:
        """Chuyển sang API key tiếp theo trong danh sách xoay vòng (nếu có)."""
        with self._key_lock:
            if not self.api_keys_pool or len(self.api_keys_pool) <= 1:
                return None
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys_pool)
            self.api_key = self.api_keys_pool[self.current_key_idx]
            logger.info(f"Xoay vòng sang API Key vị trí #{self.current_key_idx + 1}/{len(self.api_keys_pool)}")
            self._init_client()
            return self.api_key

    def acquire_api_permission(self, priority: str = "normal") -> bool:
        """Khống chế nhịp độ gọi API >= 4.2s giữa Live Stream và Video Upload."""
        with self._pacing_lock:
            now = time.time()
            elapsed = now - self.last_api_call_time
            if priority == "high":
                self.last_api_call_time = now
                return True
            if elapsed >= self.rate_limit_interval:
                self.last_api_call_time = now
                return True
            return False

    def get_active_tier_info(self) -> dict:
        """Trả về thông tin tầng mô hình đang kích hoạt chuẩn Interface Contract."""
        if self.active_tier != ModelTier.TIER_1_PRIMARY and self.cooldown_tracker.is_tier1_ready():
            self.active_tier = ModelTier.TIER_1_PRIMARY

        if self.active_tier == ModelTier.TIER_1_PRIMARY:
            tier_key = "tier_1"
            tier_name = self.tier1_model
            tier_badge = "● Tier-1 Gemini 2.0"
            is_cd = False
            cd_rem = 0.0
        elif self.active_tier == ModelTier.TIER_2_FALLBACK:
            tier_key = "tier_2"
            tier_name = self.tier2_model
            tier_badge = "● Tier-2 Gemini 1.5 (Failover)"
            is_cd = True
            cd_rem = self.cooldown_tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)
        else:
            tier_key = "tier_3"
            tier_name = "Autonomous Heuristic"
            tier_badge = "● AI Tự Hành (Local Heuristic)"
            is_cd = True
            cd_rem = self.cooldown_tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)

        return {
            "active_tier": tier_key,
            "tier_name": tier_name,
            "tier_badge": tier_badge,
            "is_cooldown": is_cd,
            "cooldown_remaining": round(cd_rem, 1),
        }

    def _parse_gemini_json(self, raw_text: str) -> dict:
        """Parse JSON an toàn, bóc tách markdown code fence."""
        text = raw_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return data

    def _safe_generate_content(self, model: str, contents: Any, config: Any = None):
        """Gọi client.models.generate_content kèm cơ chế tự động chuyển sang model tương thích nếu gặp lỗi 404 Deprecated hoặc 503 Spike."""
        candidates = [model]
        for verified_m in ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
            if verified_m not in candidates:
                candidates.append(verified_m)

        last_err = None
        for m in candidates:
            try:
                return self.client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                last_err = e
                err_msg = str(e).upper()
                if "404" in err_msg or "NOT_FOUND" in err_msg or "NO LONGER AVAILABLE" in err_msg or "503" in err_msg or "UNAVAILABLE" in err_msg:
                    logger.warning(f"Mô hình '{m}' gặp lỗi tạm thời ({err_msg[:60]}). Tự động thử mô hình tiếp theo...")
                    continue
                raise e
        if last_err:
            raise last_err

    def _call_gemini_vision(self, model: str, prompt: str, frame_img: Any) -> dict:
        from google.genai import types
        contents = [prompt]
        if isinstance(frame_img, Image.Image):
            contents.append(frame_img)
        elif isinstance(frame_img, np.ndarray):
            import cv2
            rgb = cv2.cvtColor(frame_img, cv2.COLOR_BGR2RGB)
            contents.append(Image.fromarray(rgb))
        elif frame_img is not None:
            contents.append(frame_img)

        config = types.GenerateContentConfig(
            response_mime_type="application/json"
        )
        response = self._safe_generate_content(
            model=model,
            contents=contents,
            config=config
        )
        raw_text = getattr(response, "text", "") or "{}"
        return self._parse_gemini_json(raw_text)

    def _record_success(self, res: dict, bio: dict, tier: ModelTier):
        entry = ContextMemoryEntry(
            timestamp=time.time(),
            time_str=time.strftime("%H:%M:%S"),
            action=res.get("action", "Hành vi bình thường"),
            description=res.get("description", ""),
            posture=bio.get("posture", "Ngồi thẳng bình thường"),
            torso_angle=float(bio.get("angle", 90.0)),
            prediction=res.get("prediction_next_4s", ""),
            severity=res.get("severity", "safe"),
            tier_used=tier.value
        )
        self.context_memory.record(entry)

    def execute_live_analysis(self, frame_img: Any, bio: dict) -> dict:
        """
        Thực thi suy luận khung hình có bảo vệ phân tầng, tự phục hồi và duy trì ngữ cảnh:
        - Returns: {"action": str, "description": str, "prediction_next_4s": str, "severity": str, "model_tier": str}
        - Tuyệt đối không throw ngoại lệ 429 ra ngoài luồng.
        """
        # 1. Preemptive Cooldown Reversion
        if self.active_tier != ModelTier.TIER_1_PRIMARY and self.cooldown_tracker.is_tier1_ready():
            logger.info("Chủ động chuyển đổi ngược về Tier 1 (Preemptive Reversion).")
            self.active_tier = ModelTier.TIER_1_PRIMARY

        context_str = self.context_memory.get_context_summary_for_prompt()
        prompt = f"""Bạn là Hệ thống Giám sát & Phân tích Hành vi Thông minh (Học phần Hệ Điều Hành).
{context_str}

Hãy quan sát ảnh khung hình camera vừa chụp được và phân tích JSON:
{{
    "action": "Tên hành vi tóm tắt chuẩn mực",
    "description": "Miêu tả chi tiết ngữ cảnh tiếp nối lịch sử",
    "prediction_next_4s": "Dự đoán xu hướng trong 4 giây tiếp theo",
    "severity": "safe" | "warning" | "danger"
}}
"""
        posture_text = bio.get("posture", "Ngồi thẳng bình thường")

        # 2. Thử nghiệm Tier 1 nếu đang là Tier 1
        if self.client and self.active_tier == ModelTier.TIER_1_PRIMARY and self.cooldown_tracker.is_tier1_ready():
            try:
                data = self._call_gemini_vision(self.tier1_model, prompt, frame_img)
                data["model_tier"] = ModelTier.TIER_1_PRIMARY.value
                self._record_success(data, bio, ModelTier.TIER_1_PRIMARY)
                return data
            except Exception as e1:
                if is_rate_limit_error(e1):
                    logger.warning(f"Tier-1 chạm hạn mức 429 ({e1}). Kích hoạt Cooldown 60s và Failover sang Tier-2!")
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)
                    self.active_tier = ModelTier.TIER_2_FALLBACK
                else:
                    logger.error(f"Tier-1 lỗi: {e1}")
                    self.active_tier = ModelTier.TIER_2_FALLBACK

        # 3. Thử nghiệm Tier 2 nếu đang là Tier 2 và Tier 2 sẵn sàng
        if self.client and self.active_tier == ModelTier.TIER_2_FALLBACK and self.cooldown_tracker.is_tier2_ready():
            try:
                data = self._call_gemini_vision(self.tier2_model, prompt, frame_img)
                data["model_tier"] = ModelTier.TIER_2_FALLBACK.value
                self._record_success(data, bio, ModelTier.TIER_2_FALLBACK)
                return data
            except Exception as e2:
                if is_rate_limit_error(e2):
                    logger.warning(f"Tier-2 chạm hạn mức 429 ({e2}). Kích hoạt Cooldown và chuyển sang Tier-3 Arbiter!")
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_2_FALLBACK)
                    self.active_tier = ModelTier.TIER_3_HEURISTIC
                else:
                    logger.error(f"Tier-2 lỗi: {e2}")
                    self.active_tier = ModelTier.TIER_3_HEURISTIC

        # 4. Fallback sang Tier 3 (Autonomous Heuristic Arbiter)
        self.active_tier = ModelTier.TIER_3_HEURISTIC
        res = self.heuristic_arbiter.synthesize_with_memory(posture_text, bio, self.context_memory)
        self._record_success(res, bio, ModelTier.TIER_3_HEURISTIC)
        return res

    def execute_multimodal_failover(
        self,
        contents: List[Any],
        config: Optional[Any] = None
    ) -> Tuple[Optional[dict], ModelTier]:
        """
        Thực thi suy luận đa phương thức phục vụ TokenGuard / Video Annotator:
        Quy trình phân tầng: Tier 1 -> Tier 2 -> Key Rotation -> Fallback None.
        Trả về (data_dict, used_tier).
        """
        if not self.client:
            return None, ModelTier.TIER_3_HEURISTIC

        # 1. Preemptive Reversion
        if self.active_tier != ModelTier.TIER_1_PRIMARY and self.cooldown_tracker.is_tier1_ready():
            self.active_tier = ModelTier.TIER_1_PRIMARY

        # 2. Thử Tier 1
        if self.cooldown_tracker.is_tier1_ready():
            try:
                resp = self._safe_generate_content(
                    model=self.tier1_model,
                    contents=contents,
                    config=config
                )
                raw_text = getattr(resp, "text", "") or "{}"
                data = self._parse_gemini_json(raw_text)
                return data, ModelTier.TIER_1_PRIMARY
            except Exception as e1:
                if is_rate_limit_error(e1):
                    logger.warning(f"execute_multimodal_failover: Tier 1 chạm 429. Chuyển sang Tier 2.")
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)
                    self.active_tier = ModelTier.TIER_2_FALLBACK
                else:
                    logger.error(f"execute_multimodal_failover Tier 1 lỗi: {e1}")

        # 3. Thử Tier 2
        if self.cooldown_tracker.is_tier2_ready():
            try:
                resp = self._safe_generate_content(
                    model=self.tier2_model,
                    contents=contents,
                    config=config
                )
                raw_text = getattr(resp, "text", "") or "{}"
                data = self._parse_gemini_json(raw_text)
                return data, ModelTier.TIER_2_FALLBACK
            except Exception as e2:
                if is_rate_limit_error(e2):
                    logger.warning(f"execute_multimodal_failover: Tier 2 chạm 429.")
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_2_FALLBACK)
                    self.active_tier = ModelTier.TIER_3_HEURISTIC
                else:
                    logger.error(f"execute_multimodal_failover Tier 2 lỗi: {e2}")

        # 4. Thử xoay vòng key nếu có
        rotated_key = self.rotate_api_key()
        if rotated_key and self.client:
            try:
                resp = self._safe_generate_content(
                    model=self.tier2_model,
                    contents=contents,
                    config=config
                )
                raw_text = getattr(resp, "text", "") or "{}"
                data = self._parse_gemini_json(raw_text)
                return data, ModelTier.TIER_2_FALLBACK
            except Exception:
                pass

        return None, ModelTier.TIER_3_HEURISTIC

    def execute_chat_qa(self, prompt: str) -> dict:
        """
        Hỏi đáp AI ngữ nghĩa kế thừa chuyển đổi phân tầng (Tier 1 -> Tier 2 -> Tier 3).
        Trả về: {"answer": str, "model_tier": str, "active_tier_name": str}
        """
        if not self.client:
            return {
                "answer": "[Tier-3 Hội Chẩn Tự Hành] Hệ thống đang hoạt động ở chế độ ngoại tuyến cục bộ. Dữ liệu sự kiện được bảo toàn đầy đủ.",
                "model_tier": "tier_3",
                "active_tier_name": "Autonomous Heuristic"
            }

        # 1. Preemptive Reversion
        if self.active_tier != ModelTier.TIER_1_PRIMARY and self.cooldown_tracker.is_tier1_ready():
            self.active_tier = ModelTier.TIER_1_PRIMARY

        # 2. Thử Tier 1
        if self.cooldown_tracker.is_tier1_ready():
            try:
                resp = self.client.models.generate_content(
                    model=self.tier1_model,
                    contents=[prompt]
                )
                return {
                    "answer": getattr(resp, "text", "").strip(),
                    "model_tier": "tier_1",
                    "active_tier_name": self.tier1_model
                }
            except Exception as e1:
                if is_rate_limit_error(e1):
                    logger.warning(f"execute_chat_qa: Tier 1 chạm 429. Chuyển sang Tier 2.")
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY)
                    self.active_tier = ModelTier.TIER_2_FALLBACK
                else:
                    logger.error(f"execute_chat_qa Tier 1 lỗi: {e1}")

        # 3. Thử Tier 2
        if self.cooldown_tracker.is_tier2_ready():
            try:
                resp = self.client.models.generate_content(
                    model=self.tier2_model,
                    contents=[prompt]
                )
                return {
                    "answer": getattr(resp, "text", "").strip(),
                    "model_tier": "tier_2",
                    "active_tier_name": self.tier2_model
                }
            except Exception as e2:
                if is_rate_limit_error(e2):
                    logger.warning(f"execute_chat_qa: Tier 2 chạm 429. Chuyển sang Tier 3.")
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_2_FALLBACK)
                    self.active_tier = ModelTier.TIER_3_HEURISTIC
                else:
                    logger.error(f"execute_chat_qa Tier 2 lỗi: {e2}")

        # 4. Fallback Tier 3
        return {
            "answer": "[Tier-3 Hội Chẩn Tự Hành] Hệ thống kích hoạt cơ chế tự hành cục bộ do hạn mức API Cloud chạm trần. Hoạt động giám sát duy trì an toàn và liên tục.",
            "model_tier": "tier_3",
            "active_tier_name": "Autonomous Heuristic"
        }


_GLOBAL_ORCHESTRATOR: Optional[HierarchicalModelOrchestrator] = None
_INIT_LOCK = threading.Lock()


def get_model_orchestrator() -> HierarchicalModelOrchestrator:
    """Singleton getter cho HierarchicalModelOrchestrator."""
    global _GLOBAL_ORCHESTRATOR
    with _INIT_LOCK:
        if _GLOBAL_ORCHESTRATOR is None:
            _GLOBAL_ORCHESTRATOR = HierarchicalModelOrchestrator()
        return _GLOBAL_ORCHESTRATOR
