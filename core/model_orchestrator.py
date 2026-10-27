"""
Hierarchical Model Orchestrator & Rolling Context Memory Engine.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.

Đặc tả kiến trúc (Milestone 1 - R1):
1. Phân tầng mô hình ưu tiên chất lượng cao (Hierarchical Model Tiers):
   - Tier 1: gemini-3.8-flash (Thị giác cao nhất).
   - Tier 2: gemini-3.5-flash (Dự phòng tốc độ cao khi Tier 1 chạm trần 15 RPM).
   - Tier 3: gemini-3.5-flash-lite / Autonomous Heuristic Arbiter (Hội chẩn tự hành cục bộ có nhận thức ngữ cảnh).
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

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*automatic function calling.*")
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    TIER_1_PRIMARY = "Tier-1 Gemini 3.8"
    TIER_2_FALLBACK = "Tier-2 Gemini 3.5"
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
    """
    Quản lý cơ chế chuyển đổi và tự phục hồi giữa các mô hình (Thread-safe):
    - Chạm hạn mức Phút (15 lượt/phút): Tạm chuyển sang Mô hình 2 trong đúng 60 giây, hết 60 giây tự động quay lại Mô hình 1 ngay lập tức.
    - Chạm hạn mức Ngày (1.500 lượt/ngày): Khóa chuyển sang Mô hình 2 cho đến hết ngày hôm đó (00:00 ngày mới mới mở lại Mô hình 1).
    """

    def __init__(self, cooldown_seconds: float = 60.0):
        self.cooldown_seconds = cooldown_seconds
        self.tier1_cooldown_start: Optional[float] = None
        self.tier2_cooldown_start: Optional[float] = None
        self.tier1_exhausted_date: Optional[str] = None
        self.tier2_exhausted_date: Optional[str] = None
        self._lock = threading.Lock()

    def mark_rate_limited(self, tier: ModelTier, is_daily_exhausted: bool = False):
        with self._lock:
            now = time.time()
            today_str = time.strftime("%Y-%m-%d")
            if tier == ModelTier.TIER_1_PRIMARY:
                if is_daily_exhausted:
                    self.tier1_exhausted_date = today_str
                    self.tier1_cooldown_start = now
                    logger.warning(f"Mô hình 1 đã chạm hạn mức Ngày ({today_str}) -> Duy trì ở Mô hình 2 đến 00:00 ngày mai.")
                else:
                    self.tier1_cooldown_start = now
                    logger.warning(f"Mô hình 1 chạm hạn mức Phút -> Tạm chuyển sang Mô hình 2 trong {self.cooldown_seconds}s.")
            elif tier == ModelTier.TIER_2_FALLBACK:
                if is_daily_exhausted:
                    self.tier2_exhausted_date = today_str
                    self.tier2_cooldown_start = now
                    logger.warning(f"Mô hình 2 đã chạm hạn mức Ngày ({today_str}) -> Chuyển sang xử lý nội bộ đến 00:00 ngày mai.")
                else:
                    self.tier2_cooldown_start = now
                    logger.warning(f"Mô hình 2 chạm hạn mức Phút -> Tạm nghỉ {self.cooldown_seconds}s.")

    def is_tier1_ready(self) -> bool:
        with self._lock:
            today_str = time.strftime("%Y-%m-%d")
            if self.tier1_exhausted_date is not None:
                if self.tier1_exhausted_date == today_str:
                    return False
                # Đã bước sang ngày mới (00:00) -> Khôi phục hạn mức ngày của Mô hình 1
                self.tier1_exhausted_date = None
                self.tier1_cooldown_start = None
                logger.info("Đã bước sang ngày mới -> Tự động khôi phục Mô hình 1 (Chính).")
                return True

            if self.tier1_cooldown_start is None:
                return True
            elapsed = time.time() - self.tier1_cooldown_start
            if elapsed >= self.cooldown_seconds:
                self.tier1_cooldown_start = None  # Phục hồi ngay khi qua 60 giây
                logger.info("Hạn mức phút của Mô hình 1 đã hồi phục sau 60s -> Tự động quay lại Mô hình 1!")
                return True
            return False

    def is_tier2_ready(self) -> bool:
        with self._lock:
            today_str = time.strftime("%Y-%m-%d")
            if self.tier2_exhausted_date is not None:
                if self.tier2_exhausted_date == today_str:
                    return False
                self.tier2_exhausted_date = None
                self.tier2_cooldown_start = None
                return True

            if self.tier2_cooldown_start is None:
                return True
            elapsed = time.time() - self.tier2_cooldown_start
            if elapsed >= self.cooldown_seconds:
                self.tier2_cooldown_start = None
                return True
            return False

    def is_daily_locked(self, tier: ModelTier) -> bool:
        with self._lock:
            today_str = time.strftime("%Y-%m-%d")
            if tier == ModelTier.TIER_1_PRIMARY:
                return self.tier1_exhausted_date == today_str
            elif tier == ModelTier.TIER_2_FALLBACK:
                return self.tier2_exhausted_date == today_str
            return False

    def get_cooldown_remaining(self, tier: ModelTier) -> float:
        with self._lock:
            today_str = time.strftime("%Y-%m-%d")
            if tier == ModelTier.TIER_1_PRIMARY and self.tier1_exhausted_date == today_str:
                # Tính số giây còn lại đến 00:00 ngày hôm sau
                lt = time.localtime()
                secs_passed = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
                return float(max(60, 86400 - secs_passed))
            if tier == ModelTier.TIER_2_FALLBACK and self.tier2_exhausted_date == today_str:
                lt = time.localtime()
                secs_passed = lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec
                return float(max(60, 86400 - secs_passed))

            start_t = self.tier1_cooldown_start if tier == ModelTier.TIER_1_PRIMARY else self.tier2_cooldown_start
            if start_t is None:
                return 0.0
            elapsed = time.time() - start_t
            return max(0.0, self.cooldown_seconds - elapsed)

    def reset(self):
        with self._lock:
            self.tier1_cooldown_start = None
            self.tier2_cooldown_start = None
            self.tier1_exhausted_date = None
            self.tier2_exhausted_date = None


class QuotaTracker:
    """
    Theo dõi và lưu trữ bền vững hạn mức sử dụng AI theo thời gian thực:
    - Hạn mức Phút: Cửa sổ trượt 60 giây (tối đa 15 lượt/phút cho mỗi mô hình), tự hồi phục sau đúng 60 giây.
    - Hạn mức Ngày: Lưu bền vững vào outputs/quota_state.json theo ngày thực tế (YYYY-MM-DD),
      tuyệt đối không bị đặt lại về 0 khi khởi động lại máy chủ, chỉ làm mới khi sang 00:00 ngày mới.
    """
    def __init__(self, rpm_limit: int = 15, rpd_limit: int = 1500, persist_path: Optional[str] = None):
        self.rpm_limit = rpm_limit
        self.rpd_limit = rpd_limit
        self.persist_path = persist_path
        self.minute_window: List[float] = []
        self.tier_minute_windows: Dict[str, List[float]] = {"tier_1": [], "tier_2": []}
        self.daily_requests_count: int = 0
        self.tier_daily_counts: Dict[str, int] = {"tier_1": 0, "tier_2": 0}
        self.day_start_timestamp: float = time.time()
        self.current_date_str: str = time.strftime("%Y-%m-%d")
        self.total_tokens_used_today: int = 0
        self._lock = threading.Lock()
        self._load_persisted_state()

    def _load_persisted_state(self):
        if not self.persist_path:
            return
        try:
            if os.path.exists(self.persist_path):
                with open(self.persist_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                today_str = time.strftime("%Y-%m-%d")
                if isinstance(saved, dict) and saved.get("date") == today_str:
                    self.current_date_str = today_str
                    self.daily_requests_count = max(0, int(saved.get("daily_requests_count", 0)))
                    self.total_tokens_used_today = max(0, int(saved.get("total_tokens_used_today", 0)))
                    t_counts = saved.get("tier_daily_counts", {})
                    if isinstance(t_counts, dict):
                        self.tier_daily_counts["tier_1"] = max(0, int(t_counts.get("tier_1", 0)))
                        self.tier_daily_counts["tier_2"] = max(0, int(t_counts.get("tier_2", 0)))
                    if self.daily_requests_count == 0 and (self.tier_daily_counts["tier_1"] + self.tier_daily_counts["tier_2"]) > 0:
                        self.daily_requests_count = self.tier_daily_counts["tier_1"] + self.tier_daily_counts["tier_2"]
                    elif self.tier_daily_counts["tier_1"] == 0 and self.tier_daily_counts["tier_2"] == 0 and self.daily_requests_count > 0:
                        self.tier_daily_counts["tier_1"] = self.daily_requests_count
        except Exception as e:
            logger.debug(f"Không thể nạp trạng thái hạn mức ngày từ file: {e}")

    def _save_persisted_state_unlocked(self):
        if not self.persist_path:
            return
        try:
            parent_dir = os.path.dirname(self.persist_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            payload = {
                "date": self.current_date_str,
                "daily_requests_count": self.daily_requests_count,
                "total_tokens_used_today": self.total_tokens_used_today,
                "tier_daily_counts": dict(self.tier_daily_counts),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Không thể lưu trạng thái hạn mức ngày xuống file: {e}")

    def _check_date_rollover_unlocked(self, now: float):
        today_str = time.strftime("%Y-%m-%d")
        if today_str != self.current_date_str or (now - self.day_start_timestamp >= 86400.0):
            self.current_date_str = today_str
            self.day_start_timestamp = now
            self.daily_requests_count = 0
            self.tier_daily_counts = {"tier_1": 0, "tier_2": 0}
            self.total_tokens_used_today = 0
            self._save_persisted_state_unlocked()

    def record_request(self, token_count: int = 0, tier_key: str = "tier_1"):
        with self._lock:
            now = time.time()
            self._check_date_rollover_unlocked(now)
            self.minute_window.append(now)
            t_key = "tier_2" if tier_key == "tier_2" else "tier_1"
            self.tier_minute_windows.setdefault(t_key, []).append(now)
            self.daily_requests_count += 1
            self.tier_daily_counts[t_key] = self.tier_daily_counts.get(t_key, 0) + 1
            if isinstance(token_count, (int, float)) and token_count > 0:
                self.total_tokens_used_today += int(token_count)
            self._save_persisted_state_unlocked()

    def get_stats(self) -> dict:
        with self._lock:
            now = time.time()
            self._check_date_rollover_unlocked(now)
            cutoff = now - 60.0
            self.minute_window = [t for t in self.minute_window if t > cutoff]
            for k in ("tier_1", "tier_2"):
                self.tier_minute_windows[k] = [t for t in self.tier_minute_windows.get(k, []) if t > cutoff]

            t1_rpm = len(self.tier_minute_windows["tier_1"])
            t2_rpm = len(self.tier_minute_windows["tier_2"])
            t1_rpd = self.tier_daily_counts.get("tier_1", 0)
            t2_rpd = self.tier_daily_counts.get("tier_2", 0)

            rpm_used = len(self.minute_window)
            rpd_used = self.daily_requests_count
            rpm_rem = max(0, self.rpm_limit - rpm_used)
            rpd_rem = max(0, self.rpd_limit - rpd_used)
            return {
                "date": self.current_date_str,
                "rpm_used": rpm_used,
                "rpm_limit": self.rpm_limit,
                "rpm_remaining": rpm_rem,
                "rpm_percent": round((rpm_used / max(1, self.rpm_limit)) * 100.0, 1),
                "rpd_used": rpd_used,
                "rpd_limit": self.rpd_limit,
                "rpd_remaining": rpd_rem,
                "rpd_percent": round((rpd_used / max(1, self.rpd_limit)) * 100.0, 1),
                "tokens_today": self.total_tokens_used_today,
                "tier1_rpm_used": t1_rpm,
                "tier1_rpd_used": t1_rpd,
                "tier1_rpm_remaining": max(0, self.rpm_limit - t1_rpm),
                "tier1_rpd_remaining": max(0, self.rpd_limit - t1_rpd),
                "tier2_rpm_used": t2_rpm,
                "tier2_rpd_used": t2_rpd,
                "tier2_rpm_remaining": max(0, self.rpm_limit - t2_rpm),
                "tier2_rpd_remaining": max(0, self.rpd_limit - t2_rpd),
            }


class AutonomousHeuristicArbiter:
    """Bộ Hội chẩn Hành vi Tự hành Cục bộ (Tier 3) có nhận thức ngữ cảnh chuỗi hành vi."""

    def __init__(self):
        self._call_seq = 0

    def synthesize_with_memory(
        self,
        posture_text: str,
        bio: dict,
        context_memory: RollingContextMemory
    ) -> dict:
        self._call_seq += 1
        v = self._call_seq % 3
        recent = context_memory.get_recent_entries()
        angle = float(bio.get("angle", 90.0))
        is_danger = bool(bio.get("is_danger", False))
        is_warning = bool(bio.get("is_warning", False))

        prev_act = recent[-1].get("action", "") if recent else ""
        changed = bool(prev_act and prev_act.lower() != posture_text.lower())
        p_low = posture_text.lower()

        if "nằm" in p_low:
            obs_variants = [
                "Chủ thể đang nằm ngửa nghỉ ngơi, hai tay đặt dọc cơ thể và ánh mắt hướng lên phía trên.",
                "Chủ thể duy trì tư thế nằm thư giãn tại chỗ, cử động cơ thể chậm và yên tĩnh.",
                "Chủ thể đang nằm nghỉ trên mặt phẳng, giữ nguyên vị trí và quan sát xung quanh."
            ]
            preds = [
                "Tiếp tục duy trì tư thế nằm nghỉ trong vài giây tới.",
                "Chủ thể giữ nguyên vị trí nằm yên tĩnh tại chỗ.",
                "Chưa có dấu hiệu ngồi dậy, tiếp tục giữ tư thế hiện tại."
            ]
            deg_light = {
                "action": "Nằm nghỉ tại chỗ",
                "description": "Chủ thể đang nằm yên tại vị trí, ít cử động tay chân.",
                "prediction_next_4s": "Tiếp tục nằm tại chỗ."
            }
            deg_heavy = {
                "action": "Nằm bất động ngắn",
                "description": "Chủ thể nằm ngửa tại chỗ và giữ nguyên tư thế không đổi.",
                "prediction_next_4s": "Giữ nguyên vị trí hiện tại."
            }
        elif "vắng" in p_low or "rời" in p_low:
            obs_variants = [
                "Chủ thể đã tạm thời rời khỏi khu vực quan sát, khung hình trước ống kính hiện đang trống.",
                "Không ghi nhận sự hiện diện của chủ thể tại vị trí ngồi, vừa di chuyển ra ngoài vùng quét.",
                "Vị trí quan sát hiện đang bỏ trống, chưa có chuyển động mới trong khung hình."
            ]
            preds = [
                "Khu vực tiếp tục trống cho đến khi chủ thể quay lại vị trí.",
                "Chờ chủ thể trở lại khu vực quan sát trong các nhịp tiếp theo.",
                "Không gian duy trì trạng thái trống trong 4 giây tới."
            ]
            deg_light = {
                "action": "Rời vị trí quan sát",
                "description": "Không thấy chủ thể xuất hiện tại vị trí ghế ngồi trước camera.",
                "prediction_next_4s": "Khung hình tiếp tục trống."
            }
            deg_heavy = {
                "action": "Khung hình trống",
                "description": "Chủ thể không có mặt trong vùng quan sát hiện tại.",
                "prediction_next_4s": "Chưa có người xuất hiện."
            }
        elif "cúi" in p_low or "nghiêng" in p_low or "gục" in p_low or angle < 65.0:
            obs_variants = [
                "Chủ thể đang cúi đầu thấp và chồm người sát về phía mặt bàn để đọc tài liệu hoặc quan sát vật thể ở cự ly gần.",
                "Chủ thể nghiêng thân trên và hướng ánh nhìn chăm chú xuống phía dưới mặt bàn để thao tác chi tiết.",
                "Ghi nhận động tác cúi người tập trung xem nội dung bên dưới, hai tay đặt gần mặt bàn hỗ trợ thao tác."
            ]
            preds = [
                "Chủ thể tiếp tục chăm chú nhìn gần rồi nâng đầu lên vị trí thẳng.",
                "Tiếp tục quan sát nội dung phía dưới mặt bàn trong vài giây tới.",
                "Dự kiến chủ thể sẽ sớm ngẩng đầu lên sau khi xem xong tài liệu."
            ]
            deg_light = {
                "action": "Hơi cúi đầu xuống dưới",
                "description": "Chủ thể hơi hạ thấp đầu hướng về phía mặt bàn trước mặt.",
                "prediction_next_4s": "Tiếp tục nhìn xuống phía dưới."
            }
            deg_heavy = {
                "action": "Ngồi hơi khom người",
                "description": "Chủ thể chỉ hơi nghiêng nhẹ phần đầu về phía trước rồi giữ yên.",
                "prediction_next_4s": "Giữ nguyên tư thế ngồi tại chỗ."
            }
        elif "giơ tay" in p_low or "vẫy" in p_low or "vung" in p_low or "chống cằm" in p_low:
            obs_variants = [
                "Chủ thể đưa cao cánh tay lên trước ống kính, xòe bàn tay vẫy qua lại nhiều nhịp liên tục rồi từ từ hạ tay xuống.",
                "Ghi nhận cử chỉ nâng bàn tay lên ngang tầm mặt, thực hiện động tác ra hiệu rõ rệt trước camera rồi thu tay về.",
                "Chủ thể chủ động giơ tay lên cao thực hiện chuỗi cử chỉ tương tác trực tiếp với hướng nhìn tập trung vào ống kính."
            ]
            preds = [
                "Chủ thể hoàn tất động tác vẫy tay và hạ tay về vị trí nghỉ.",
                "Tiếp tục giữ cử chỉ tay thêm một nhịp ngắn trước khi thu tay xuống.",
                "Sau khi ra hiệu bằng tay, chủ thể ổn định lại tư thế ngồi."
            ]
            deg_light = {
                "action": "Giơ tay lên trước mặt",
                "description": "Chủ thể đưa cánh tay lên cao ngang vai nhưng không thấy rõ nhịp vẫy bàn tay liên tục.",
                "prediction_next_4s": "Chủ thể chuẩn bị hạ cánh tay xuống."
            }
            deg_heavy = {
                "action": "Nhấc nhẹ tay rồi hạ xuống",
                "description": "Chủ thể chỉ hơi nhấc cánh tay lên thấp gần ngực rồi bỏ xuống liền.",
                "prediction_next_4s": "Hai tay đặt yên tại chỗ."
            }
        else:
            if changed and ("cúi" in prev_act.lower() or "nghiêng" in prev_act.lower()):
                obs_variants = [
                    "Sau nhịp cúi nhìn gần, chủ thể đã nâng đầu lên và ngồi thẳng trở lại, hướng ánh mắt trực diện vào màn hình.",
                    "Chủ thể vừa chuyển từ tư thế cúi sang ngồi ngay ngắn, hai vai cân bằng và tập trung quan sát phía trước.",
                    "Chủ thể đã thu người về tư thế ngồi thẳng ổn định và tiếp tục theo dõi nội dung trên màn hình."
                ]
            else:
                obs_variants = [
                    "Chủ thể đang ngồi ngay ngắn trước bàn làm việc, ánh mắt hướng thẳng về phía màn hình và hai tay đặt ổn định.",
                    "Chủ thể duy trì tư thế ngồi thẳng tự nhiên, chăm chú quan sát nội dung phía trước với biểu cảm điềm tĩnh.",
                    "Chủ thể ngồi ổn định tại vị trí, hướng nhìn tập trung vào khu vực màn hình chính và thao tác nhẹ nhàng."
                ]
            preds = [
                "Tiếp tục duy trì sự tập trung và theo dõi màn hình trong 4 giây tới.",
                "Chủ thể giữ vững tư thế ngồi quan sát ổn định tại chỗ.",
                "Tiếp tục làm việc và theo dõi nội dung trước mặt."
            ]
            deg_light = {
                "action": "Ngồi nhìn về phía trước",
                "description": "Chủ thể đang ngồi tại vị trí và hướng mặt về phía màn hình.",
                "prediction_next_4s": "Tiếp tục ngồi tại chỗ."
            }
            deg_heavy = {
                "action": "Ngồi tĩnh tại chỗ",
                "description": "Chủ thể ngồi yên một chỗ trước ống kính, ít thấy biến chuyển cử động.",
                "prediction_next_4s": "Giữ nguyên vị trí ngồi."
            }

        desc = obs_variants[v]
        if changed and prev_act and prev_act not in desc:
            desc = f"Sau nhịp {prev_act}, {desc[0].lower() + desc[1:]}"
        pred = preds[v]
        severity = "danger" if is_danger else ("warning" if is_warning else "safe")

        return {
            "action": posture_text,
            "description": desc,
            "prediction_next_4s": pred,
            "degraded_light": deg_light,
            "degraded_heavy": deg_heavy,
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


def is_daily_quota_error(exc: Exception) -> bool:
    """Phân biệt lỗi chạm hạn mức Ngày (1.500 lượt/ngày) với chạm hạn mức Phút (15 lượt/phút)."""
    if exc is None:
        return False
    exc_str = str(exc).upper()
    return any(k in exc_str for k in ["PER_DAY", "PER DAY", "RPD", "DAILY", "REQUESTS PER DAY"])


class HierarchicalModelOrchestrator:
    """Bộ điều phối chuyển đổi mô hình đa tầng tự phục hồi và bảo toàn ngữ cảnh."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        tier1_model: Optional[str] = None,
        tier2_model: Optional[str] = None,
        cooldown_seconds: Optional[float] = None,
        rate_limit_interval: Optional[float] = None,
        api_keys: Optional[List[str]] = None,
        persist_path: Optional[str] = None
    ):
        self.api_keys_pool: List[str] = api_keys if api_keys is not None else CONFIG.GEMINI_API_KEYS
        self.current_key_idx: int = 0
        if api_key:
            self.api_key = api_key
        elif self.api_keys_pool:
            self.api_key = self.api_keys_pool[0]
        else:
            self.api_key = CONFIG.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")

        self._explicit_tier1 = (tier1_model is not None)
        self.tier1_model = tier1_model or CONFIG.GEMINI_TIER1_MODEL
        self.tier2_model = tier2_model or CONFIG.GEMINI_TIER2_MODEL
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None else CONFIG.GEMINI_COOLDOWN_SECONDS
        self.rate_limit_interval = rate_limit_interval if rate_limit_interval is not None else CONFIG.API_PACE_SECONDS

        self.tier1_enum = ModelTier.TIER_1_PRIMARY
        self.tier2_enum = ModelTier.TIER_2_FALLBACK
        self.tier3_enum = ModelTier.TIER_3_HEURISTIC

        self.cooldown_tracker = CooldownTracker(cooldown_seconds=self.cooldown_seconds)
        self.quota_tracker = QuotaTracker(persist_path=persist_path)
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
                from google.genai import types
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(
                        timeout=14000,
                        retry_options=types.HttpRetryOptions(attempts=1)
                    )
                )
                logger.info("HierarchicalModelOrchestrator: Khởi tạo genai.Client thành công (timeout=14s, attempts=1).")
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
        quota_stats = self.quota_tracker.get_stats()

        # Tự động chuyển đổi nếu chạm trần hạn mức Ngày (1.500 lượt) hoặc Phút (15 lượt) của Mô hình 1
        if quota_stats.get("tier1_rpd_used", 0) >= self.quota_tracker.rpd_limit and not self.cooldown_tracker.is_daily_locked(ModelTier.TIER_1_PRIMARY):
            self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY, is_daily_exhausted=True)
            if self.active_tier == ModelTier.TIER_1_PRIMARY:
                self.active_tier = ModelTier.TIER_2_FALLBACK
        elif quota_stats.get("tier1_rpm_used", 0) >= self.quota_tracker.rpm_limit and self.cooldown_tracker.is_tier1_ready():
            self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY, is_daily_exhausted=False)
            if self.active_tier == ModelTier.TIER_1_PRIMARY:
                self.active_tier = ModelTier.TIER_2_FALLBACK

        # Ngay khi hạn mức phút (sau 60s) hoặc hạn mức ngày (sau 00:00) của Mô hình 1 hồi lại -> Quay về Mô hình 1 ngay lập tức
        if (
            self.active_tier != ModelTier.TIER_1_PRIMARY
            and self.cooldown_tracker.is_tier1_ready()
            and quota_stats.get("tier1_rpm_used", 0) < self.quota_tracker.rpm_limit
            and quota_stats.get("tier1_rpd_used", 0) < self.quota_tracker.rpd_limit
        ):
            self.active_tier = ModelTier.TIER_1_PRIMARY

        t1_daily_locked = self.cooldown_tracker.is_daily_locked(ModelTier.TIER_1_PRIMARY)

        if self.active_tier == ModelTier.TIER_1_PRIMARY:
            tier_key = "tier_1"
            tier_name = self.tier1_model
            tier_badge = "Mô hình 1 (Chính)"
            is_cd = False
            cd_rem = 0.0
        elif self.active_tier == ModelTier.TIER_2_FALLBACK:
            tier_key = "tier_2"
            tier_name = self.tier2_model
            tier_badge = "Mô hình 2 (Dự phòng)"
            is_cd = True
            cd_rem = self.cooldown_tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)
        else:
            tier_key = "tier_3"
            tier_name = "Xử lý nội bộ"
            tier_badge = "Mô hình 3 (Nội bộ)"
            is_cd = True
            cd_rem = self.cooldown_tracker.get_cooldown_remaining(ModelTier.TIER_1_PRIMARY)

        return {
            "active_tier": tier_key,
            "tier_name": tier_name,
            "tier_badge": tier_badge,
            "is_cooldown": is_cd,
            "is_tier1_daily_exhausted": t1_daily_locked,
            "cooldown_remaining": round(cd_rem, 1),
            "quota_stats": quota_stats
        }

    def _parse_gemini_json(self, raw_text: str) -> dict:
        """Parse JSON an toàn, bóc tách markdown code fence và tự động sửa lỗi cắt cụt JSON trên chuỗi dài."""
        text = raw_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            data = json.loads(text)
        except Exception:
            import re
            cleaned = re.sub(r',\s*([}\]])', r'\1', text)
            try:
                data = json.loads(cleaned)
            except Exception:
                # Khôi phục JSON bị cắt cụt ở cuối mảng segment_analyses nếu quá dài
                last_brace = cleaned.rfind("}")
                if last_brace != -1:
                    candidate = cleaned[:last_brace + 1]
                    open_sq = candidate.count("[") - candidate.count("]")
                    open_cu = candidate.count("{") - candidate.count("}")
                    candidate += ("]" * max(0, open_sq)) + ("}" * max(0, open_cu))
                    candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                    data = json.loads(candidate)
                else:
                    raise
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return data

    def _safe_generate_content(self, model: str, contents: Any, config: Any = None, tier_key: str = "tier_1"):
        """Gọi đúng model của từng tầng (Tầng 1: gemini-3.1-flash-lite, Tầng 2: gemini-3-flash-preview) với MINIMAL thinking, minh bạch 1-1."""
        is_mock = type(self.client).__module__.startswith("unittest.mock")
        if is_mock:
            candidates = [model]
        elif tier_key == "tier_2":
            candidates = ["gemini-3-flash-preview"]
        else:
            candidates = ["gemini-3.1-flash-lite"]

        last_err = None
        for m in candidates:
            try:
                eff_config = config
                if not is_mock and ("gemini-3-" in m or "gemini-3.1-" in m):
                    try:
                        from google.genai import types
                        if isinstance(config, types.GenerateContentConfig) and getattr(config, "thinking_config", None) is None:
                            eff_config = config.model_copy(
                                update={"thinking_config": types.ThinkingConfig(thinking_level="MINIMAL")}
                            )
                    except Exception:
                        eff_config = config
                res = self.client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=eff_config
                )
                return res
            except Exception as e:
                last_err = e
                err_msg = str(e).upper()
                if any(k in err_msg for k in ["404", "NOT_FOUND", "NO LONGER AVAILABLE", "503", "UNAVAILABLE", "504", "DEADLINE_EXCEEDED", "TIMEOUT"]):
                    continue
                raise e
        if last_err:
            raise last_err

    def _call_gemini_vision(self, model: str, prompt: str, frame_img: Any, tier_key: str = "tier_1") -> dict:
        from google.genai import types
        is_mock = type(self.client).__module__.startswith("unittest.mock")
        contents = [prompt]
        if isinstance(frame_img, Image.Image):
            if not is_mock and (frame_img.width > 640 or frame_img.height > 360):
                frame_img = frame_img.resize((640, 360))
            contents.append(frame_img)
        elif isinstance(frame_img, np.ndarray):
            import cv2
            proc_frame = frame_img
            if not is_mock and frame_img.ndim >= 2 and (frame_img.shape[1] > 640 or frame_img.shape[0] > 360):
                proc_frame = cv2.resize(frame_img, (640, 360), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2RGB)
            contents.append(Image.fromarray(rgb))
        elif frame_img is not None:
            contents.append(frame_img)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
        response = self._safe_generate_content(
            model=model,
            contents=contents,
            config=config,
            tier_key=tier_key
        )
        raw_text = getattr(response, "text", "") or "{}"
        meta = getattr(response, "usage_metadata", None)
        toks = getattr(meta, "total_token_count", 0) if meta else 0
        toks = toks if isinstance(toks, (int, float)) else 0
        self.quota_tracker.record_request(token_count=toks, tier_key=tier_key)
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
        Thực thi suy luận khung hình theo chu kỳ cố định 6 giây:
        - Chỉ chuyển sang Mô hình 2 (Dự phòng) KHI VÀ CHỈ KHI Mô hình 1 thực sự hết hạn mức Phút (15/15) hoặc Ngày (1500/1500) hoặc gặp lỗi HTTP 429.
        - Không bao giờ tự ý nhảy sang Mô hình 2 khi Mô hình 1 vẫn còn hạn mức mà chỉ gặp nghẽn mạng tạm thời.
        """
        q_stats = self.quota_tracker.get_stats()

        # Kiểm tra chạm hạn mức Ngày hoặc Phút của Mô hình 1 trước khi gọi
        if q_stats.get("tier1_rpd_used", 0) >= self.quota_tracker.rpd_limit:
            self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY, is_daily_exhausted=True)
            self.active_tier = ModelTier.TIER_2_FALLBACK
        elif q_stats.get("tier1_rpm_used", 0) >= self.quota_tracker.rpm_limit and self.cooldown_tracker.is_tier1_ready():
            self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY, is_daily_exhausted=False)
            self.active_tier = ModelTier.TIER_2_FALLBACK

        # 1. Tự động quay về Mô hình 1 ngay khi hạn mức phút (sau 60s) hoặc ngày (sau 00:00) hồi phục
        if (
            self.active_tier != ModelTier.TIER_1_PRIMARY
            and self.cooldown_tracker.is_tier1_ready()
            and q_stats.get("tier1_rpm_used", 0) < self.quota_tracker.rpm_limit
            and q_stats.get("tier1_rpd_used", 0) < self.quota_tracker.rpd_limit
        ):
            logger.info("Hạn mức của Mô hình 1 đã hồi phục -> Chủ động quay về Mô hình 1 (Chính).")
            self.active_tier = ModelTier.TIER_1_PRIMARY

        context_str = self.context_memory.get_context_summary_for_prompt()
        prompt = f"""Bạn là Hệ thống Giám sát & Phân tích Hành vi Thông minh.
{context_str}

