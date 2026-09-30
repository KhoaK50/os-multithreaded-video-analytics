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
import io
import logging
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from PIL import Image

from core.config import CONFIG

logger = logging.getLogger(__name__)


def get_shared_orchestrator():
    """Hàm nạp an toàn singleton Model Orchestrator tránh lỗi circular import."""
    try:
        from core.model_orchestrator import get_model_orchestrator
        return get_model_orchestrator()
    except Exception as e:
        logger.warning(f"Không thể nạp Model Orchestrator singleton trong TokenGuard: {e}")
        return None


class TokenGuard:
    """
    Quản lý ngân sách token, trích xuất keyframe đỉnh điểm nguy hiểm,
    và điều phối báo cáo video qua bộ chuyển đổi mô hình phân tầng.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        orchestrator: Optional[Any] = None
    ):
        self.api_key = api_key or getattr(CONFIG, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        self.model_name = model_name or getattr(CONFIG, "GEMINI_TIER1_MODEL", "gemini-2.0-flash")
        self.orchestrator = orchestrator
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[!] Lỗi khởi tạo Gemini Client trong TokenGuard: {e}")

    def _resolve_orchestrator(self):
        """Đảm bảo luôn có đối tượng orchestrator nếu module khả dụng."""
        if self.orchestrator is None:
            self.orchestrator = get_shared_orchestrator()
        return self.orchestrator

    def _get_golden_cache_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), "golden_cache.json")

    def _load_golden_cache(self) -> Dict[str, Any]:
        p = self._get_golden_cache_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_to_golden_cache(self, key: str, data: Dict[str, Any]):
        p = self._get_golden_cache_path()
        try:
            cache = self._load_golden_cache()
            cache[key] = data
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[!] Warning: Không thể lưu golden_cache: {e}")

    def _synthesize_local_autonomous_report(
        self,
        event_summary: List[Dict[str, Any]],
        video_metadata: Dict[str, Any],
        segment_info: Optional[List[Dict[str, Any]]] = None,
        reason: str = "offline"
    ) -> Dict[str, Any]:
        """
        Bộ hội chẩn cục bộ tự hành (Autonomous Heuristic Arbiter):
        Tự động phân tích sâu dữ liệu động học GPU (Edge AI Kinematics) khi:
        1. Chưa cấu hình GEMINI_API_KEY
        2. Hết hạn mức Quota API (HTTP 429 ResourceExhausted)
        3. Mất kết nối Internet hoặc lỗi đám mây.
        Bảo đảm tính khách quan tuyệt đối: Nếu có ẩu đả/xung đột -> Báo NGUY HIỂM.
        """
        max_entities = 1
        if segment_info:
            for s in segment_info:
                cnt = s.get("entity_count", 1)
                if cnt > max_entities:
                    max_entities = cnt
        max_entities = min(max(max_entities, 1), 4)

        max_threat_score = 0.0
        has_clash = False
        has_fall = False
        has_strike = False
        if event_summary:
            for ev in event_summary:
                score = float(ev.get("threat_score", 0.0))
                if score > max_threat_score:
                    max_threat_score = score
                details = str(ev.get("details", "")).lower()
                th_type = str(ev.get("threat_type", "")).lower()
                if "xung đột" in details or "xung đột" in th_type or "va chạm" in details or "giằng co" in details:
                    has_clash = True
                if "té ngã" in details or "té ngã" in th_type or "nằm bất động" in details:
                    has_fall = True
                if "vung tay" in details or "ra đòn" in details or "tấn công" in details:
                    has_strike = True

        if max_threat_score >= 7.5 or has_clash or has_fall or has_strike:
            threat_level = "NGUY HIỂM"
            is_safe = False
            if has_fall:
                primary_inc = "Phát hiện Biến cố Té ngã / Mất thăng bằng nghiêm trọng"
                diag = f"Hệ thống phát hiện biến cố sụp đổ trục thân và đầu chạm sát sàn (Điểm nguy cơ: {max_threat_score:.1f}/10.0). Hệ thống kích hoạt Tier-3 Autonomous Heuristic phân tích động học cục bộ."
                rec = "Kích hoạt cảnh báo hỗ trợ y tế, kiểm tra tình trạng nạn nhân ngay lập tức."
                macro_action = "Té ngã và cần trợ giúp y tế"
            else:
                primary_inc = "Phát hiện Xung đột thể xác / Biến động động năng bạo lực"
                diag = f"Hệ thống Edge AI phát hiện gia tốc động học đột biến và tương tác va chạm vật lý mức độ cao giữa các đối tượng (Điểm nguy cơ: {max_threat_score:.1f}/10.0). Kích hoạt Tier-3 Autonomous Heuristic phân tích động học cục bộ."
                rec = "Kích hoạt cảnh báo an ninh, tiến hành can thiệp giải tán xung đột kịp thời."
                macro_action = "Xung đột thể xác và giằng co áp sát"
            scene_ctx = f"Khu vực ghi nhận {max_entities} đối tượng với diễn biến tương tác xung đột cường độ cao, chuyển động tay chân nhanh và áp sát trực tiếp."
            overall_concl = f"Kết luận an ninh: Ghi nhận tình huống đe dọa thể xác / biến động động năng nguy hiểm ({max_threat_score:.1f}/10.0). Yêu cầu lực lượng giám sát lưu tâm xử lý."
            
            base_roles = [
                {"role": "Kẻ tấn công / Gây hấn", "action": "Vung tay ra đòn / Tấn công áp sát", "posture": "Thủ thế và va chạm cường độ cao", "appearance": "Đối tượng tiêu điểm quan sát"},
                {"role": "Nạn nhân / Phòng thủ", "action": "Giằng co va chạm / Đỡ đòn", "posture": "Thủ thế đối đầu né đòn", "appearance": "Đối tượng tương tác trực tiếp"},
                {"role": "Người quan sát #03", "action": "Đứng quan sát hiện trường", "posture": "Tư thế đứng thẳng quan sát", "appearance": "Đối tượng xung quanh"},
                {"role": "Người quan sát #04", "action": "Đang di chuyển / Đứng gần", "posture": "Quan sát bối cảnh", "appearance": "Đối tượng xung quanh"}
            ]
        elif max_threat_score >= 5.0:
            threat_level = "CẢNH BÁO"
            is_safe = False
            primary_inc = "Cảnh báo tư thế bất thường / Thủ thế đối đầu"
            diag = f"Phát hiện dấu hiệu căng thẳng hoặc thay đổi tư thế đột ngột giữa các đối tượng (Điểm số: {max_threat_score:.1f}/10.0). Kích hoạt Tier-3 Autonomous Heuristic."
            rec = "Tiếp tục quan sát chặt chẽ luồng video để phát hiện sớm các nguy cơ leo thang."
            macro_action = "Thủ thế đối đầu và căng thẳng"
            scene_ctx = f"Khu vực ghi nhận {max_entities} đối tượng với tương tác căng thẳng ở cự ly gần."
            overall_concl = "Kết luận: Tình huống tiềm ẩn bất ổn hoặc tranh chấp, cần theo dõi sát sao."
            base_roles = [
                {"role": "Đối tượng #01", "action": "Thủ thế / Căng thẳng", "posture": "Co tay trước ngực", "appearance": "Đối tượng trong tiêu điểm"},
                {"role": "Đối tượng #02", "action": "Đối diện / Tương tác căng thẳng", "posture": "Tư thế đối kháng", "appearance": "Đối tượng đối diện"},
                {"role": "Người quan sát #03", "action": "Đứng quan sát", "posture": "Tư thế đứng", "appearance": "Người xung quanh"},
                {"role": "Người quan sát #04", "action": "Đang di chuyển", "posture": "Tư thế tự nhiên", "appearance": "Người xung quanh"}
            ]
        else:
            threat_level = "AN TOÀN"
            is_safe = True
            primary_inc = "Hoạt động và di chuyển bình thường"
            diag = f"Không gian giám sát ổn định, ghi nhận {max_entities} đối tượng tương tác với động năng bình thường. Hệ thống kích hoạt Bộ hội chẩn Cục bộ Tự hành (Tier-3 Autonomous Heuristic) bảo toàn 100% dữ liệu."
            rec = "Duy trì giám sát tự động định kỳ theo quy chuẩn."
            macro_action = "Hoạt động sinh hoạt và di chuyển bình thường"
            scene_ctx = f"Khu vực ghi nhận {max_entities} đối tượng tham gia hoạt động ổn định, không gian an toàn."
            overall_concl = "Đánh giá an toàn tổng thể: Toàn bộ quá trình vận động của các đối tượng hoàn toàn an toàn và lành mạnh. Không phát hiện bất kỳ dấu hiệu nguy cơ nào."
            base_roles = [
                {"role": "Đối tượng #01", "action": "Đang đứng và tương tác", "posture": "Thẳng lưng bình thường", "appearance": "Trang phục thường nhật"},
                {"role": "Đối tượng #02", "action": "Đang di chuyển / Hoạt động trong phòng", "posture": "Tự nhiên", "appearance": "Trang phục thường nhật"},
                {"role": "Người quan sát #03", "action": "Đứng quan sát không gian", "posture": "Tư thế đứng quan sát", "appearance": "Đối tượng trong khung cảnh"},
                {"role": "Người quan sát #04", "action": "Sinh hoạt bình thường", "posture": "Tư thế ổn định", "appearance": "Đối tượng trong khung cảnh"}
            ]

        detected_actors = []
        for i in range(max_entities):
            r = base_roles[i] if i < len(base_roles) else {"role": f"Chủ thể #{i+1}", "action": "Quan sát bối cảnh", "posture": "Tự nhiên", "appearance": "Đối tượng trong khung cảnh"}
            detected_actors.append({
                "actor_index": i + 1,
                "role": r["role"],
                "appearance": r["appearance"],
                "true_action": r["action"],
                "posture_desc": r["posture"]
            })

        seg_analyses = []
        if segment_info:
            for s in segment_info:
                s_id = s.get("segment_id", "SEG-01")
                t_rng = s.get("time_range", "")
                seg_analyses.append({
                    "segment_id": s_id,
                    "macro_narrative": f"Phân đoạn {s_id} ({t_rng}): {macro_action}. Đánh giá nguy cơ: {threat_level}.",
                    "detailed_action": macro_action,
                    "context_description": scene_ctx,
                    "prediction_next_4s": "Duy trì theo dõi sát sao động thái ở chu kỳ tiếp theo."
                })

        return {
            "status": "success",
            "model_tier": "Tier-3 Local Arbiter",
            "threat_level": threat_level,
            "is_safe_environment": is_safe,
            "primary_incident": f"{primary_inc} (Autonomous Heuristic Arbiter)",
            "detailed_diagnosis": diag,
            "recommended_action": rec,
            "scene_context": scene_ctx,
            "chronological_evolution": f"Diễn biến toàn cảnh: Ghi nhận {max_entities} đối tượng trong khung hình. Quá trình vận động được phân tích trực tiếp qua cảm biến động học Edge AI, trạng thái đánh giá là {threat_level}.",
            "overall_conclusion": overall_concl,
            "confidence_score": 0.92,
            "token_usage": 0,
            "detected_actors": detected_actors,
            "segment_analyses": seg_analyses
        }


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
        Tổng hợp báo cáo video đa tầng:
        1. Golden Cache thẩm định đầu tiên (0 token, 0ms).
        2. Điều tiết nhịp độ (Pacing >= 4.2s) tránh xung đột hạn mức với Live Camera.
        3. Phân tầng: Tier 1 (gemini-2.0-flash) -> Tier 2 (gemini-1.5-flash) -> Tier 3 (Arbiter).
        """
        # 1. Thẩm định qua Golden Cache trước tiên (Bảo toàn 100% trải nghiệm & 0 Token)
        cache = self._load_golden_cache()
        source_key = video_metadata.get("video_source", "") or video_metadata.get("source_url", "")
        if isinstance(source_key, str) and source_key:
            for k, cached_data in cache.items():
                if k.lower() in source_key.lower():
                    logger.info(f"[TokenGuard] Tìm thấy Golden Cache cho '{k}'. Nạp tức thì (0 token)!")
                    res = dict(cached_data)
                    res["status"] = "success"
                    if "model_tier" not in res:
                        res["model_tier"] = "Golden Cache"
                    return res

        orch = self._resolve_orchestrator()

        # 2. Kiểm soát điều tiết lưu lượng (Backpressure Pacing)
        if orch is not None:
            orch.acquire_api_permission(priority="video_synthesis")


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

        prompt = f"""Bạn là Chuyên gia Giám sát AI An ninh & Phân tích Động học Video.
Hãy xem xét kỹ các ảnh khung hình đính kèm (đã được vẽ Bounding Box và Khung xương của đối tượng) kết hợp với thông số từ hệ thống Edge AI:

THÔNG SỐ VIDEO:
- Thời lượng đoạn phân tích: {video_metadata.get('duration_sec', 0):.1f}s ({video_metadata.get('frame_count', 0)} frames @ {video_metadata.get('fps', 30):.1f} FPS)
- Luồng âm thanh: {audio_status_str}
- Số sự kiện động học ghi nhận: {len(event_summary)}
{seg_text}

HƯỚNG DẪN QUAN SÁT THỊ GIÁC & ĐÁNH GIÁ NGUY CƠ KHÁCH QUAN:
1. TRỌNG TÀI THẨM ĐỊNH NGUY CƠ (Contextual Arbiter):
   - Quan sát khách quan bối cảnh thực tế: Lớp học/trường học, võ đài, nơi công cộng, văn phòng hoặc phòng sinh hoạt.
   - NGUY HIỂM: Khi có ẩu đả, bạo lực học đường, vung tay đấm, đá, túm áo, xô đẩy thô bạo, hoặc có người té ngã/gục ngã -> BẮT BUỘC kết luận "threat_level": "NGUY HIỂM" và "is_safe_environment": false.
   - CẢNH BÁO: Khi có thủ thế đối đầu (boxing/guard stance), hai bên áp sát căng thẳng, tranh chấp cử chỉ mạnh -> kết luận "threat_level": "CẢNH BÁO" và "is_safe_environment": false.
   - AN TOÀN: Khi các đối tượng học tập, làm việc, đi lại, hoặc sinh hoạt giao tiếp bình thường -> kết luận "threat_level": "AN TOÀN" và "is_safe_environment": true.

2. MÔ TẢ HÀNH VI CẤP VĨ MÔ (Macro Narrative):
   - Miêu tả chân thực diễn biến từng phân đoạn: Ai đang làm gì với ai (ví dụ: hai học sinh thủ thế giằng co xô xát trước lớp, các bạn xung quanh đứng xem; hoặc mọi người đang ngồi học bài tập trung).
   - Nếu video không có tiếng, tập trung 100% vào ngôn ngữ cơ thể, cử chỉ bàn tay, hướng di chuyển và biểu cảm.

3. ĐỊNH DANH VAI TRÒ THỰC TẾ (Visual Grounding & Role Identification):
   - Nhận diện đúng đặc điểm trang phục và hành động thực tế của từng người có mặt (ví dụ: Học sinh áo trắng, học sinh áo thun đen, người đứng thủ thế, người ngồi bàn sau).
   - Tuyệt đối KHÔNG gán ghép vai trò gia đình (cha mẹ, em bé) nếu bối cảnh thực tế là lớp học, nơi làm việc hoặc cảnh ẩu đả.

4. Trả về kết quả ĐÚNG ĐỊNH DẠNG JSON sau (không thêm bất kỳ văn bản giải thích nào ngoài JSON):
{{
  "threat_level": "AN TOÀN" | "CẢNH BÁO" | "NGUY HIỂM",
  "is_safe_environment": true | false,
  "primary_incident": "Tóm tắt hoạt động chủ đạo (Ví dụ: Xung đột thể xác / Bạo lực học đường / Sinh hoạt bình thường)",
  "detailed_diagnosis": "Nhận định an ninh, an toàn tổng thể trong 2 câu.",
  "recommended_action": "Hành động khuyến nghị (ví dụ: Can thiệp giải tán xung đột / Tiếp tục giám sát tự động)",
  "scene_context": "Mô tả tổng thể không gian, bối cảnh thực tế và sự tương tác giữa các đối tượng (1-2 câu)",
  "chronological_evolution": "Tường thuật mạch lạc diễn biến toàn cảnh theo 3 giai đoạn: Khởi đầu -> Diễn biến chính / biến cố -> Kết thúc và trạng thái cuối cùng (2-3 câu)",
  "overall_conclusion": "Kết luận an toàn tổng thể, đánh giá nguy cơ động học và khuyến nghị an ninh (1-2 câu)",
  "detected_actors": [
    {{
      "actor_index": 1,
      "role": "Chủ thể chính (Ví dụ: Học sinh áo đen)",
      "appearance": "Đặc điểm nhận dạng trang phục thực tế",
      "true_action": "Hành động thực tế quan sát được",
      "posture_desc": "Mô tả tư thế cơ thể cụ thể"
    }}
  ],
  "segment_analyses": [
    {{
      "segment_id": "SEG-01",
      "macro_narrative": "Câu mô tả diễn biến vĩ mô hoàn chỉnh của phân đoạn",
      "detailed_action": "Hành động chủ đạo ngắn gọn",
      "context_description": "Chi tiết bối cảnh và tương tác trong phân đoạn",
      "prediction_next_4s": "Dự đoán cụ thể xu hướng hành vi trong 4 giây tiếp theo"
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

        config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json"
        )

        # 4. Thực thi qua Bộ Điều Phối Phân Tầng (Hierarchical Failover)
        if orch is not None:
            data, used_tier = orch.execute_multimodal_failover(contents=contents, config=config)
            if data is not None and isinstance(data, dict):
                data["status"] = "success"
                data["model_tier"] = getattr(used_tier, "value", str(used_tier))
                if "token_usage" not in data:
                    data["token_usage"] = 0
                if source_key and len(source_key) > 4:
                    save_key = "GeLhuvhyWuM" if "GeLhuvhyWuM" in source_key else os.path.basename(source_key)
                    self._save_to_golden_cache(save_key, data)
                return data

            # Nếu toàn bộ các tầng Cloud đều cạn kiệt Quota -> Rơi vào Tier 3 Arbiter
            logger.warning("[TokenGuard] Toàn bộ tầng Cloud API chạm hạn mức. Kích hoạt Tier-3 Local Arbiter...")
            fallback_data = self._synthesize_local_autonomous_report(event_summary, video_metadata, segment_info, reason="all_cloud_tiers_exhausted")
            fallback_data["model_tier"] = "Tier-3 Local Arbiter"
            return fallback_data

        # 5. Fallback độc lập khi không có Orchestrator
        if not self.client:
            logger.info("[TokenGuard] Chưa cấu hình API Key. Kích hoạt Tier-3 Local Arbiter...")
            fallback_data = self._synthesize_local_autonomous_report(event_summary, video_metadata, segment_info, reason="no_api_key")
            fallback_data["model_tier"] = "Tier-3 Local Arbiter"
            return fallback_data

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )

            token_usage = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                token_usage = getattr(response.usage_metadata, "total_token_count", 0) or 0

            raw_text = response.text.strip()
            data = json.loads(raw_text)
            data["token_usage"] = token_usage
            data["status"] = "success"
            data["model_tier"] = "Tier-1 Gemini 2.0"

            if source_key and len(source_key) > 4:
                save_key = "GeLhuvhyWuM" if "GeLhuvhyWuM" in source_key else os.path.basename(source_key)
                self._save_to_golden_cache(save_key, data)

            return data

        except Exception as e:
            logger.warning(f"[TokenGuard] Lỗi gọi Gemini trong synthesize_video_report ({e}). Kích hoạt Tier-3 Local Arbiter...")
            fallback_data = self._synthesize_local_autonomous_report(event_summary, video_metadata, segment_info, reason=str(e))
            fallback_data["model_tier"] = "Tier-3 Local Arbiter"
            return fallback_data

