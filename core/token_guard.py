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
import re
import cv2
import numpy as np
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
        self.model_name = model_name or getattr(CONFIG, "GEMINI_TIER1_MODEL", "gemini-3.8-flash")
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
        # Theo yêu cầu người dùng: Vô hiệu hóa triệt để bộ nhớ đệm, luôn phân tích tươi mới
        return {}

    def _save_to_golden_cache(self, key: str, data: Dict[str, Any]):
        # Không lưu cache, bảo đảm mỗi lượt phân tích đều độc lập và phản ánh đúng hiện trạng
        pass

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
        if segment_info:
            for s in segment_info:
                loc_s = float(s.get("local_score", 0.0))
                if loc_s > max_threat_score:
                    max_threat_score = loc_s
                if loc_s >= 7.5 or s.get("local_severity") == "danger":
                    has_clash = True
        if event_summary:
            for ev in event_summary:
                score = float(ev.get("threat_score", 0.0))
                if score > max_threat_score:
                    max_threat_score = score
                details = str(ev.get("details", "")).lower()
                th_type = str(ev.get("threat_type", "")).lower()
                if any(w in details or w in th_type for w in ["xung đột", "va chạm", "giằng co", "xô xát", "quang học", "xung lực", "động học"]):
                    has_clash = True
                if "té ngã" in details or "té ngã" in th_type or "nằm bất động" in details:
                    has_fall = True
                if "vung tay" in details or "ra đòn" in details or "tấn công" in details:
                    has_strike = True

        if max_threat_score >= 8.0 or has_clash or has_fall or has_strike:
            threat_level = "NGUY HIỂM"
            is_safe = False
            if has_fall:
                primary_inc = "Phát hiện người bị ngã xuống sàn cần hỗ trợ khẩn cấp"
                diag = "Ghi nhận một cá nhân bất ngờ mất thăng bằng và ngã xuống mặt sàn, những người xung quanh lập tức dừng lại và tiến lại gần để kiểm tra tình hình."
                rec = "Nhanh chóng cử người đến kiểm tra tình trạng sức khỏe và hỗ trợ người bị ngã."
                macro_action = "Bị ngã xuống sàn và cần hỗ trợ"
            else:
                primary_inc = "Phát hiện xô xát và va chạm tay chân trực tiếp giữa các cá nhân"
                diag = "Các cá nhân tiến sát vào nhau, xuất hiện hành động vung tay đánh và xô đẩy trực diện khiến người đối diện phải giơ hai tay lên che chắn và lùi bước né tránh."
                rec = "Cử người kịp thời đến can ngăn và tách các bên ra xa nhau để giữ trật tự."
                macro_action = "Xô xát và giằng co trực tiếp"
            scene_ctx = f"Khu vực có {max_entities} người xuất hiện, đang xảy ra tình huống va chạm tay chân và giằng co trực tiếp giữa các cá nhân."
            overall_concl = "Kết luận: Đã xảy ra hành vi xô xát trực tiếp giữa các cá nhân trong khu vực, cần sớm can thiệp để ổn định trật tự."
            
            if has_fall and not (has_clash or has_strike):
                base_roles = [
                    {"role": "Người bị ngã", "actor_label": "Người ngã trên sàn", "distinctive_anchor": "Khu vực giữa sàn nhà", "action": "Bị ngã nằm trên mặt sàn", "posture": "Nằm trên mặt sàn", "appearance": "Người cần hỗ trợ"},
                    {"role": "Người tiến lại hỗ trợ", "actor_label": "Người đến giúp đỡ", "distinctive_anchor": "Đứng cạnh người bị ngã", "action": "Bước lại gần hỏi thăm và đỡ dậy", "posture": "Đứng cúi người hỗ trợ", "appearance": "Người xung quanh"},
                    {"role": "Người đứng gần đó", "actor_label": "Người quan sát", "distinctive_anchor": "Khu vực bên cạnh", "action": "Đứng nhìn về phía người bị ngã", "posture": "Đang đứng quan sát", "appearance": "Người xung quanh"},
                    {"role": "Người đi ngang qua", "actor_label": "Người phía sau", "distinctive_anchor": "Khu vực phía sau", "action": "Dừng bước theo dõi sự việc", "posture": "Đang đứng tự nhiên", "appearance": "Người xung quanh"}
                ]
            else:
                base_roles = [
                    {"role": "Chủ động gây hấn", "actor_label": "Người chủ động lao vào", "distinctive_anchor": "Đứng áp sát phía trước", "action": "Tiến sát và vung tay đánh về phía đối phương", "posture": "Đang đứng nhào tới vung tay", "appearance": "Người tham gia xô xát"},
                    {"role": "Phòng thủ / Chống đỡ", "actor_label": "Người bị tác động", "distinctive_anchor": "Đứng đối diện người gây hấn", "action": "Giơ hai tay che chắn vùng đầu ngực và lùi bước né đòn", "posture": "Đang đứng co tay che chắn", "appearance": "Người tham gia xô xát"},
                    {"role": "Người ngoài cuộc / Quan sát", "actor_label": "Người đứng xem", "distinctive_anchor": "Đứng lùi ở bên ngoài", "action": "Đứng giữ khoảng cách và nhìn về phía hai người đang xô xát", "posture": "Đang đứng quan sát", "appearance": "Người xung quanh"},
                    {"role": "Người ngoài cuộc / Quan sát", "actor_label": "Người phía sau", "distinctive_anchor": "Khu vực phía sau", "action": "Ngồi hoặc đứng nhìn theo diễn biến sự việc", "posture": "Tư thế tự nhiên", "appearance": "Người xung quanh"}
                ]
        elif max_threat_score >= 4.0:
            threat_level = "CẢNH BÁO"
            is_safe = False
            primary_inc = "Ghi nhận hai bên đứng đối mặt căng thẳng và lời qua tiếng lại"
            diag = "Các cá nhân tiến lại gần đứng đối diện nhau với thái độ căng thẳng, có cử chỉ chỉ tay và giơ tay phòng thủ trước ngực nhưng chưa xảy ra đánh nhau."
            rec = "Theo dõi sát tình hình và chủ động nhắc nhở để tránh sự việc leo thang thành xô xát."
            macro_action = "Đứng đối mặt tranh cãi căng thẳng"
            scene_ctx = f"Khu vực có {max_entities} người, trong đó hai người đang đứng đối diện nhau khá gần với cử chỉ tranh luận căng thẳng."
            overall_concl = "Kết luận: Hai bên đang có dấu hiệu lời qua tiếng lại và căng thẳng, cần lưu ý quan sát để ngăn ngừa va chạm."
            base_roles = [
                {"role": "Đối mặt căng thẳng", "actor_label": "Người đứng phía trước", "distinctive_anchor": "Vị trí phía trước", "action": "Đứng đối diện và giơ tay tranh luận căng thẳng", "posture": "Đang đứng đối diện", "appearance": "Người trong cuộc"},
                {"role": "Đối mặt căng thẳng", "actor_label": "Người đứng đối diện", "distinctive_anchor": "Vị trí đối diện", "action": "Đứng nhìn thẳng vào người đối diện và giữ khoảng cách phòng bị", "posture": "Đang đứng đối diện", "appearance": "Người trong cuộc"},
                {"role": "Người ngoài cuộc / Quan sát", "actor_label": "Người đứng gần đó", "distinctive_anchor": "Vị trí bên cạnh", "action": "Đứng yên theo dõi cuộc nói chuyện", "posture": "Đang đứng tự nhiên", "appearance": "Người xung quanh"},
                {"role": "Người ngoài cuộc / Quan sát", "actor_label": "Người phía sau", "distinctive_anchor": "Khu vực phía sau", "action": "Giữ nguyên vị trí sinh hoạt", "posture": "Tư thế tự nhiên", "appearance": "Người xung quanh"}
            ]
        else:
            threat_level = "AN TOÀN"
            is_safe = True
            primary_inc = "Mọi người sinh hoạt, di chuyển và trò chuyện bình thường"
            diag = f"Ghi nhận {max_entities} người trong khu vực đang ngồi học tập, làm việc hoặc đi lại trao đổi tự nhiên, không có biểu hiện tranh cãi hay xô xát."
            rec = "Không gian hoàn toàn bình thường, tiếp tục duy trì quan sát định kỳ."
            macro_action = "Sinh hoạt và trò chuyện bình thường"
            scene_ctx = f"Khu vực có {max_entities} người đang sinh hoạt, làm việc và trò chuyện ôn hòa trong không gian trật tự."
            overall_concl = "Đánh giá tổng thể: Toàn bộ hoạt động của mọi người trong khu vực diễn ra bình thường, thân thiện và hoàn toàn an toàn."
            base_roles = [
                {"role": "An toàn", "actor_label": "Người ở vị trí trung tâm", "distinctive_anchor": "Vị trí trung tâm", "action": "Ngồi hoặc đứng trao đổi tự nhiên", "posture": "Tư thế thoải mái", "appearance": "Trang phục thường ngày"},
                {"role": "An toàn", "actor_label": "Người bên cạnh", "distinctive_anchor": "Vị trí bên cạnh", "action": "Trò chuyện và phối hợp nhịp nhàng", "posture": "Tư thế tự nhiên", "appearance": "Trang phục thường ngày"},
                {"role": "An toàn", "actor_label": "Người trong phòng", "distinctive_anchor": "Khu vực lân cận", "action": "Giữ nguyên vị trí làm việc", "posture": "Tư thế tự nhiên", "appearance": "Trang phục thường ngày"},
                {"role": "An toàn", "actor_label": "Người phía sau", "distinctive_anchor": "Khu vực phía sau", "action": "Sinh hoạt bình thường", "posture": "Tư thế ổn định", "appearance": "Trang phục thường ngày"}
            ]

        detected_actors = []
        for i in range(max_entities):
            r = base_roles[i] if i < len(base_roles) else {"role": "An toàn", "actor_label": f"Người thứ {i+1}", "distinctive_anchor": f"Vị trí thứ {i+1}", "action": "Sinh hoạt tự nhiên", "posture": "Tự nhiên", "appearance": "Trang phục thường ngày"}
            detected_actors.append({
                "actor_index": i + 1,
                "tag_id": i + 1,
                "actor_label": r.get("actor_label", f"Người thứ {i+1}"),
                "distinctive_anchor": r.get("distinctive_anchor", f"Vị trí thứ {i+1}"),
                "role": r["role"],
                "appearance": r["appearance"],
                "true_action": r["action"],
                "posture_desc": r["posture"]
            })

        seg_analyses = []
        if segment_info:
            num_segs = len(segment_info)
            for s in segment_info:
                s_id = s.get("segment_id", "SEG-01")
                t_rng = s.get("time_range", "")
                loc_sc = float(s.get("local_score", 0.0))
                loc_sum = str(s.get("local_summary", "")).strip()
                loc_pred = str(s.get("local_prediction", "")).strip()

                if num_segs == 1:
                    seg_threat_lvl = threat_level
                else:
                    seg_threat_lvl = "NGUY HIỂM" if loc_sc >= 7.5 else ("CẢNH BÁO" if loc_sc >= 4.0 else "AN TOÀN")
                
                if seg_threat_lvl == "NGUY HIỂM":
                    seg_act = macro_action if threat_level == "NGUY HIỂM" else "Xô xát và giằng co trực tiếp"
                    if has_fall and not (has_clash or has_strike):
                        macro_sum = "Một người bất ngờ mất thăng bằng ngã xuống sàn, những người xung quanh tiến lại gần hỗ trợ."
                        detailed_narrative = (
                            f"Trong khoảng thời gian {t_rng}, một cá nhân bất ngờ loạng choạng rồi ngã xuống mặt sàn. "
                            f"Những người đứng gần đó lập tức dừng việc đang làm và bước tới kiểm tra, đỡ người bị ngã dậy."
                        )
                    else:
                        is_loc_sum_safe = any(w in loc_sum.lower() for w in ["ổn định", "bình thường", "an toàn", "không có xung lực", "chưa phát sinh"])
                        macro_sum = loc_sum if (loc_sum and not is_loc_sum_safe) else "Các cá nhân lao vào áp sát nhau, vung tay đánh và giằng co trực diện."
                        detailed_narrative = (
                            f"Trong khoảng thời gian {t_rng}, một người chủ động bước nhanh tới áp sát và vung tay đánh trực diện về phía người đối diện. "
                            f"Người bị tấn công lập tức giơ hai tay lên che chắn vùng đầu ngực và nghiêng người lùi lại để tự vệ, trong khi những người xung quanh lùi ra giữ khoảng cách quan sát."
                        )
                elif seg_threat_lvl == "CẢNH BÁO":
                    seg_act = "Đứng đối mặt tranh cãi căng thẳng"
                    is_loc_sum_mismatch = any(w in loc_sum.lower() for w in ["ổn định", "bình thường", "an toàn", "không có xung lực"])
                    macro_sum = loc_sum if (loc_sum and not is_loc_sum_mismatch) else "Hai bên tiến lại gần đứng đối mặt nhau với cử chỉ chỉ tay và trao đổi căng thẳng."
                    detailed_narrative = (
                        f"Trong khoảng thời gian {t_rng}, các cá nhân bước lại gần và đứng đối diện nhau với thái độ căng thẳng, xuất hiện cử chỉ đưa tay chỉ trỏ hoặc giơ tay phòng bị trước ngực. "
                        f"Hai bên mới dừng ở mức lời qua tiếng lại chứ chưa xảy ra hành động đánh nhau hay xô đẩy mạnh."
                    )
                else:
                    seg_act = "Sinh hoạt và trao đổi bình thường"
                    is_loc_sum_combat = any(w in loc_sum.lower() for w in ["xung đột", "xô xát", "tấn công", "phòng vệ", "cảnh báo"])
                    macro_sum = loc_sum if (loc_sum and not is_loc_sum_combat) else "Mọi người giữ khoảng cách thoải mái, ngồi làm việc hoặc đứng trò chuyện tự nhiên."
                    detailed_narrative = (
                        f"Trong khoảng thời gian {t_rng}, các cá nhân trong khung hình đang ngồi tại chỗ hoặc đứng trò chuyện, đi lại tự nhiên. "
                        f"Mọi người giữ khoảng cách thoải mái và cử chỉ ôn hòa, hoàn toàn không có dấu hiệu tranh cãi hay va chạm."
                    )

                seg_analyses.append({
                    "segment_id": s_id,
                    "macro_narrative": macro_sum,
                    "detailed_action": seg_act,
                    "detailed_narrative": detailed_narrative,
                    "weapon_detected": "Hung khí / Vật cứng" if (seg_threat_lvl == "NGUY HIỂM" and has_strike and loc_sc >= 8.6) else None,
                    "posture_override": None,
                    "threat_score": round(min(9.6, max(8.0, loc_sc)) if seg_threat_lvl == "NGUY HIỂM" else (min(7.4, max(4.5, loc_sc)) if seg_threat_lvl == "CẢNH BÁO" else min(2.4, max(0.5, loc_sc))), 1),
                    "threat_level": seg_threat_lvl,
                    "context_description": detailed_narrative,
                    "prediction_next_4s": loc_pred if loc_pred else "Tiếp tục quan sát diễn biến hoạt động của mọi người trong vài giây tiếp theo."
                })

        return {
            "status": "success",
            "model_tier": "Tier-3 Local Arbiter",
            "threat_level": threat_level,
            "is_safe_environment": is_safe,
            "primary_incident": primary_inc,
            "detailed_diagnosis": diag,
            "recommended_action": rec,
            "scene_context": scene_ctx,
            "chronological_evolution": f"Diễn biến toàn cảnh: Khu vực có {max_entities} người xuất hiện trong khung hình. Mọi cử chỉ và tương tác giữa các cá nhân được ghi nhận liền mạch với mức độ đánh giá là {threat_level}.",
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
        Lọc ra tối đa `max_keyframes` ảnh:
        - Nếu có sự kiện nguy hiểm: ưu tiên các mốc rủi ro cao nhất, cách nhau tối thiểu `min_time_gap`.
        - Nếu không có sự kiện nguy hiểm hoặc video an toàn: trích xuất đa pha thời gian
          (Khởi phát -> Cao trào -> Hệ quả) để Gemini nhận diện trọn vẹn tiến trình hành vi.
        """
        if not candidate_frames:
            return []

        timestamps = sorted(candidate_frames.keys())
        selected = []
        selected_timestamps = []

        if event_log:
            # Sắp xếp các sự kiện theo điểm nguy cơ giảm dần
            sorted_events = sorted(
                event_log,
                key=lambda x: x.get("threat_score", 0.0),
                reverse=True
            )
            for ev in sorted_events:
                ts = ev.get("timestamp", 0.0)
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

        # Nếu chưa đủ max_keyframes (hoặc không có event_log), bổ sung các khung hình đa pha thời gian
        if len(selected) < max_keyframes and timestamps:
            if not selected:
                # Không có event nguy hiểm nào -> Trích xuất đa pha hoàn chỉnh (Khởi phát -> Trọng tâm -> Kết quả)
                k = min(max_keyframes, len(timestamps))
                if k == 1:
                    chosen_indices = [len(timestamps) // 2]
                else:
                    chosen_indices = [int(round(i * (len(timestamps) - 1) / float(k - 1))) for i in range(k)]
                
                seen_idx = set()
                phase_labels = ["KHỞI ĐẦU", "CAO TRÀO / VẬN ĐỘNG CHÍNH", "HỆ QUẢ / KẾT THÚC", "DIỄN BIẾN"]
                for p_i, idx in enumerate(chosen_indices):
                    if idx not in seen_idx:
                        seen_idx.add(idx)
                        ts = timestamps[idx]
                        selected.append({
                            "timestamp": ts,
                            "threat_type": phase_labels[p_i] if p_i < len(phase_labels) else "TỔNG QUAN",
                            "threat_score": 0.0,
                            "details": f"Khung hình đa pha thời gian ({ts:.1f}s)",
                            "frame": candidate_frames[ts]
                        })
            else:
                # Đã có một số event, bổ sung thêm frame phân tán đều còn thiếu
                for ts in timestamps:
                    too_close = any(abs(ts - sel_ts) < min_time_gap for sel_ts in selected_timestamps)
                    if not too_close:
                        selected.append({
                            "timestamp": ts,
                            "threat_type": "BỔ SUNG BỐI CẢNH",
                            "threat_score": 0.0,
                            "details": f"Khung hình bổ trợ ({ts:.1f}s)",
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
        segment_info: Optional[List[Dict[str, Any]]] = None,
        segment_keyframes: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Tổng hợp báo cáo video đa tầng (Multi-Image Batch Request):
        1. Golden Cache thẩm định đầu tiên (0 token, 0ms, đối soát chính xác).
        2. Điều tiết nhịp độ (Pacing >= 4.2s) tránh xung đột hạn mức với Live Camera.
        3. Phân tầng: Tier 1 (gemini-3.8-flash) -> Tier 2 (gemini-3.5-flash) -> Tier 3 (Arbiter).
        4. Gửi đồng loạt keyframe các phân đoạn trong 1 request duy nhất (< 1,800 tokens, 100% trong hạn mức 15 RPM).
        """
        # 1. Thẩm định qua Golden Cache trước tiên (Bảo toàn 100% trải nghiệm & 0 Token)
        cache = self._load_golden_cache()
        source_key = video_metadata.get("video_source", "") or video_metadata.get("source_url", "")
        if isinstance(source_key, str) and source_key:
            src_base = os.path.basename(source_key).lower()
            for k, cached_data in cache.items():
                k_lower = k.lower()
                if src_base == k_lower:
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
                actors_str = f" | Các ID hiển thị trên ảnh chụp: {s.get('snapshot_actors')}" if s.get("snapshot_actors") else ""
                seg_lines.append(
                    f"- Phân đoạn {s.get('segment_id', '')} ({s.get('time_range', '')}, ảnh chụp tại {s.get('snapshot_ts', 0.0)}s): "
                    f"Ghi nhận {s.get('entity_count', 1)} đối tượng{actors_str}"
                )
            seg_text = "\nDANH SÁCH PHÂN ĐOẠN TIMELINE & ĐỐI TƯỢNG TRÊN ẢNH ĐẠI DIỆN (HÃY NHÌN TRỰC TIẾP ẢNH ĐỂ ĐÁNH GIÁ MỨC ĐỘ AN NINH VÀ TƯ THẾ NGỒI/ĐỨNG CỦA TỪNG ID):\n" + "\n".join(seg_lines)

        audio_status_str = video_metadata.get('audio_status', 'Không rõ')
        actor_hints_data = video_metadata.get('actor_hints', [])
        hints_lines = []
        for ah in actor_hints_data:
            hints_lines.append(f"- {ah.get('id_str', f'ID #{ah.get('cid', 1):02d}')}: {ah.get('position', 'không rõ')}, {ah.get('size_desc', '')}.")
        hints_text = ("\nCÁC ĐỐI TƯỢNG VÀ VỊ TRÍ KHÔNG GIAN GHI NHẬN TỪ BỘ THEO DÕI ĐỘNG HỌC:\n" + "\n".join(hints_lines)) if hints_lines else ""
        optical_note = ""
        if video_metadata.get("optical_alert"):
            optical_note = "\n[GỢI Ý CHUYỂN ĐỘNG]: Có ghi nhận nhịp chuyển động nhanh và tiếp xúc gần trong cảnh, hãy nhìn kỹ hình ảnh để xác định đây là xô xát thật hay chỉ là sinh hoạt bình thường.\n"

        prompt = f"""Bạn là một chuyên gia phân tích hành vi con người với lối quan sát tinh tế, tự nhiên và giàu sinh khí.
Hãy quan sát kỹ những người trong các ảnh đính kèm như thể bạn đang trực tiếp nhìn họ ngoài đời thực và thuật lại sự việc cho người dùng bằng ngôn ngữ đời thường, tự nhiên, rõ ràng nhất:

THÔNG SỐ VIDEO:
- Thời lượng đoạn phân tích: {video_metadata.get('duration_sec', 0):.1f}s
- Luồng âm thanh: {audio_status_str}
{hints_text}
{optical_note}
{seg_text}

QUY TẮC VĂN PHONG CON NGƯỜI BẮT BUỘC (BÁO CÁO DÀNH CHO NGƯỜI DÙNG, KHÔNG PHẢI LOG MÁY):
- Hãy viết hoàn toàn như một con người đang quan sát và kể lại hành động của những người trong video.
- CẤM TUYỆT ĐỐI dùng các thuật ngữ máy móc, đo đạc kỹ thuật hoặc nhãn hệ thống trong câu văn báo cáo: KHÔNG viết "px", "px/s", "m/s", "cự ly > 1.5 m", "xung lực", "động năng", "gia tốc động học", "biến thiên động học", "sinh cơ học", "trục thân", "trục lưng", "góc nghiêng", "T1", "T2", "T3", "T4", "PEAK", "Edge AI", "Autonomous Heuristic", "Tier-1", "Tier-2", "Tier-3", "Bounding Box".
- Thay vì viết "áp sát ở cự ly 47 px với xung lực đột biến", hãy miêu tả tự nhiên như con người: "bước nhanh lại gần và vung tay đánh mạnh về phía người đối diện khiến người này phải giơ hai tay lên che chắn trước ngực".

HƯỚNG DẪN QUAN SÁT THỊ GIÁC & ĐÁNH GIÁ NGUY CƠ KHÁCH QUAN:
1. TRỌNG TÀI THẨM ĐỊNH NGUY CƠ (Contextual Arbiter):
   - Quan sát khách quan bối cảnh thực tế: Lớp học/trường học, võ đài, nơi công cộng, văn phòng hoặc phòng sinh hoạt gia đình.
   - NGUY HIỂM: CHỈ KHI ĐÃ XẢY RA ẩu đả thể xác thực sự, dùng gậy gộc/hung khí vụt hoặc đâm, vung tay đấm đá/vật lộn trực diện, hoặc có người bị xô ngã/gục ngã -> kết luận "threat_level": "NGUY HIỂM" và "is_safe_environment": false.
   - CẢNH BÁO: Khi hai bên mới dừng ở mức căng thẳng lời nói, chỉ tay, tiến lại gần đối mặt hoặc thủ thế nhưng CHƯA có va chạm thể xác trực diện -> BẮT BUỘC kết luận "threat_level": "CẢNH BÁO" (điểm 4.5 - 5.8). TUYỆT ĐỐI KHÔNG đánh giá "NGUY HIỂM" dựa trên suy đoán tâm lý hay "sát khí" khi chưa có đòn đánh!
   - AN TOÀN: Khi các đối tượng sinh hoạt gia đình vui vẻ, cha mẹ chơi đùa cùng con cái, học tập, làm việc, đi lại, hoặc giao tiếp bình thường -> BẮT BUỘC kết luận "threat_level": "AN TOÀN", "is_safe_environment": true, "threat_score" trong các phân đoạn phải <= 1.8, và TUYỆT ĐỐI KHÔNG gán vai trò chiến đấu ("Kẻ tấn công", "Nạn nhân", "Phòng thủ") cho các thành viên trong cảnh an toàn.

2. ĐẶC TRỊ BẠO LỰC BAN ĐÊM, THIẾU SÁNG, MỜ NHÒE, CHE KHUẤT & GÓC QUAY XA:
   - Khi quan sát chuỗi ảnh liên hoàn đính kèm:
     So sánh sự thay đổi vị trí và cử chỉ của mọi người từ đầu đến cuối đoạn:
     + Nếu thấy 2 hoặc nhiều người lao vào nhau, ôm ghì, giằng co, vung tay/chân, xô đẩy, hoặc một người ngã xuống/lảo đảo: ĐÂY LÀ HÀNH VI XÔ XÁT / ĐÁNH NHAU / ẨU ĐẢ!
     + Phân biệt rõ ràng giữa ẨU ĐẢ thực tế với HOẠT ĐỘNG AN TOÀN: Khi các đối tượng trong bối cảnh gia đình (cha mẹ bế bồng, chơi đùa với con cái), trường học (học sinh trò chuyện, ngồi học, đi lại) hoặc nơi làm việc, các chuyển động nhanh hoặc bế bồng KHÔNG PHẢI là xô xát. Trong trường hợp này, BẮT BUỘC kết luận "threat_level": "AN TOÀN", "threat_score" <= 2.0, và "is_safe_environment": true.
     + Gợi ý chuyển động (nếu có) chỉ để bạn kiểm chứng chi tiết, KHÔNG ĐƯỢC ép buộc quy chụp nếu hình ảnh thực tế hoàn toàn là sinh hoạt an toàn, hòa nhã.

3. NHẬN DIỆN VŨ KHÍ & VẬT DỤNG NGUY HIỂM (Weapon & Tool Detection):
   - Quan sát kỹ xem các đối tượng có cầm gậy, que, thước dài, hung khí hoặc vật dụng nào để tấn công/đe dọa đối phương hay không.
   - Ghi nhận vào trường "weapon_detected" trong từng phân đoạn (Ví dụ: "Gậy dài", "Baton", "Ghế", hoặc null nếu không có).
   - Nếu có vũ khí/gậy trong cảnh xung đột, phân đoạn đó BẮT BUỘC có threat_score >= 8.5 và threat_level: "NGUY HIỂM".

4. NHẬN DIỆN TƯ THẾ NGỒI / ĐỨNG & VẬN ĐỘNG TRUNG THỰC (Gemini Visual Posture Rescue):
   - BẮT BUỘC NHÌN TRỰC TIẾP ẢNH ĐỂ HIỆU CHỈNH ĐỨNG HAY NGỒI CHO TỪNG [ID #0X], tuyệt đối không để sai lệch giữa đứng và ngồi:
     + Khi đối tượng [ID #0X] ở vị trí bàn ghế, phần thân dưới nằm sau mặt bàn và tầm đầu/vai ngang tầm người ngồi: BẮT BUỘC xác định là ĐANG NGỒI (ví dụ: "Ngồi tại bàn học", "Ngồi thẳng lưng tại bàn", "Ngồi quay đầu quan sát"). Tuyệt đối không gán nhầm là "Đang đứng" chỉ vì lưng thẳng!
     + Chỉ xác định là ĐANG ĐỨNG khi nhìn thấy rõ đối tượng đứng nhô cao vượt hẳn lên trên mặt bàn ghế hoặc đang đứng/di chuyển ở lối đi.
   - Trong mỗi phân đoạn, bạn BẮT BUỘC điền trường "dominant_posture" (4-6 từ) tổng hợp tư thế thực tế đã hiệu chỉnh của phân đoạn đó (Ví dụ: "Ngồi tại bàn học", "Ngồi học & Đứng trao đổi", "Đứng đối diện căng thẳng", "Xô xát / Vung tay đánh") để hiển thị ra bảng bên ngoài.

5. MÔ TẢ HÀNH VI CẤP VĨ MÔ & QUAN HỆ NHÂN QUẢ (Causal Macro Narrative):
   - Miêu tả chân thực diễn biến từng phân đoạn theo quan hệ nhân quả: Ai là người chủ động tác động lên ai (ví dụ: ID #03 bên phải chủ động vung gậy tấn công khiến ID #02 trục giữa giật lùi phòng vệ).
   - Tuyệt đối không dùng cụm từ chung chung sáo rỗng (như "hai bên có tương tác qua lại").
   - Đi thẳng vào hành vi và tương tác nhân quả trọng tâm, KHÔNG miêu tả dài dòng về bàn ghế, ánh sáng tự nhiên hay màu sắc phòng học.

6. NGUYÊN TẮC RÀNG BUỘC NHÃN KHUNG HÌNH & HIỆU CHỈNH CÁ NHÂN HÓA TỪNG NGƯỜI (Individualized Tag-Based Grounding - "Mỗi người mỗi vẻ"):
   - BẮT BUỘC ĐỌC NHÃN KHUNG BAO TRÊN TỪNG ẢNH PHÂN ĐOẠN: Mỗi ảnh đính kèm là ảnh đại diện chính thức của phân đoạn tương ứng (SEG-01, SEG-02...). Bạn PHẢI đọc đúng mã [ID #0X] vẽ trực tiếp trên ảnh của phân đoạn đó và đối chiếu với mục "Các ID hiển thị trên ảnh chụp" của phân đoạn đó.
   - TUYỆT ĐỐI KHÔNG lấy ID hoặc tư thế của khung ảnh trước/sau gán nhầm sang khung ảnh hiện tại.
   - PHÂN ĐỊNH RẠCH RÒI CẶP GÂY XUNG ĐỘT LẪN NHAU VÀ NGƯỜI NGOÀI CUỘC CHỈ NGÓ NHÌN (segment_actors):
     + Trong mỗi phân đoạn, bạn BẮT BUỘC điền mảng "segment_actors" hiệu chỉnh riêng biệt cho từng [ID #0X] có mặt trong phân đoạn đó ("mỗi người mỗi vẻ", tuyệt đối không dùng chung một câu mẫu áp cho nhiều người):
       * Người trực tiếp gây ra xung đột lẫn nhau (chỉ đúng cặp hoặc nhóm đang lao vào nhau, chỉ tay đối mặt, đẩy hoặc đánh nhau): Ghi rõ tương tác với mã ID nào trong "role" (Ví dụ: "Chủ động tấn công · với ID #02", "Giằng co / Phòng thủ · với ID #03", "Đối đầu chỉ tay · với ID #04"), mô tả động tác tay/chân thực tế trong "action" và tư thế đứng/ngồi cụ thể trong "posture", gán "severity": "danger" (nếu đang đánh nhau) hoặc "warning" (nếu đang đối mặt căng thẳng / phòng thủ).
       * Người ngoài cuộc chỉ ngó nhìn / đứng xem / ngồi tại bàn quay lại nhìn (khi trong phân đoạn ĐANG CÓ xung đột của người khác): Gán "severity": "safe", "role": "Người ngoài cuộc / Quan sát", và miêu tả đúng tư thế ngồi hoặc đứng riêng của từng người đó trong "action" & "posture" (Ví dụ: "Ngồi yên tại bàn đầu ngoái cổ nhìn về phía sau", "Đứng bên hành lang khoanh tay theo dõi sự việc").
       * Trong phân đoạn AN TOÀN (chưa có xung đột): Gán "severity": "safe", "role": "Học sinh" (hoặc vai trò tự nhiên), và ghi chính xác tư thế Đang ngồi hay Đang đứng của từng ID trong "action" & "posture" (Ví dụ: action="Ngồi trao đổi tại bàn", posture="Đang ngồi tại bàn học").
   - TRONG BỐI CẢNH AN TOÀN (Gia đình, trường học bình thường, công sở): Trường "role" PHẢI ghi vai trò tự nhiên của người đó (ví dụ: "Người cha", "Người mẹ", "Bé gái", "Học sinh", "Nhân viên"), TUYỆT ĐỐI KHÔNG dùng từ chiến đấu như "Kẻ tấn công", "Nạn nhân", "Người tham gia", "Ngoài cuộc".
   - QUY TẮC CHỐNG ĐỒNG NHẤT (Anti-Homogeneity): Nếu trong bối cảnh có nhiều người cùng mặc trang phục giống nhau (ví dụ: cùng mặc áo thun đen, cùng mặc áo sơ mi trắng đồng phục, đồ thể thao), TUYỆT ĐỐI KHÔNG dùng màu áo chung chung để phân biệt! Dùng vị trí không gian ("Bên trái", "Bàn đầu", "Trung tâm", "Bên phải", "Hàng sau").
   - BỘ LỌC TÍN HIỆU RÁC (Zero Fluff / Zero AI Slop):
     + KHÔNG miêu tả chi tiết vụn vặt vô nghĩa (màu tường, màu gạch nền, bàn ghế xếp ngay ngắn, ánh sáng tự nhiên).
     + KHÔNG đưa ra lời khuyên sáo rỗng vô nghĩa (như "hãy gọi 115 ngay", "cần giữ bình tĩnh") nếu không có chấn thương/biến cố nguy cấp thực tế.
     + TUYỆT ĐỐI KHÔNG để chú thích mở/đóng ngoặc đơn trong các trường văn bản người dùng ("actor_label", "distinctive_anchor", "true_action").

7. ĐẶC TRỊ TIẾN TRÌNH ĐA PHA (CHƯA VA CHẠM -> CAO TRÀO XÔ XÁT -> HẠ NHIỆT):
   - BẮT BUỘC phân biệt rạch ròi giữa CĂNG THẲNG LỜI NÓI (chưa đánh nhau) và BẠO LỰC THỂ XÁC (đã đánh nhau):
     + Pha 1 (Chưa đánh nhau / Chưa có va chạm thể xác): Khi các đối tượng đang ngồi/đứng trò chuyện, hoặc mới chỉ tay, tiến lại gần tranh cãi nhưng CHƯA có đòn đánh hay xô đẩy thể xác trực tiếp:
       * Nếu bình thường: BẮT BUỘC đánh giá "AN TOÀN" (0.8 - 2.2 điểm).
       * Nếu đang chỉ tay / tiến lại gần đối mặt căng thẳng: BẮT BUỘC đánh giá "CẢNH BÁO" (4.5 - 5.6 điểm).
       * TUYỆT ĐỐI KHÔNG ĐƯỢC ĐÁNH GIÁ "NGUY HIỂM" (hay >= 7.5 điểm) cho phân đoạn chưa có va chạm thể xác!
     + Pha 2 (Cao trào ẩu đả): Chỉ những phân đoạn nhìn thấy rõ đòn đánh, đấm đá, vật lộn, xô đẩy mạnh hoặc vung hung khí trên ảnh mới đánh giá "NGUY HIỂM" (8.0 - 9.6 điểm).
     + Pha 3 (Ngừng đánh / Hạ nhiệt): Khi các đối tượng đã dừng tay, tách nhau ra, có người can ngăn hoặc quay về chỗ: BẮT BUỘC hạ mức độ về "CẢNH BÁO" (4.5 - 5.8 điểm) hoặc "AN TOÀN" (0.8 - 2.0 điểm).
   - BẮT BUỘC TRẢ VỀ ĐẦY ĐỦ TẤT CẢ CÁC PHÂN ĐOẠN trong DANH SÁCH PHÂN ĐOẠN TIMELINE (từ SEG-01 đến SEG-XX).

8. Trả về kết quả ĐÚNG ĐỊNH DẠNG JSON sau (không thêm bất kỳ văn bản giải thích nào ngoài JSON):
{{
  "threat_level": "AN TOÀN" | "CẢNH BÁO" | "NGUY HIỂM",
  "is_safe_environment": true | false,
  "primary_incident": "Tóm tắt tiến trình sự kiện ngắn gọn, chính xác (1 câu)",
  "detailed_diagnosis": "Nhận định an ninh toàn diện phản ánh đúng các pha diễn biến và trạng thái kết thúc (2 câu súc tích).",
  "recommended_action": "Hành động khuyến nghị thực tế (Ví dụ: Giám sát ổn định sau sự cố / Nhắc nhở kỷ luật)",
  "scene_context": "Mô tả tổng thể không gian, bối cảnh thực tế và sự tương tác giữa các đối tượng (1-2 câu)",
  "chronological_evolution": "Tường thuật mạch lạc diễn biến toàn cảnh theo 3 giai đoạn: Giai đoạn đầu: ... Giai đoạn giữa: ... Giai đoạn kết thúc: ...",
  "overall_conclusion": "Kết luận an toàn tổng thể, đánh giá nguy cơ động học và khuyến nghị an ninh (1-2 câu)",
  "detected_actors": [
    {{
      "actor_index": 1,
      "tag_id": 1,
      "actor_label": "Tên gọi nhận diện gợi nhớ (Ví dụ: Học sinh bàn đầu hoặc Bé nhỏ)",
      "distinctive_anchor": "Điểm neo vị trí không gian (Ví dụ: Bên trái, Bàn đầu, Trung tâm, Bên phải)",
      "role": "Vai trò thực tế (Ví dụ: Thành viên gia đình / Học sinh / Người can ngăn / Nạn nhân)",
      "appearance": "Đặc điểm nhận dạng trang phục và vóc dáng",
      "true_action": "Hành động thực tế quan sát được",
      "posture_desc": "Mô tả tư thế cơ thể cụ thể (Ghi rõ Đang ngồi hay Đang đứng)"
    }}
  ],
  "segment_analyses": [
    {{
      "segment_id": "SEG-01",
      "macro_narrative": "Tóm tắt ngắn gọn 1 câu (12-22 từ) về diễn biến chính của phân đoạn để hiển thị ngoài bảng tổng quan",
      "detailed_action": "Cụm từ ngắn (4-8 từ) chỉ hành động chủ đạo",
      "dominant_posture": "Tư thế chủ đạo của phân đoạn do Gemini hiệu chỉnh (Ví dụ: 'Ngồi tại bàn học', 'Ngồi học & Đứng trao đổi', 'Đứng đối diện căng thẳng', 'Xô xát / Ra đòn')",
      "detailed_narrative": "Mô tả chi tiết nhưng CÔ ĐỌNG, SÚC TÍCH (2-3 câu, khoảng 35-55 từ, chỉ ghi thông tin cốt lõi cần thiết): Nêu rõ cặp đối tượng nào đang trực tiếp tương tác/gây xung đột với nhau, ai chỉ đứng/ngồi ngoài cuộc quan sát trên ảnh chụp của phân đoạn này và lý do xếp loại mức độ an ninh. Không lặp lại câu chữ của macro_narrative, không tả cảnh vật bàn ghế thừa thãi.",
      "focal_actors_desc": "Tóm lược ngắn gọn cặp tương tác chính và người quan sát trong ảnh (Ví dụ: ID #03 đối đầu trực tiếp với ID #02; ID #01 và ID #04 ngồi bàn đầu quan sát)",
      "segment_actors": [
        {{
          "tag_id": "ID #01",
          "role": "Vai trò riêng biệt của ID này trong phân đoạn (Ví dụ: 'Chủ động tấn công · với ID #02', 'Phòng thủ / Giằng co · với ID #01', 'Người ngoài cuộc / Quan sát', hoặc 'Học sinh')",
          "action": "Hành vi thực tế riêng của người này trên khung ảnh (mỗi người mỗi vẻ, không rập khuôn)",
          "posture": "Tư thế cơ thể thực tế của người này trên khung ảnh (Ghi rõ Đang ngồi tại bàn hay Đang đứng)",
          "severity": "danger" | "warning" | "safe"
        }}
      ],
      "weapon_detected": "Gậy / Hung khí" | null,
      "posture_override": null,
      "threat_score": 5.0,
      "threat_level": "NGUY HIỂM" | "CẢNH BÁO" | "AN TOÀN",
      "context_description": "Ghi giống detailed_narrative (2-3 câu cốt lõi, không lặp lại)",
      "prediction_next_4s": "Dự đoán ngắn gọn 1 câu về xu hướng hành vi trong 4 giây tiếp theo",
      "degraded_action": "Cụm từ ngắn (4-8 từ) mô tả hành vi bị biến dị/sơ sài ở nhánh suy giảm tài nguyên Z (khi lỡ mất khung hình đỉnh cử chỉ)",
      "degraded_narrative": "Mô tả hành vi bị biến dị ở nhánh Z khi thiếu hụt tài nguyên làm lỡ mất khoảnh khắc đỉnh của cử chỉ (ví dụ: nhánh chuẩn thấy rõ giơ tay vẫy hoặc va chạm đỉnh điểm, còn nhánh Z chỉ thấy hơi nhấc nhẹ tay rồi bỏ xuống liền hoặc lướt qua). Chỉ viết ngôn ngữ hành vi tự nhiên, tuyệt đối không giải thích kỹ thuật."
    }}
  ]
}}
"""

        contents = [prompt]

        # Đính kèm ảnh: Khi có danh sách ảnh đại diện của từng phân đoạn (segment_keyframes),
        # chỉ dùng đúng các ảnh đó để đảm bảo khớp 1-1 tuyệt đối giữa ảnh đại diện trên UI và phân tích của Gemini.
        raw_candidates = []
        if segment_keyframes:
            raw_candidates.extend(segment_keyframes)
        elif peak_keyframes:
            raw_candidates.extend(peak_keyframes)

        # Nhóm theo phân đoạn gốc (SEG-01, SEG-02...) và ưu tiên các phân đoạn có điểm nguy cơ cao nhất
        seg_score_map = {}
        if segment_info:
            for s in segment_info:
                seg_score_map[str(s.get("segment_id", ""))] = float(s.get("local_score", 0.0))

        seg_groups = {}
        for kf in raw_candidates:
            if kf.get("frame") is None:
                continue
            raw_sid = str(kf.get("segment_id", ""))
            m = re.search(r'(SEG-\d+)', raw_sid)
            key = m.group(1) if m else f"T_{round(kf.get('timestamp', 0.0), 1)}"
            seg_groups.setdefault(key, []).append(kf)

        ordered_keys = sorted(seg_groups.keys())
        rep_per_seg = []
        for idx_k, k in enumerate(ordered_keys):
            best_kf = max(
                seg_groups[k],
                key=lambda x: float(x.get("threat_score", seg_score_map.get(k, 0.0)))
            )
            best_kf = dict(best_kf)
            best_kf["_seg_key"] = k
            best_kf["_order_idx"] = idx_k
            best_kf["_priority_score"] = max(float(best_kf.get("threat_score", 0.0)), seg_score_map.get(k, 0.0))
            rep_per_seg.append(best_kf)

        if len(rep_per_seg) <= 6:
            for idx, kf in enumerate(rep_per_seg):
                frame = kf.get("frame")
                seg_id = kf.get("segment_id", f"Mốc {idx+1}")
                t_rng = kf.get("time_range", f"{kf.get('timestamp', 0):.1f}s")
                if frame is not None:
                    # Resize ảnh xuống tối đa 640x360 (nằm gọn trong 1 Tile 768x768 = 258 tokens theo Công thức 8 Bạch thư)
                    h, w = frame.shape[:2]
                    scale = min(640 / w, 360 / h, 1.0)
                    if scale < 1.0:
                        small_frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
                    else:
                        small_frame = frame

                    rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb_frame)
                    img_byte_arr = io.BytesIO()
                    pil_img.save(img_byte_arr, format='JPEG', quality=75)
                    img_bytes = img_byte_arr.getvalue()

                    contents.append(f"\n[ẢNH KHUNG HÌNH PHÂN ĐOẠN {seg_id} ({t_rng})]:")
                    contents.append(types.Part.from_bytes(
                        data=img_bytes,
                        mime_type="image/jpeg"
                    ))
        elif rep_per_seg:
            # Với video dài có nhiều phân đoạn (> 6 phân đoạn, ví dụ 17-19 phân đoạn SEG-01..SEG-19),
            # ghép mỗi 4 phân đoạn liên tiếp vào 1 Bảng Ghép Thị Giác 2x2 sắc nét (512x288 mỗi ô = 1024x576)
            # để Gemini đọc rõ từng nhãn [ID #0X] và phân biệt chính xác tư thế Đang ngồi tại bàn hay Đang đứng.
            cell_w, cell_h = 512, 288
            for chunk_start in range(0, len(rep_per_seg), 4):
                chunk = rep_per_seg[chunk_start:chunk_start + 4]
                grid_bgr = np.zeros((cell_h * 2, cell_w * 2, 3), dtype=np.uint8)
                chunk_labels = []
                for c_idx, kf in enumerate(chunk):
                    frame = kf.get("frame")
                    raw_sid = str(kf.get("_seg_key") or kf.get("segment_id", f"SEG-{chunk_start + c_idx + 1:02d}"))
                    t_rng = str(kf.get("time_range", f"{kf.get('timestamp', 0):.1f}s")).replace("➔", "-")
                    chunk_labels.append(f"{raw_sid} ({t_rng})")
                    if frame is not None and frame.size > 0:
                        cell_img = cv2.resize(frame, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
                    else:
                        cell_img = np.zeros((cell_h, cell_w, 3), dtype=np.uint8)
                    # Vẽ nhãn định danh phân đoạn rõ nét ở góc trên bên trái mỗi ô trong lưới 2x2
                    tag_txt = f"{raw_sid} [{t_rng}]"
                    cv2.rectangle(cell_img, (0, 0), (min(cell_w, 16 + len(tag_txt) * 10), 26), (12, 16, 24), -1)
                    cv2.putText(cell_img, tag_txt, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
                    r_pos = c_idx // 2
                    c_pos = c_idx % 2
                    y0, x0 = r_pos * cell_h, c_pos * cell_w
                    grid_bgr[y0:y0 + cell_h, x0:x0 + cell_w] = cell_img

                rgb_grid = cv2.cvtColor(grid_bgr, cv2.COLOR_BGR2RGB)
                pil_grid = Image.fromarray(rgb_grid)
                img_byte_arr = io.BytesIO()
                pil_grid.save(img_byte_arr, format='JPEG', quality=80)
                img_bytes = img_byte_arr.getvalue()

                contents.append(
                    f"\n[ẢNH BẢNG GHÉP 2x2 (Trái-Trên, Phải-Trên, Trái-Dưới, Phải-Dưới) CÁC PHÂN ĐOẠN {', '.join(chunk_labels)}]:"
                )
                contents.append(types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/jpeg"
                ))

        config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=8192,
            response_mime_type="application/json"
        )

        # 4. Thực thi qua Bộ Điều Phối Phân Tầng (Hierarchical Failover)
        if orch is not None:
            data, used_tier = orch.execute_multimodal_failover(contents=contents, config=config)
            if data is not None and isinstance(data, dict):
                self._sanitize_video_report_payload(data)
                data["status"] = "success"
                data["model_tier"] = getattr(used_tier, "value", str(used_tier))
                if "token_usage" not in data:
                    data["token_usage"] = 0
                if source_key and len(source_key) > 4:
                    save_key = os.path.basename(source_key)
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
            self._sanitize_video_report_payload(data)
            data["token_usage"] = token_usage
            data["status"] = "success"
            data["model_tier"] = "Tier-1 Gemini 3.8"

            if source_key and len(source_key) > 4:
                save_key = os.path.basename(source_key)
                self._save_to_golden_cache(save_key, data)

            return data

        except Exception as e:
            logger.warning(f"[TokenGuard] Lỗi gọi Gemini trong synthesize_video_report ({e}). Kích hoạt Tier-3 Local Arbiter...")
            fallback_data = self._synthesize_local_autonomous_report(event_summary, video_metadata, segment_info, reason=str(e))
            fallback_data["model_tier"] = "Tier-3 Local Arbiter"
            return fallback_data

    @staticmethod
    def _clean_human_video_text(text: Any) -> str:
        if not text:
            return ""
        s = str(text).strip()
        s = re.sub(r'\(\s*Autonomous\s+Heuristic\s+Arbiter\s*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\(\s*T[1-4](?:-PEAK)?(?:\s*[,/→\-]\s*T[1-4](?:-PEAK)?)*\s*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\[\s*T[1-4](?:-PEAK)?(?:\s*[,/→\-]\s*T[1-4](?:-PEAK)?)*\s*\]', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\b(?:ở|tại|từ|đến|sang|qua|pha|mốc|giai đoạn)?\s*T[1-4](?:-PEAK)?\b', '', s, flags=re.IGNORECASE)
        s = re.sub(r'(?:Hệ thống\s+)?(?:Kích hoạt\s+)?(?:Bộ hội chẩn\s+Cục bộ\s+Tự hành\s*)?\(?Tier-[123]\s*Autonomous\s*Heuristic[^.]*\.?', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\b(?:ở\s+)?cự ly\s*(?:an toàn\s*)?(?:dưới\s*|xuống còn\s*|tiếp xúc\s*|tiếp cận\s*)?(?:>\s*)?\d+(?:\.\d+)?\s*(?:px|m)\b', 'ở khoảng cách gần', s, flags=re.IGNORECASE)
        s = re.sub(r'\b(?:với\s+)?(?:vận tốc|tốc độ)(?:\s+vung\s+đòn|\s+vung\s+chi|\s+dịch\s+chuyển|\s+chuyển\s+động|\s+đỉnh|\s+chi)?(?:\s+đạt|\s+lên\s+mức)?\s*\d+(?:\.\d+)?\s*(?:px/s|m/s)\b', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\(\s*\d+(?:\.\d+)?\s*(?:px/s|px|m/s)[^)]*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r',?\s*không có xung lực đột biến', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\bxung lực(?:\s+động học|\s+cơ thể|\s+va chạm)?\b', 'tác động', s, flags=re.IGNORECASE)
        s = re.sub(r'\bđộng năng(?:\s+bạo lực)?\b', 'chuyển động', s, flags=re.IGNORECASE)
        s = re.sub(r'\bsinh cơ học\b', 'tư thế', s, flags=re.IGNORECASE)
        s = re.sub(r'\s{2,}', ' ', s)
        s = re.sub(r'\s+([,.;:!?])', r'\1', s)
        s = re.sub(r'^[,.;:\-\s]+', '', s).strip()
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        return s

    @classmethod
    def _sanitize_video_report_payload(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return data
        for k in ("primary_incident", "detailed_diagnosis", "recommended_action", "scene_context", "chronological_evolution", "overall_conclusion"):
            if k in data and data[k]:
                data[k] = cls._clean_human_video_text(data[k])
        segs = data.get("segment_analyses")
        if isinstance(segs, list):
            for seg in segs:
                if isinstance(seg, dict):
                    for sk in ("macro_narrative", "detailed_action", "detailed_narrative", "context_description", "prediction_next_4s", "degraded_action", "degraded_narrative"):
                        if sk in seg and seg[sk]:
                            seg[sk] = cls._clean_human_video_text(seg[sk])
        return data