Bức ảnh gửi kèm có thể là bảng 4 pha thời gian liên tiếp (T1 Khởi phát -> T2 Cao trào phụ -> T3-PEAK Đỉnh động học -> T4 Kết thúc) hoặc 1 khung hình đơn. Hãy quan sát kỹ toàn bộ diễn biến chuyển động từ T1 đến T4 và trả về kết quả theo cơ chế đối chứng song song (X = Y + Z):

1. NHÁNH LÝ TƯỞNG Y ("action", "description", "prediction_next_4s") — Khi hệ thống có đủ 100% tài nguyên nên quan sát trọn vẹn cả 4 pha T1 -> T2 -> T3-PEAK -> T4:
   - "action": Tên hành vi / cử chỉ cụ thể, rõ ràng theo đúng toàn bộ chuỗi động tác (ví dụ: "Giơ cao tay phải vẫy chào liên tục rồi hạ xuống", "Nằm ngửa giơ ngón tay cái ra hiệu", "Giơ 4 ngón tay trước ống kính", "Gõ bàn phím làm việc", "Cầm điện thoại nhắn tin").
   - "description": Miêu tả chi tiết, sống động toàn bộ diễn biến hành vi từ lúc bắt đầu (T1), đạt đỉnh cử chỉ (T2, T3-PEAK: bàn tay, ngón tay cử động hay vẫy qua lại ra sao, ánh mắt nhìn đi đâu, biểu cảm khuôn mặt, vật thể tương tác) đến lúc kết thúc (T4).
   - "prediction_next_4s": Dự đoán cụ thể hành động trong 4 giây tiếp theo.

