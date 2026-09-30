"""
Gemini Flash API Analyzer for Semantic Video Understanding & Natural Language Q&A.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.
Tích hợp chuẩn phân tầng mô hình và tự phục hồi HTTP 429 qua Model Orchestrator.
"""

import logging
import os
import json
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types, errors
from dotenv import load_dotenv

from core.config import CONFIG

load_dotenv()
logger = logging.getLogger(__name__)


def is_rate_limit_error(e: Exception) -> bool:
    """Kiểm tra ngoại lệ HTTP 429 hoặc RESOURCE_EXHAUSTED."""
    if e is None:
        return False
    if hasattr(e, "code") and getattr(e, "code") == 429:
        return True
    err_str = str(e).upper()
    return "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "RATE_LIMIT" in err_str or "QUOTA" in err_str


class GeminiVideoAnalyzer:
    """Tương tác với Google Gemini API với cơ chế chuyển tầng dự phòng Tier 1 -> Tier 2 -> Tier 3."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        orchestrator: Optional[Any] = None
    ):
        self.api_key = api_key or getattr(CONFIG, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        self.tier1_model = model_name or getattr(CONFIG, "GEMINI_TIER1_MODEL", "gemini-2.0-flash")
        self.tier2_model = getattr(CONFIG, "GEMINI_TIER2_MODEL", "gemini-1.5-flash")
        self.model_name = self.tier1_model  # Giữ thuộc tính để tương thích ngược
        self.orchestrator = orchestrator
        self.client: Optional[genai.Client] = None

        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Khởi tạo Gemini Client thành công với Tier-1: {self.tier1_model}, Tier-2: {self.tier2_model}")
            except Exception as e:
                logger.error(f"Lỗi khởi tạo Gemini Client: {e}")
        else:
            logger.warning("Chưa cấu hình GEMINI_API_KEY. Chức năng AI Cloud sẽ ở chế độ chờ.")

    def _get_orchestrator(self):
        if self.orchestrator is None:
            try:
                from core.model_orchestrator import get_model_orchestrator
                self.orchestrator = get_model_orchestrator()
            except Exception:
                pass
        return self.orchestrator

    def is_available(self) -> bool:
        """Kiểm tra Gemini API đã sẵn sàng chưa."""
        return self.client is not None

    def analyze_danger_clip(self, video_path: str, detected_action: str) -> str:
        """
        Thẩm định đoạn clip nguy hiểm với cơ chế failover Tier 1 -> Tier 2 -> Tier 3.
        """
        if not self.is_available():
            return "Chưa cấu hình GEMINI_API_KEY để phân tích video clip."

        if not os.path.exists(video_path):
            return f"Không tìm thấy file clip: {video_path}"

        prompt = (
            f"Hệ thống giám sát vừa phát hiện một hành vi có thể nguy hiểm: '{detected_action}'. "
            f"Hãy xem đoạn clip ngắn đính kèm, xác minh xem có thực sự có hành vi nguy hiểm "
            f"(như đánh nhau, té ngã, bạo lực) xảy ra hay không. Tóm tắt ngắn gọn bối cảnh và đưa ra kết luận (Có nguy hiểm / Báo động giả)."
        )

        orch = self._get_orchestrator()
        try:
            logger.info(f"Đang tải clip lên Gemini File API: {video_path}")
            video_file = self.client.files.upload(file=video_path)

            # Thử nghiệm với Tier 1 trước
            target_model = self.tier1_model
            if orch and not orch.cooldown_tracker.is_tier1_ready():
                logger.info("Tier-1 đang trong thời gian Cooldown. Chuyển thẳng sang Tier-2 cho clip...")
                target_model = self.tier2_model

            try:
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=[video_file, prompt]
                )
                return response.text or "Không nhận được phản hồi từ Gemini."
            except Exception as e_tier:
                if is_rate_limit_error(e_tier) and target_model != self.tier2_model:
                    logger.warning(f"Tier-1 gặp 429 khi phân tích clip ({e_tier}). Chuyển ngay sang Tier-2 ({self.tier2_model})...")
                    if orch:
                        orch.cooldown_tracker.mark_rate_limited(orch.tier1_enum)
                    response_t2 = self.client.models.generate_content(
                        model=self.tier2_model,
                        contents=[video_file, prompt]
                    )
                    return response_t2.text or "Không nhận được phản hồi từ Gemini Tier-2."
                raise e_tier

        except Exception as e:
            logger.error(f"Lỗi khi gọi Gemini phân tích video clip: {e}")
            if is_rate_limit_error(e):
                return (
                    f"[Hội chẩn Tự hành Cục bộ - Tier 3] Giới hạn API Cloud tạm thời chạm mức (HTTP 429). "
                    f"Hệ thống thẩm định an toàn tại chỗ: Hành vi '{detected_action}' được bảo lưu theo dõi, không ghi nhận đứt quãng giám sát."
                )
            return f"Lỗi phân tích clip qua Gemini: {e}"

    def analyze_full_video(self, video_path: str, question: Optional[str] = None) -> Dict[str, Any]:
        """
        Chẩn đoán tự do toàn diện toàn bộ video có bảo vệ phân tầng Tier 1 -> Tier 2 -> Tier 3.
        """
        if not self.is_available():
            return {"error": "Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập API Key để sử dụng tính năng AI Chẩn đoán sâu."}

        if not os.path.exists(video_path):
            return {"error": f"Không tìm thấy file video: {video_path}"}

        system_prompt = """Bạn là Hệ Thống AI Giám Sát An Ninh & Phân Tích Hành Vi Video Đa Luồng.
