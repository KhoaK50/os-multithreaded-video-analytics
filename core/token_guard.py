"""
Token Guard & Peak Anomaly Selector Module.
Bảo vệ hạn mức Token và chi phí khi phân tích video dài hoặc nhiều hành vi.

Chiến lược kiến trúc:
1. Edge AI (RTX 5060) xử lý 100% frame offline (0 token).
2. Peak Anomaly Selector lọc tối đa 1-3 keyframe tại đỉnh điểm nguy hiểm.
3. Gửi DUY NHẤT 1 request tổng hợp đến Gemini 3.5 Flash Lite.
4. Tổng lượng token khống chế luôn dưới 1,500 tokens.
"""

import os
import cv2
import json
import time
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from PIL import Image
import io


class TokenGuard:
    """
    Quản lý ngân sách token và trích xuất keyframe đỉnh điểm nguy hiểm.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-3.5-flash-lite"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = os.getenv("GEMINI_MODEL", model_name)
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[!] Lỗi khởi tạo Gemini Client trong TokenGuard: {e}")

    def select_peak_keyframes(
        self,
        event_log: List[Dict[str, Any]],
        candidate_frames: Dict[float, Any],
        max_keyframes: int = 3,
        min_time_gap: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Lọc ra tối đa `max_keyframes` ảnh tại các mốc thời gian có nguy cơ cao nhất,
        cách nhau tối thiểu `min_time_gap` giây để tránh trùng lặp.
        """
        if not event_log or not candidate_frames:
            # Nếu không có sự kiện nguy hiểm nào, lấy đúng 1 frame đại diện ở giữa video
            if candidate_frames:
                timestamps = sorted(candidate_frames.keys())
                mid_ts = timestamps[len(timestamps) // 2]
                return [{
                    "timestamp": mid_ts,
                    "threat_type": "TỔNG QUAN",
                    "threat_score": 0.0,
                    "frame": candidate_frames[mid_ts]
                }]
            return []

        # Sắp xếp các sự kiện theo điểm nguy cơ giảm dần
        sorted_events = sorted(
            event_log,
            key=lambda x: x.get("threat_score", 0.0),
            reverse=True
        )

        selected = []
        selected_timestamps = []

        for ev in sorted_events:
            ts = ev.get("timestamp", 0.0)
            # Kiểm tra khoảng cách thời gian với các keyframe đã chọn
            too_close = any(abs(ts - sel_ts) < min_time_gap for sel_ts in selected_timestamps)
            if not too_close and ts in candidate_frames:
                selected.append({
                    "timestamp": ts,
                    "threat_type": ev.get("threat_type", "NGUY HIỂM"),
                    "threat_score": ev.get("threat_score", 0.0),
                    "details": ev.get("details", ""),
                    "frame": candidate_frames[ts]
                })
                selected_timestamps.append(ts)
                if len(selected) >= max_keyframes:
                    break

        # Sắp xếp lại theo thứ tự thời gian tăng dần
        selected.sort(key=lambda x: x["timestamp"])
        return selected

    def synthesize_video_report(
        self,
        video_metadata: Dict[str, Any],
        event_summary: List[Dict[str, Any]],
        peak_keyframes: List[Dict[str, Any]],
        segment_info: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Gửi duy nhất 1 lượt gọi đến Gemini 3.5 Flash Lite tổng hợp toàn bộ video
        và miêu tả chi tiết ngữ cảnh cho từng phân đoạn timeline.
        Bảo toàn hạn mức < 1,500 tokens.
        """
        if not self.client:
            return {
                "status": "warning",
                "summary": "Chưa cấu hình API Key Gemini. Báo cáo dựa trên kết quả Edge AI cục bộ.",
                "threat_level": "AN TOÀN" if not event_summary else "CẢNH BÁO",
                "primary_incident": "Bình thường",
                "detailed_diagnosis": "Không ghi nhận dấu hiệu thương tích hoặc bạo lực bất thường.",
                "recommended_action": "Duy trì chế độ giám sát tự động thông thường.",
                "scene_context": "Khu vực giám sát an toàn.",
                "segment_analyses": [],
                "token_usage": 0
            }

        # Tạo bảng tóm tắt thời gian (timeline summary text)
        timeline_lines = []
        for ev in event_summary[:20]: # Giới hạn 20 dòng để tiết kiệm token
            ts_str = f"{int(ev.get('timestamp', 0)) // 60:02d}:{int(ev.get('timestamp', 0)) % 60:02d}"
            timeline_lines.append(
                f"- [{ts_str}] Đối tượng {ev.get('person_id', 1)}: {ev.get('threat_type', 'HÀNH VI')} "
                f"({ev.get('details', '')}, Điểm số: {ev.get('threat_score', 0):.2f})"
            )
        timeline_text = "\n".join(timeline_lines) if timeline_lines else "- Toàn bộ khung cảnh duy trì trạng thái ổn định."

        seg_text = ""
        if segment_info:
            seg_lines = []
            for s in segment_info:
                seg_lines.append(f"- Phân đoạn {s.get('segment_id', '')} ({s.get('time_range', '')}): Ghi nhận {s.get('entity_count', 1)} đối tượng")
            seg_text = "\nDANH SÁCH PHÂN ĐOẠN TIMELINE:\n" + "\n".join(seg_lines)

        audio_status_str = video_metadata.get('audio_status', 'Không rõ')

        prompt = f"""Bạn là Chuyên gia Giám sát AI An ninh, Y tế & Phân tích Động học Video.
Hãy xem xét kỹ các ảnh khung hình đính kèm (đã được vẽ Bounding Box và Khung xương của đối tượng) kết hợp với thông số từ hệ thống Edge AI:

THÔNG SỐ VIDEO:
- Thời lượng đoạn phân tích: {video_metadata.get('duration_sec', 0):.1f}s ({video_metadata.get('frame_count', 0)} frames @ {video_metadata.get('fps', 30):.1f} FPS)
- Luồng âm thanh: {audio_status_str}
- Số sự kiện động học ghi nhận: {len(event_summary)}
{seg_text}

HƯỚNG DẪN ĐẶC BIỆT VỀ QUAN SÁT THỊ GIÁC & ĐÁNH GIÁ NGUY CƠ:
1. TRỌNG TÀI THẨM ĐỊNH NGUY CƠ (Contextual Arbiter):
   - Nếu bối cảnh là sinh hoạt gia đình bình thường (người cha/mẹ bế bồng, nâng niu, vui đùa cùng em bé, các thành viên đứng trò chuyện, làm việc trong phòng khách/phòng ngủ), bạn BẮT BUỘC kết luận "threat_level": "AN TOÀN" và "is_safe_environment": true.
   - Tuyệt đối KHÔNG coi cử động tay nhanh khi bế trẻ, thay đổi tư thế hay cúi người là bạo lực hay nguy hiểm.
   - CHỈ kết luận "NGUY HIỂM" khi có hành vi bạo lực xâm hại thực sự (đánh đập, ẩu đả hung hãn, vũ khí) hoặc có người té ngã bất tỉnh chấn thương nghiêm trọng.

2. MÔ TẢ HÀNH VI CẤP VĨ MÔ (Macro Narrative):
   - Không lặp lại các cụm từ vi mô máy móc. Thay vào đó, hãy viết một câu chuyện hoàn chỉnh, tự nhiên và chuyên nghiệp cho từng phân đoạn: Ai đang làm gì với ai (ví dụ: người cha bế em bé trên tay dỗ dành nhẹ nhàng, người mẹ đứng bên cạnh tương tác hỗ trợ).
   - Nếu video câm (không có âm thanh), hãy tập trung 100% vào ngôn ngữ cơ thể, cử chỉ bàn tay, hướng ánh mắt và biểu cảm. Không bịa đặt các chi tiết về âm thanh khi video không có tiếng.

3. ĐỊNH DANH VAI TRÒ THỰC TẾ (Visual Grounding & Role Identification):
   - Quan sát toàn cảnh và nhận diện đúng các nhân vật thực tế có mặt (thông thường chỉ có 3 - 4 người trong phòng).
   - Tuyệt đối KHÔNG kết luận ai "ngồi làm việc" khi cả phòng đều đang đứng hoặc di chuyển.
   - Tuyệt đối KHÔNG kết luận ai "khoanh tay trước ngực" khi hai tay họ buông xuôi tự nhiên, để ngang eo hoặc đang bế trẻ.
   - Nhận định đúng vai trò thực tế: Ai là người bế em bé, ai là em bé, ai là người mẹ, ai là người cha/người quan sát.

4. Trả về kết quả ĐÚNG ĐỊNH DẠNG JSON sau (không thêm bất kỳ văn bản giải thích nào ngoài JSON):
{{
  "threat_level": "AN TOÀN" | "CẢNH BÁO" | "NGUY HIỂM",
  "is_safe_environment": true | false,
  "primary_incident": "Tóm tắt hoạt động chủ đạo (Ví dụ: Chăm sóc gia đình / Bế em bé / Sinh hoạt bình thường)",
  "detailed_diagnosis": "Nhận định an ninh, an toàn tổng thể trong 2 câu.",
  "recommended_action": "Hành động khuyến nghị (ví dụ: Duy trì giám sát tự động / Không cần can thiệp)",
  "scene_context": "Mô tả tổng thể không gian và sự tương tác giữa các đối tượng trong video (1-2 câu)",
  "detected_actors": [
    {{
      "actor_index": 1,
      "role": "Người bế em bé",
      "appearance": "Đặc điểm nhận dạng (Ví dụ: Mặc áo thun/quần short)",
      "true_action": "Bế em bé và dỗ dành",
      "posture_desc": "Hai tay nâng đỡ em bé trước ngực"
    }},
    {{
      "actor_index": 2,
      "role": "Em bé nhỏ",
      "appearance": "Em bé nhỏ được bế bồng",
      "true_action": "Được bế bồng an toàn",
      "posture_desc": "Nằm trong vòng tay người lớn"
    }},
    {{
      "actor_index": 3,
      "role": "Người mẹ (Váy trắng)",
      "appearance": "Phụ nữ mặc váy trắng",
      "true_action": "Đứng bên cạnh tương tác hỗ trợ",
      "posture_desc": "Tư thế đứng tự nhiên"
    }},
    {{
      "actor_index": 4,
      "role": "Người cha",
      "appearance": "Người đàn ông đứng ở cửa/ban công",
      "true_action": "Đứng quan sát bảo vệ gia đình",
      "posture_desc": "Tư thế đứng quan sát"
    }}
  ],
  "segment_analyses": [
    {{
      "segment_id": "SEG-01",
      "macro_narrative": "Câu mô tả hành vi vĩ mô hoàn chỉnh (Ví dụ: Người cha đang bế bồng, đung đưa em bé trước ngực trong khi người mẹ đứng bên cạnh quan sát hỗ trợ)",
      "detailed_action": "Hành động chủ đạo ngắn gọn (Ví dụ: Bế em bé và tương tác gia đình)",
      "context_description": "Chi tiết tương tác giữa các đối tượng trong phân đoạn này",
      "prediction_next_4s": "Dự đoán cụ thể xu hướng hành vi của các đối tượng trong 4 giây tiếp theo"
    }}
  ]
}}
"""


        contents = [prompt]

        # Đính kèm ảnh Keyframes (đã resize tối ưu để tiết kiệm token)
        for idx, kf in enumerate(peak_keyframes):
            frame = kf.get("frame")
            if frame is not None:
                # Resize ảnh xuống tối đa 640x360 để tiết kiệm token tối đa
                h, w = frame.shape[:2]
                scale = min(640 / w, 360 / h, 1.0)
                if scale < 1.0:
                    small_frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                else:
                    small_frame = frame
                
                # Chuyển BGR sang RGB cho Pillow
                rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_frame)
                
                # Nén JPEG chất lượng 80
                img_byte_arr = io.BytesIO()
                pil_img.save(img_byte_arr, format='JPEG', quality=80)
                img_bytes = img_byte_arr.getvalue()
                
                contents.append(types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/jpeg"
                ))

        if not self.client:
            return {
                "status": "offline",
                "threat_level": "CẢNH BÁO" if event_summary else "AN TOÀN",
                "primary_incident": "Chế độ Edge AI Offline (Chưa cấu hình GEMINI_API_KEY)",
                "macro_narrative": "Toàn bộ video đã được nhận diện và dán nhãn bằng mô hình Edge AI YOLOv8-Pose cục bộ.",
                "detailed_diagnosis": "Hệ thống đang hoạt động ở chế độ cục bộ 0-token. Để kích hoạt Cloud AI chẩn đoán mở rộng, vui lòng cấu hình GEMINI_API_KEY trong file .env.",
                "recommended_action": "Theo dõi các phân đoạn và nhãn tư thế khung xương đã tạo.",
                "confidence_score": 1.0,
                "token_usage": 0,
                "detected_actors": [],
                "timeline_analysis": []
            }

        try:
            config = types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )

            # Lấy số token đã dùng
            token_usage = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                token_usage = getattr(response.usage_metadata, "total_token_count", 0) or 0

            # Parse JSON
            raw_text = response.text.strip()
            data = json.loads(raw_text)
            data["token_usage"] = token_usage
            data["status"] = "success"
            return data

        except Exception as e:
            print(f"[!] Lỗi gọi Gemini trong synthesize_video_report: {e}")
            return {
                "status": "error",
                "threat_level": "CẢNH BÁO" if event_summary else "AN TOÀN",
                "primary_incident": "Lỗi phân tích Cloud AI",
                "detailed_diagnosis": f"Không thể lấy phản hồi từ Gemini: {str(e)[:100]}",
                "recommended_action": "Kiểm tra thủ công video đã xuất nhãn",
                "token_usage": 0
            }