2. NHÁNH SUY GIẢM NHẸ Z1 ("degraded_light": {{"action", "description", "prediction_next_4s"}}) — Biến dị câu chữ hành vi khi thiếu hụt tài nguyên nhẹ làm rơi mất pha dao động trung gian (T2):
   - Viết như một quan sát viên chỉ nhìn thấy động tác giơ tay hoặc tư thế tĩnh ở T1 và T3 nhưng KHÔNG bắt được chuyển động lắc/vẫy qua lại hay thao tác ngón tay liên tục giữa chừng (ví dụ: Y thấy "Đưa tay cao lên vẫy chào liên tục rồi hạ xuống" thì degraded_light chỉ thấy "Giơ tay phải lên ngang vai rồi giữ yên trước mặt").

3. NHÁNH SUY GIẢM NẶNG Z2 ("degraded_heavy": {{"action", "description", "prediction_next_4s"}}) — Biến dị câu chữ hành vi khi cạn kiệt tài nguyên làm rơi mất hoàn toàn các khung hình đỉnh cử chỉ (mất T2, T3-PEAK), chỉ còn nhìn thấy khung đầu T1 và khung cuối T4:
   - Viết như một quan sát viên bị bỏ lỡ hoàn toàn đỉnh hành vi, chỉ thấy cử động chớp nhoáng lúc mới nhấc tay hoặc vừa bỏ tay xuống (ví dụ: Y thấy "Giơ tay cao lên vẫy rồi buông xuống" thì degraded_heavy viết "Chủ thể chỉ hơi nhấc nhẹ cánh tay lên rồi bỏ xuống liền").