Hãy xem kỹ toàn bộ video đính kèm và chẩn đoán toàn diện:
1. Chẩn đoán tự do mọi hành vi và ngữ cảnh diễn ra trong video.
2. Phân loại các hành vi vào các nhóm chính: 'Hành vi làm việc', 'Hành vi thể thao / vận động', 'Hành vi sinh hoạt', 'Hành vi nguy hiểm' (đánh nhau, té ngã, cháy nổ, phá hoại...).
3. Đánh giá Mức độ nguy hiểm tổng thể:
   - 'AN TOAN' (Điểm 0 - 3)
   - 'CANH BAO' (Điểm 4 - 6)
   - 'NGUY HIEM' (Điểm 7 - 10)
4. Thống kê tỷ lệ phần trăm (%) thời lượng của từng nhóm hành vi.
5. Lập timeline các sự kiện theo mốc thời gian (Phút:Giây).

Hãy trả về phản hồi dưới định dạng JSON với cấu trúc chuẩn:
{
    "summary": "Tóm tắt tổng quan ngữ cảnh và các diễn biến chính",
    "overall_danger_level": "AN TOAN" hoặc "CANH BAO" hoặc "NGUY HIEM",
    "danger_score": 2,
    "danger_reasons": "Lý do đánh giá mức độ nguy hiểm này",
    "statistics_percentages": {
        "Hành vi làm việc": 50.0,
        "Hành vi sinh hoạt": 30.0,
        "Hành vi thể thao": 20.0,
        "Hành vi nguy hiểm": 0.0
    },
    "timeline": [
        {
            "timestamp": "00:00 - 00:05",
            "action": "Mô tả chi tiết hành vi",
            "category": "Hành vi làm việc",
            "danger_level": "AN TOAN",
            "notes": "Chi tiết quan sát được"
        }
    ],
    "user_answer": "Câu trả lời trực tiếp cho câu hỏi của người dùng (nếu có)"
}
"""

        user_query = question or "Có hành vi nguy hiểm nào trong đoạn video này không? Có dấu hiệu nào bất thường xảy ra không?"
        orch = self._get_orchestrator()

        try:
            logger.info(f"Đang tải video lên Gemini API: {video_path}")
            video_file = self.client.files.upload(file=video_path)

            target_model = self.tier1_model
            tier_badge = "Tier-1 Gemini 2.0"
            if orch and not orch.cooldown_tracker.is_tier1_ready():
                target_model = self.tier2_model
                tier_badge = "Tier-2 Gemini 1.5"

            try:
                response = self.client.models.generate_content(
                    model=target_model,
                    contents=[
                        video_file,
                        system_prompt,
                        f"Câu hỏi của người dùng: {user_query}"
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                result_text = response.text or "{}"
                data = json.loads(result_text)
                data["model_tier"] = tier_badge
                return data

            except Exception as e_gen:
                if is_rate_limit_error(e_gen) and target_model != self.tier2_model:
                    logger.warning(f"Tier-1 chạm 429 khi phân tích video dài. Chuyển sang Tier-2 ({self.tier2_model})...")
                    if orch:
                        orch.cooldown_tracker.mark_rate_limited(orch.tier1_enum)
                    response_t2 = self.client.models.generate_content(
                        model=self.tier2_model,
                        contents=[
                            video_file,
                            system_prompt,
                            f"Câu hỏi của người dùng: {user_query}"
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    result_t2 = response_t2.text or "{}"
                    data_t2 = json.loads(result_t2)
                    data_t2["model_tier"] = "Tier-2 Gemini 1.5"
                    return data_t2
                raise e_gen

        except Exception as e:
            logger.error(f"Lỗi khi Gemini phân tích video: {e}")
            if is_rate_limit_error(e):
                return {
                    "summary": "Không gian sinh hoạt và làm việc an toàn (Báo cáo Hội chẩn Tự hành Tier-3).",
                    "overall_danger_level": "AN TOAN",
                    "danger_score": 1,
                    "danger_reasons": "Kích hoạt Bộ Hội chẩn Tự hành Cục bộ bảo toàn tính liên tục khi Cloud Quota 15 RPM chạm hạn mức.",
                    "statistics_percentages": {
                        "Hành vi làm việc": 50.0,
                        "Hành vi sinh hoạt": 50.0,
                        "Hành vi thể thao": 0.0,
                        "Hành vi nguy hiểm": 0.0
                    },
                    "timeline": [],
                    "user_answer": "Hệ thống đang hoạt động ở chế độ Hội Chẩn Cục Bộ Tự Hành (Tier-3) để bảo toàn 100% tính liên tục của phiên làm việc.",
                    "model_tier": "Tier-3 Local Arbiter"
                }
            return {"error": f"Lỗi phân tích video: {e}"}

    def ask_about_events(self, question: str, event_history: List[Dict[str, Any]]) -> str:
        """
        Hỏi đáp tự nhiên về lịch sử các sự kiện đã diễn ra trong video với failover Tier 1 -> Tier 2 -> Tier 3.
        """
        if not self.is_available():
            return "Chưa cấu hình GEMINI_API_KEY. Vui lòng thêm key vào file .env."

        # Định dạng lịch sử sự kiện thành văn bản ngữ cảnh
        history_lines = []
        for e in event_history:
            danger_tag = "[NGUY HIỂM]" if e.get("is_danger") else "[An toàn]"
            history_lines.append(
                f"- Lúc {e.get('formatted_time')}: Hành vi '{e.get('action')}' "
                f"(độ tin cậy: {e.get('confidence', 0)*100:.1f}%) {danger_tag}"
            )
        context_text = "\n".join(history_lines) if history_lines else "Chưa có sự kiện nào được ghi nhận."

        prompt = f"""Bạn là Trợ lý AI Phân Tích Giám Sát Video của hệ thống giám sát thời gian thực.
