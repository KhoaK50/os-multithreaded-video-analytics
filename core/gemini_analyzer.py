"""
Gemini Flash API Analyzer for Semantic Video Understanding & Natural Language Q&A.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Chức năng:
- Sử dụng SDK chính thức google-genai
- Thẩm định lại ngữ cảnh các clip nguy hiểm 3-5s tự động
- Hỏi đáp tự nhiên (Semantic Q&A) dựa trên dữ liệu nhật ký sự kiện hoặc video
"""

import logging
import os
from typing import Optional, List, Dict, Any
from google import genai
from dotenv import load_dotenv
load_dotenv()

from google.genai import types

logger = logging.getLogger(__name__)


class GeminiVideoAnalyzer:
    """Tương tác với Google Gemini Flash API để phân tích ngữ cảnh và hỏi đáp."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.client: Optional[genai.Client] = None

        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Khởi tạo Gemini Client thành công với model {self.model_name}")
            except Exception as e:
                logger.error(f"Lỗi khởi tạo Gemini Client: {e}")
        else:
            logger.warning("Chưa cấu hình GEMINI_API_KEY. Chức năng AI Cloud sẽ ở chế độ chờ.")

    def is_available(self) -> bool:
        """Kiểm tra Gemini API đã sẵn sàng chưa."""
        return self.client is not None

    def analyze_danger_clip(self, video_path: str, detected_action: str) -> str:
        """
        Thẩm định đoạn clip nguy hiểm được trích xuất tự động từ hệ thống.
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

        try:
            logger.info(f"Đang tải clip lên Gemini: {video_path}")
            video_file = self.client.files.upload(file=video_path)
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[video_file, prompt]
            )
            return response.text or "Không nhận được phản hồi từ Gemini."
        except Exception as e:
            logger.error(f"Lỗi khi gọi Gemini phân tích video: {e}")
            return f"Lỗi phân tích clip qua Gemini: {e}"

    def analyze_full_video(self, video_path: str, question: Optional[str] = None) -> Dict[str, Any]:
        """
        Chẩn đoán tự do toàn diện toàn bộ video:
        - Tự do phát hiện bất kỳ hành vi nào (không giới hạn nhãn)
        - Phân loại 4 nhóm lớn (Làm việc, Thể thao, Sinh hoạt, Nguy hiểm)
        - Đánh giá mức độ nguy hiểm (Thang điểm 1-10 và Safe / Caution / Danger)
        - Thống kê tỷ lệ % thời gian từng loại hành vi
        - Trả lời câu hỏi tự nhiên nếu người dùng yêu cầu
        """
        if not self.is_available():
            return {
                "error": "Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập API Key để sử dụng tính năng AI Chẩn đoán sâu."
            }

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

        try:
            logger.info(f"Đang tải video lên Gemini API: {video_path}")
            video_file = self.client.files.upload(file=video_path)

            logger.info(f"Đang yêu cầu Gemini Flash phân tích sâu video...")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    video_file,
                    system_prompt,
                    f"Câu hỏi của người dùng: {user_query}"
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            import json
            result_text = response.text or "{}"
            data = json.loads(result_text)
            return data

        except Exception as e:
            logger.error(f"Lỗi khi Gemini phân tích video: {e}")
            return {"error": f"Lỗi phân tích video: {e}"}

    def ask_about_events(self, question: str, event_history: List[Dict[str, Any]]) -> str:
        """
        Hỏi đáp tự nhiên về lịch sử các sự kiện đã diễn ra trong video.
        """
        if not self.is_available():
            return "Chưa cấu hình GEMINI_API_KEY. Vui lòng thêm key vào file .env."

        # Định dạng lịch sử sự kiện thành văn bản ngữ cảnh
        history_lines = []
        for e in event_history:
            danger_tag = "[NGUY HIỂM]" if e.get("is_danger") else "[An toàn]"
            history_lines.append(
                f"- Lúc {e.get('formatted_time')}: Hành vi '{e.get('action')}' "
                f"(độ tin cậy: {e.get('confidence')*100:.1f}%) {danger_tag}"
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
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text or "Gemini không có câu trả lời."
        except Exception as e:
            logger.error(f"Lỗi khi hỏi đáp Gemini: {e}")
            return f"Lỗi truy vấn Gemini: {e}"