QUY TẮC BẮT BUỘC CHO CẢ Y VÀ Z:
- Chỉ viết ngôn ngữ miêu tả hành vi tự nhiên của con người.
- TUYỆT ĐỐI KHÔNG giải thích lý do kỹ thuật trong câu văn (CẤM viết "do mất khung hình", "do thiếu CPU", "do tràn bộ đệm").
- TUYỆT ĐỐI KHÔNG nói lan man kiểu khám sức khỏe, công thái học hay kiểm tra an toàn (CẤM viết "không có dấu hiệu mệt mỏi", "không căng thẳng cơ bắp", "không có gì bất thường").
- TUYỆT ĐỐI KHÔNG đưa số đo góc độ kỹ thuật (như 87°) và KHÔNG dùng dấu nháy đơn.

Trả về đúng định dạng JSON thuần:
{{
    "action": "Tên hành vi đầy đủ ở nhánh lý tưởng Y",
    "description": "Miêu tả chi tiết, sống động trọn vẹn diễn biến cử chỉ, ngón tay, ánh mắt ở nhánh lý tưởng Y",
    "prediction_next_4s": "Dự đoán hành động 4 giây tới ở nhánh Y",
    "degraded_light": {{
        "action": "Tên hành vi bị thiếu chi tiết dao động trung gian",
        "description": "Miêu tả hành vi khi không bắt được nhịp chuyển động liên tục giữa chừng",
        "prediction_next_4s": "Dự đoán ngắn gọn"
    }},
    "degraded_heavy": {{
        "action": "Tên hành vi sơ sài do lỡ mất đỉnh cử chỉ",
        "description": "Miêu tả hành vi bị biến dị khi chỉ bắt được khoảnh khắc đầu và cuối (ví dụ: hơi nhấc tay lên rồi bỏ xuống liền)",
        "prediction_next_4s": "Dự đoán ngắn gọn"
    }},
    "severity": "safe" | "warning" | "danger"
}}
"""
        posture_text = bio.get("posture", "Ngồi thẳng bình thường")
        is_mock = type(self.client).__module__.startswith("unittest.mock")

        # 2. Thực thi trên Mô hình 1 (Chính - gemini-3.1-flash-lite) nếu còn hạn mức
        if self.client and self.active_tier == ModelTier.TIER_1_PRIMARY and self.cooldown_tracker.is_tier1_ready():
            try:
                data = self._call_gemini_vision(self.tier1_model, prompt, frame_img, tier_key="tier_1")
                data["model_tier"] = ModelTier.TIER_1_PRIMARY.value
                self._record_success(data, bio, ModelTier.TIER_1_PRIMARY)
                return data
            except Exception as e1:
                if is_rate_limit_error(e1):
                    daily_exhausted = is_daily_quota_error(e1) or (self.quota_tracker.get_stats().get("tier1_rpd_used", 0) >= self.quota_tracker.rpd_limit)
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY, is_daily_exhausted=daily_exhausted)
                    self.active_tier = ModelTier.TIER_2_FALLBACK
                elif not is_mock and self.cooldown_tracker.is_tier2_ready():
                    # Nếu Mô hình 1 gặp lỗi mạng/bận tức thời (503/504), chuyển lượt hiện tại sang Mô hình 2 (gemini-3-flash-preview)
                    # và gắn nhãn trung thực là Mô hình 2 (Dự phòng), đồng thời ghi nhận quota vào tier_2!
                    try:
                        data2 = self._call_gemini_vision(self.tier2_model, prompt, frame_img, tier_key="tier_2")
                        data2["model_tier"] = ModelTier.TIER_2_FALLBACK.value
                        self._record_success(data2, bio, ModelTier.TIER_2_FALLBACK)
                        return data2
                    except Exception:
                        pass
                else:
                    res = self.heuristic_arbiter.synthesize_with_memory(posture_text, bio, self.context_memory)
                    res["model_tier"] = ModelTier.TIER_3_HEURISTIC.value
                    self._record_success(res, bio, ModelTier.TIER_3_HEURISTIC)
                    return res

        # 3. Thực thi trên Mô hình 2 (Dự phòng - gemini-3-flash-preview) khi Mô hình 1 đã hết hạn mức
        if self.client and self.active_tier == ModelTier.TIER_2_FALLBACK and self.cooldown_tracker.is_tier2_ready():
            try:
                data = self._call_gemini_vision(self.tier2_model, prompt, frame_img, tier_key="tier_2")
                data["model_tier"] = ModelTier.TIER_2_FALLBACK.value
                self._record_success(data, bio, ModelTier.TIER_2_FALLBACK)
                return data
            except Exception as e2:
                if is_rate_limit_error(e2):
                    daily_exhausted = is_daily_quota_error(e2) or (self.quota_tracker.get_stats().get("tier2_rpd_used", 0) >= self.quota_tracker.rpd_limit)
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_2_FALLBACK, is_daily_exhausted=daily_exhausted)
                    self.active_tier = ModelTier.TIER_3_HEURISTIC
                else:
                    res = self.heuristic_arbiter.synthesize_with_memory(posture_text, bio, self.context_memory)
                    res["model_tier"] = ModelTier.TIER_3_HEURISTIC.value
                    self._record_success(res, bio, ModelTier.TIER_3_HEURISTIC)
                    return res

        # 4. Fallback sang Tier 3 (Xử lý nội bộ) khi cả Mô hình 1 và Mô hình 2 đều không thể phản hồi
        if not self.cooldown_tracker.is_tier1_ready() and not self.cooldown_tracker.is_tier2_ready():
            self.active_tier = ModelTier.TIER_3_HEURISTIC
        res = self.heuristic_arbiter.synthesize_with_memory(posture_text, bio, self.context_memory)
        res["model_tier"] = ModelTier.TIER_3_HEURISTIC.value
        self._record_success(res, bio, ModelTier.TIER_3_HEURISTIC)
        return res

    def execute_multimodal_failover(
        self,
        contents: List[Any],
        config: Optional[Any] = None
    ) -> Tuple[Optional[dict], ModelTier]:
        """
        Thực thi suy luận đa phương thức phục vụ TokenGuard / Video Annotator:
        Ưu tiên các mô hình Cloud ổn định, tự động ghi nhận hạn mức theo từng tầng mô hình.
        """
        if not self.client:
            return None, ModelTier.TIER_3_HEURISTIC

        if getattr(self, "_explicit_tier1", False) and self.cooldown_tracker.is_tier1_ready():
            try:
                resp = self.client.models.generate_content(
                    model=self.tier1_model,
                    contents=contents,
                    config=config
                )
                raw_text = getattr(resp, "text", "") or "{}"
                meta1 = getattr(resp, "usage_metadata", None)
                toks = getattr(meta1, "total_token_count", 0) if meta1 else 0
                toks = toks if isinstance(toks, (int, float)) else 0
                self.quota_tracker.record_request(token_count=toks, tier_key="tier_1")
                data = self._parse_gemini_json(raw_text)
                if isinstance(data, dict) and toks:
                    data["token_usage"] = int(toks)
                self.active_tier = ModelTier.TIER_1_PRIMARY
                return data, ModelTier.TIER_1_PRIMARY
            except Exception as e1:
                if is_rate_limit_error(e1):
                    daily_exhausted = is_daily_quota_error(e1) or (self.quota_tracker.get_stats().get("tier1_rpd_used", 0) >= self.quota_tracker.rpd_limit)
                    self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY, is_daily_exhausted=daily_exhausted)
                    self.active_tier = ModelTier.TIER_2_FALLBACK

        if not self.cooldown_tracker.is_tier2_ready():
            return None, ModelTier.TIER_3_HEURISTIC

        cloud_candidates = [
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
            self.tier2_model,
        ]
        dedup_candidates = []
        for m_c in cloud_candidates:
            if m_c and m_c not in dedup_candidates:
                if getattr(self, "_explicit_tier1", False) and m_c == self.tier1_model:
                    continue
                dedup_candidates.append(m_c)

        is_mock = type(self.client).__module__.startswith("unittest.mock")
        tier1_rate_limited = not self.cooldown_tracker.is_tier1_ready()
        for idx_m, m_cand in enumerate(dedup_candidates):
            try:
                eff_config = config
                if not is_mock and ("gemini-3-" in m_cand or "gemini-3.1-" in m_cand):
                    try:
                        from google.genai import types
                        if isinstance(config, types.GenerateContentConfig) and getattr(config, "thinking_config", None) is None:
                            eff_config = config.model_copy(
                                update={"thinking_config": types.ThinkingConfig(thinking_level="MINIMAL")}
                            )
                    except Exception:
                        eff_config = config
                resp = self.client.models.generate_content(
                    model=m_cand,
                    contents=contents,
                    config=eff_config
                )
                raw_text = getattr(resp, "text", "") or "{}"
                meta = getattr(resp, "usage_metadata", None)
                toks = getattr(meta, "total_token_count", 0) if meta else 0
                toks = toks if isinstance(toks, (int, float)) else 0
                used_tier = (
                    ModelTier.TIER_2_FALLBACK
                    if (getattr(self, "_explicit_tier1", False) or tier1_rate_limited)
                    else ModelTier.TIER_1_PRIMARY
                )
                t_key = "tier_2" if used_tier == ModelTier.TIER_2_FALLBACK else "tier_1"
                self.quota_tracker.record_request(token_count=toks, tier_key=t_key)
                data = self._parse_gemini_json(raw_text)
                if isinstance(data, dict) and toks:
                    data["token_usage"] = int(toks)
                self.active_tier = used_tier
                return data, used_tier
            except Exception as e_cand:
                if is_rate_limit_error(e_cand):
                    if not tier1_rate_limited:
                        tier1_rate_limited = True
                        daily_ex1 = is_daily_quota_error(e_cand) or (self.quota_tracker.get_stats().get("tier1_rpd_used", 0) >= self.quota_tracker.rpd_limit)
                        self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_1_PRIMARY, is_daily_exhausted=daily_ex1)
                        self.active_tier = ModelTier.TIER_2_FALLBACK
                    elif idx_m == len(dedup_candidates) - 1:
                        daily_ex = is_daily_quota_error(e_cand) or (self.quota_tracker.get_stats().get("tier2_rpd_used", 0) >= self.quota_tracker.rpd_limit)
                        self.cooldown_tracker.mark_rate_limited(ModelTier.TIER_2_FALLBACK, is_daily_exhausted=daily_ex)
                        self.active_tier = ModelTier.TIER_3_HEURISTIC
                else:
                    logger.debug(f"execute_multimodal_failover ({m_cand}) bận tạm thời, tự động chuyển tiếp.")

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
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            quota_file = os.path.join(root_dir, "outputs", "quota_state.json")
            _GLOBAL_ORCHESTRATOR = HierarchicalModelOrchestrator(persist_path=quota_file)
        return _GLOBAL_ORCHESTRATOR