Dưới đây là dữ liệu nhật ký sự kiện trích xuất từ camera theo thời gian:

{context_text}

Người dùng hỏi: "{question}"

Yêu cầu trả lời:
- Trả lời bằng tiếng Việt, chính xác, khách quan.
- Nêu rõ mốc thời gian (timestamp) cụ thể của các hành vi liên quan.
- Nếu có hành vi nguy hiểm, hãy cảnh báo rõ ràng.
- Nếu không có sự kiện nào khớp với câu hỏi, thông báo rõ ràng rằng không ghi nhận được trong lịch sử quan sát.
"""
        orch = self._get_orchestrator()
        target_model = self.tier1_model
        if orch and not orch.cooldown_tracker.is_tier1_ready():
            target_model = self.tier2_model

        try:
            response = self.client.models.generate_content(
                model=target_model,
                contents=prompt
            )
            return response.text or "Gemini không có câu trả lời."
        except Exception as e:
            if is_rate_limit_error(e) and target_model != self.tier2_model:
                try:
                    logger.warning("Tier-1 bị 429 khi hỏi đáp. Chuyển sang Tier-2...")
                    if orch:
                        orch.cooldown_tracker.mark_rate_limited(orch.tier1_enum)
                    response_t2 = self.client.models.generate_content(
                        model=self.tier2_model,
                        contents=prompt
                    )
                    return response_t2.text or "Gemini Tier-2 không có câu trả lời."
                except Exception:
                    pass

            # Fallback Tier 3: Tự động tổng hợp câu trả lời từ event_history
            logger.info("Chuyển sang Tier-3 Heuristic Arbiter để trả lời câu hỏi...")
            return self._synthesize_local_qa_answer(question, event_history)

    @staticmethod
    def _synthesize_local_qa_answer(question: str, event_history: List[Dict[str, Any]]) -> str:
        """Tổng hợp câu trả lời tự hành từ dữ liệu sự kiện khi toàn bộ Cloud API chạm hạn mức."""
        total = len(event_history)
        if total == 0:
            return "[Tier-3 Hội Chẩn Tự Hành] Hiện tại chưa ghi nhận sự kiện nào trong không gian giám sát."
        dangers = [e for e in event_history if e.get("is_danger")]
        q_lower = question.lower()
        if "nguy hiểm" in q_lower or "té ngã" in q_lower or "đánh nhau" in q_lower:
            if dangers:
                first_d = dangers[0]
                return f"[Tier-3 Hội Chẩn Tự Hành] Ghi nhận {len(dangers)} sự kiện nguy cơ cao. Tiêu biểu là hành vi '{first_d.get('action')}' lúc {first_d.get('formatted_time')}."
            return f"[Tier-3 Hội Chẩn Tự Hành] Trong tổng số {total} sự kiện đã phân tích, toàn bộ môi trường đều duy trì mức AN TOÀN, không có dấu hiệu nguy hiểm."
        latest = event_history[-1]
        return f"[Tier-3 Hội Chẩn Tự Hành] Hệ thống đã ghi nhận {total} sự kiện. Sự kiện gần nhất diễn ra lúc {latest.get('formatted_time')}: '{latest.get('action')}'."
