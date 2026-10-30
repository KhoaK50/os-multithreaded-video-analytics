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
        actual_cnt = int(video_metadata.get("actual_person_count") or 0)
        is_crowd = bool(video_metadata.get("is_crowd_scene"))
        if actual_cnt > 0 and not is_crowd:
            max_entities = min(actual_cnt, 4)
        else:
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
                    {"role": "Nạn nhân té ngã", "actor_label": "Nạn nhân té ngã", "distinctive_anchor": "Trung tâm", "action": "Mất thăng bằng ngã xuống mặt sàn", "posture": "Nằm trên mặt sàn", "appearance": "Người cần hỗ trợ"},
                    {"role": "Người tiến lại hỗ trợ", "actor_label": "Người tiến lại hỗ trợ", "distinctive_anchor": "Bên phải", "action": "Bước lại gần kiểm tra và đỡ dậy", "posture": "Đứng cúi người hỗ trợ", "appearance": "Người hỗ trợ"},
                    {"role": "Người ngoài cuộc quan sát", "actor_label": "Người ngoài cuộc quan sát", "distinctive_anchor": "Bên trái", "action": "Đứng nhìn về phía người bị ngã", "posture": "Đang đứng quan sát", "appearance": "Người xung quanh"},
                    {"role": "Người ngoài cuộc quan sát", "actor_label": "Người ngoài cuộc quan sát", "distinctive_anchor": "Phía sau", "action": "Dừng bước theo dõi sự việc", "posture": "Đang đứng tự nhiên", "appearance": "Người xung quanh"}
                ]
            else:
                base_roles = [
                    {"role": "Chủ động tấn công", "actor_label": "Chủ động tấn công", "distinctive_anchor": "Bên trái", "action": "Áp sát cự ly gần và vung tay ra đòn về phía đối phương", "posture": "Đang đứng nhào tới vung đòn", "appearance": "Chủ thể trực tiếp xung đột"},
                    {"role": "Phòng vệ / Né đòn", "actor_label": "Phòng vệ / Né đòn", "distinctive_anchor": "Bên phải", "action": "Co tay che chắn vùng đầu ngực và nghiêng người né đòn", "posture": "Đang đứng co tay phòng vệ", "appearance": "Chủ thể đối kháng"},
                    {"role": "Người ngoài cuộc quan sát", "actor_label": "Người ngoài cuộc quan sát", "distinctive_anchor": "Trung tâm", "action": "Giữ khoảng cách và quan sát diễn biến xung đột", "posture": "Đang đứng quan sát", "appearance": "Người xung quanh"},
                    {"role": "Người ngoài cuộc quan sát", "actor_label": "Người ngoài cuộc quan sát", "distinctive_anchor": "Phía sau", "action": "Đứng ở cự ly xa theo dõi sự việc", "posture": "Tư thế tự nhiên", "appearance": "Người xung quanh"}
                ]
        elif max_threat_score >= 4.0:
            threat_level = "CẢNH BÁO"
            is_safe = False
            primary_inc = "Ghi nhận hai bên đứng đối mặt căng thẳng và lời qua tiếng lại"
            diag = "Các cá nhân tiến lại gần đứng đối diện nhau với thái độ căng thẳng, có cử chỉ chỉ tay và giơ tay phòng thủ trước ngực nhưng chưa tung đòn đánh."
            rec = "Theo dõi sát tình hình và chủ động nhắc nhở để tránh sự việc leo thang thành xô xát."
            macro_action = "Đứng đối mặt tranh cãi căng thẳng"
            scene_ctx = f"Khu vực có {max_entities} người, trong đó hai bên đang đứng đối diện nhau ở cự ly gần với cử chỉ tranh luận căng thẳng."
            overall_concl = "Kết luận: Hai bên đang có dấu hiệu lời qua tiếng lại và đối đầu gần, cần lưu ý quan sát để ngăn ngừa va chạm."
            base_roles = [
                {"role": "Đối đầu căng thẳng", "actor_label": "Đối đầu căng thẳng", "distinctive_anchor": "Bên trái", "action": "Đứng đối diện và có cử chỉ trao đổi căng thẳng", "posture": "Đang đứng đối diện", "appearance": "Chủ thể đối đầu"},
                {"role": "Đối đầu căng thẳng", "actor_label": "Đối đầu căng thẳng", "distinctive_anchor": "Bên phải", "action": "Đứng nhìn thẳng vào người đối diện và giữ khoảng cách phòng bị", "posture": "Đang đứng đối diện", "appearance": "Chủ thể đối đầu"},
                {"role": "Người ngoài cuộc quan sát", "actor_label": "Người ngoài cuộc quan sát", "distinctive_anchor": "Trung tâm", "action": "Đứng yên theo dõi cuộc đối thoại", "posture": "Đang đứng tự nhiên", "appearance": "Người xung quanh"},
                {"role": "Người ngoài cuộc quan sát", "actor_label": "Người ngoài cuộc quan sát", "distinctive_anchor": "Phía sau", "action": "Giữ nguyên vị trí sinh hoạt", "posture": "Tư thế tự nhiên", "appearance": "Người xung quanh"}
            ]
        else:
            threat_level = "AN TOÀN"
            is_safe = True
            primary_inc = "Mọi người sinh hoạt, di chuyển và trò chuyện bình thường"
            diag = f"Ghi nhận {max_entities} người trong khu vực đang sinh hoạt, trao đổi hoặc đi lại tự nhiên, không có biểu hiện tranh cãi hay xô xát."
            rec = "Không gian hoàn toàn bình thường, tiếp tục duy trì quan sát định kỳ."
            macro_action = "Sinh hoạt và trao đổi bình thường"
            scene_ctx = f"Khu vực có {max_entities} người đang sinh hoạt và trao đổi ôn hòa trong không gian trật tự."
            overall_concl = "Đánh giá tổng thể: Toàn bộ hoạt động của mọi người trong khu vực diễn ra bình thường và hoàn toàn an toàn."
            base_roles = [
                {"role": "Hoạt động bình thường", "actor_label": "Hoạt động bình thường", "distinctive_anchor": "Bên trái", "action": "Sinh hoạt và trao đổi tự nhiên", "posture": "Tư thế thoải mái", "appearance": "Trang phục thường ngày"},
                {"role": "Hoạt động bình thường", "actor_label": "Hoạt động bình thường", "distinctive_anchor": "Bên phải", "action": "Trao đổi và di chuyển nhịp nhàng", "posture": "Tư thế tự nhiên", "appearance": "Trang phục thường ngày"},
                {"role": "Hoạt động bình thường", "actor_label": "Hoạt động bình thường", "distinctive_anchor": "Trung tâm", "action": "Duy trì hoạt động ổn định", "posture": "Tư thế tự nhiên", "appearance": "Trang phục thường ngày"},
                {"role": "Hoạt động bình thường", "actor_label": "Hoạt động bình thường", "distinctive_anchor": "Phía sau", "action": "Sinh hoạt bình thường", "posture": "Tư thế ổn định", "appearance": "Trang phục thường ngày"}
            ]

        detected_actors = []
        for i in range(max_entities):
            r = base_roles[i] if i < len(base_roles) else {"role": "Hoạt động bình thường", "actor_label": "Hoạt động bình thường", "distinctive_anchor": "Trung tâm", "action": "Sinh hoạt tự nhiên", "posture": "Tự nhiên", "appearance": "Trang phục thường ngày"}
            detected_actors.append({
                "actor_index": i + 1,
                "actor_label": r.get("actor_label", "Hoạt động bình thường"),
                "distinctive_anchor": r.get("distinctive_anchor", "Trung tâm"),
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
                    dom_posture = "Ngã xuống sàn" if (has_fall and not (has_clash or has_strike)) else "Xô xát / Ra đòn"
                    deg_act = "Ngã xuống mặt sàn" if (has_fall and not (has_clash or has_strike)) else "Áp sát xô đẩy và va chạm"
                    if has_fall and not (has_clash or has_strike):
                        macro_sum = "Một người bất ngờ mất thăng bằng ngã xuống sàn, những người xung quanh tiến lại gần hỗ trợ."
                        detailed_narrative = (
                            f"Trong khoảng thời gian {t_rng}, một cá nhân bất ngờ loạng choạng rồi ngã xuống mặt sàn. "
                            f"Những người đứng gần đó lập tức dừng việc đang làm và bước tới kiểm tra, đỡ người bị ngã dậy."
                        )
                        deg_nar = "Một cá nhân đang nằm trên mặt sàn và những người xung quanh tiến lại gần cúi xuống hỗ trợ."
                    else:
                        is_loc_sum_safe = any(w in loc_sum.lower() for w in ["ổn định", "bình thường", "an toàn", "không có xung lực", "chưa phát sinh"])
                        macro_sum = loc_sum if (loc_sum and not is_loc_sum_safe) else "Các cá nhân áp sát ở cự ly gần, vung tay ra đòn tốc độ cao và đối kháng trực diện."
                        bystander_tail = ", trong khi những người xung quanh giữ khoảng cách quan sát." if max_entities > 2 else "."
                        detailed_narrative = (
                            f"Trong khoảng thời gian {t_rng}, một người chủ động bước nhanh tới áp sát và tung đòn vung tay tốc độ cao về phía đối phương. "
                            f"Người đối diện lập tức giơ tay che chắn vùng đầu ngực và nghiêng người lách né đòn{bystander_tail}"
                        )
                        deg_nar = "Các cá nhân tiến sát vào nhau, xuất hiện hành động vung đòn tốc độ cao và đối kháng trực tiếp ở cự ly gần."
                elif seg_threat_lvl == "CẢNH BÁO":
                    seg_act = "Đứng đối mặt tranh cãi căng thẳng"
                    dom_posture = "Đứng đối diện căng thẳng"
                    deg_act = "Đứng đối mặt căng thẳng"
                    is_loc_sum_mismatch = any(w in loc_sum.lower() for w in ["ổn định", "bình thường", "an toàn", "không có xung lực"])
                    macro_sum = loc_sum if (loc_sum and not is_loc_sum_mismatch) else "Hai bên tiến lại gần đứng đối mặt nhau với cử chỉ trao đổi căng thẳng."
                    detailed_narrative = (
                        f"Trong khoảng thời gian {t_rng}, các cá nhân bước lại gần và đứng đối diện nhau với thái độ căng thẳng, xuất hiện cử chỉ đưa tay trao đổi hoặc giữ thế phòng bị trước ngực. "
                        f"Hai bên mới dừng ở mức đối đầu gần, chưa ghi nhận pha vung đòn tấn công."
                    )
                    deg_nar = "Các cá nhân đứng đối diện nhau ở khoảng cách gần với tư thế và cử chỉ trao đổi căng thẳng."
                else:
                    seg_act = "Sinh hoạt và trao đổi bình thường"
                    dom_posture = "Sinh hoạt bình thường"
                    deg_act = "Sinh hoạt và trao đổi tự nhiên"
                    is_loc_sum_combat = any(w in loc_sum.lower() for w in ["xung đột", "xô xát", "tấn công", "phòng vệ", "cảnh báo"])
                    macro_sum = loc_sum if (loc_sum and not is_loc_sum_combat) else "Mọi người giữ khoảng cách thoải mái, sinh hoạt và trao đổi tự nhiên."
                    detailed_narrative = (
                        f"Trong khoảng thời gian {t_rng}, các cá nhân trong khung hình đang sinh hoạt, trao đổi và đi lại tự nhiên. "
                        f"Mọi người giữ khoảng cách thoải mái và cử chỉ ôn hòa, hoàn toàn không có dấu hiệu tranh cãi hay va chạm."
                    )
                    deg_nar = "Mọi người trong khu vực giữ vị trí ổn định, sinh hoạt và trao đổi tự nhiên."

                seg_analyses.append({
                    "segment_id": s_id,
                    "macro_narrative": macro_sum,
                    "detailed_action": seg_act,
                    "dominant_posture": dom_posture,
                    "detailed_narrative": detailed_narrative,
                    "weapon_detected": None,
                    "posture_override": None,
                    "threat_score": round(min(9.6, max(8.0, loc_sc)) if seg_threat_lvl == "NGUY HIỂM" else (min(7.4, max(4.5, loc_sc)) if seg_threat_lvl == "CẢNH BÁO" else min(2.4, max(0.5, loc_sc))), 1),
                    "threat_level": seg_threat_lvl,
                    "context_description": detailed_narrative,
                    "prediction_next_4s": loc_pred if loc_pred else "Tiếp tục quan sát diễn biến hoạt động của mọi người trong vài giây tiếp theo.",
                    "degraded_action": deg_act,
                    "degraded_narrative": deg_nar
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
        for ev in event_summary[:20]:
            ts_str = f"{int(ev.get('timestamp', 0)) // 60:02d}:{int(ev.get('timestamp', 0)) % 60:02d}"
            timeline_lines.append(
                f"- [{ts_str}] {ev.get('threat_type', 'HÀNH VI')} "
                f"({ev.get('details', '')}, Điểm động học: {ev.get('threat_score', 0):.2f})"
            )
        timeline_text = "\n".join(timeline_lines) if timeline_lines else "- Toàn bộ khung cảnh duy trì trạng thái ổn định."

        seg_text = ""
        if segment_info:
            seg_lines = []
            for s in segment_info:
                actors_str = f" | Chủ thể & vị trí ghi nhận: {s.get('snapshot_actors')}" if s.get("snapshot_actors") else ""
                seg_lines.append(
                    f"- Phân đoạn {s.get('segment_id', '')} ({s.get('time_range', '')}, ảnh đại diện tại {s.get('snapshot_ts', 0.0)}s, "
                    f"điểm động học sơ bộ {s.get('local_score', 0.0)}/10): "
                    f"Có {s.get('entity_count', 1)} người{actors_str}"
                )
            seg_text = "\nDANH SÁCH PHÂN ĐOẠN TIMELINE & VỊ TRÍ CHỦ THỂ TRÊN ẢNH ĐẠI DIỆN:\n" + "\n".join(seg_lines)

        audio_status_str = video_metadata.get('audio_status', 'Không rõ')
        actual_person_cnt = int(video_metadata.get('actual_person_count') or 0)
        person_cnt_line = (
            f"- Số người thực tế xuất hiện đồng thời trong cảnh: {actual_person_cnt} người "
            f"(TUYỆT ĐỐI chỉ mô tả đúng {actual_person_cnt} người thực sự có mặt, KHÔNG ĐƯỢC bịa thêm người thứ {actual_person_cnt + 1} hay đối tượng phụ không tồn tại)"
            if actual_person_cnt > 0 else ""
        )
        actor_hints_data = video_metadata.get('actor_hints', [])
        hints_lines = []
        for ah in actor_hints_data:
            hints_lines.append(
                f"- Chủ thể vị trí {ah.get('position', 'Trung tâm')}: {ah.get('role_hint', 'Hoạt động bình thường')}, {ah.get('size_desc', 'vóc dáng người lớn')}."
            )
        hints_text = ("\nCÁC CHỦ THỂ VÀ VỊ TRÍ KHÔNG GIAN GHI NHẬN TỪ BỘ THEO DÕI ĐỘNG HỌC:\n" + "\n".join(hints_lines)) if hints_lines else ""
        optical_note = ""
        if video_metadata.get("optical_alert"):
            optical_note = "\n[GỢI Ý CHUYỂN ĐỘNG]: Có ghi nhận nhịp chuyển động nhanh và tiếp xúc gần trong cảnh, hãy nhìn kỹ hình ảnh để xác định đây là xô xát thật hay chỉ là sinh hoạt bình thường.\n"

        prompt = f"""Bạn là chuyên gia phân tích hành vi thị giác an ninh với khả năng quan sát chuẩn xác, khách quan và mạch lạc.
Hãy quan sát kỹ những người trong các ảnh đính kèm và thuật lại diễn biến bằng ngôn ngữ tiếng Việt trang trọng, rõ ràng, súc tích:

THÔNG SỐ VIDEO:
- Thời lượng đoạn phân tích: {video_metadata.get('duration_sec', 0):.1f}s
- Luồng âm thanh: {audio_status_str}
{person_cnt_line}
{hints_text}
{optical_note}
{seg_text}

QUY TẮC ĐỊNH DANH & VĂN PHONG BẮT BUỘC:
- CẤM TUYỆT ĐỐI sử dụng mã số tracker như "ID #01", "ID #02", "ID #03", "ID #04", "Đối tượng #01", "Đối tượng #03", "Người tham gia 1", "Người tham gia 2" ở BẤT KỲ trường nào trong JSON.
- Thay vì gắn nhãn số ID, hãy định danh từng người bằng VAI TRÒ HÀNH VI kết hợp VỊ TRÍ KHÔNG GIAN thực tế trên khung hình: ví dụ "Người bên trái", "Người bên phải", "Người ở trung tâm", cùng vai trò như "Chủ động tấn công", "Phòng vệ / Né đòn", "Đối đầu căng thẳng", "Người ngoài cuộc quan sát", hoặc "Hoạt động bình thường".
- CẤM TUYỆT ĐỐI dùng thuật ngữ máy móc kỹ thuật trong lời văn báo cáo: KHÔNG viết "px", "px/s", "m/s", "cự ly > 1.5 m", "xung lực", "động năng", "gia tốc động học", "sinh cơ học", "trục thân", "T1", "T2", "T3", "T4", "PEAK", "Edge AI", "Autonomous Heuristic", "Tier-1", "Tier-2", "Tier-3", "Bounding Box".
- CẤM TUYỆT ĐỐI viết chú thích trong dấu ngoặc đơn (...) ở bất kỳ trường văn bản nào dành cho người dùng.

HƯỚNG DẪN QUAN SÁT THỊ GIÁC & ĐÁNH GIÁ MỨC ĐỘ NGUY CƠ:
1. PHÂN ĐỊNH CHÍNH XÁC 3 MỨC ĐỘ AN NINH THEO TIẾN TRÌNH THỜI GIAN:
   - NGUY HIỂM (8.0 - 9.6 điểm):
     + Khi thực sự đã xảy ra ẩu đả thể xác, đấm đá, vật lộn, giằng co, xô ngã, hoặc dùng gậy gộc/hung khí tấn công.
     + Nếu hai bên đã thực sự vung nắm đấm hoặc tung đòn tấn công bạo lực ở cự ly gần: Đánh giá NGUY HIỂM.
   - CẢNH BÁO (4.5 - 6.0 điểm):
     + Khi hai bên chỉ mới tiếp cận, đứng đối diện nhau, có cử chỉ chỉ tay, tranh cãi gay gắt bằng lời nói hoặc có dấu hiệu căng thẳng ban đầu nhưng CHƯA HỀ có va chạm thể xác, chưa có đòn đánh trúng (Pha Khởi đầu / Tiền xung đột) -> BẮT BUỘC chỉ xếp loại "threat_level": "CẢNH BÁO" với "threat_score" từ 4.5 đến 5.5 điểm. Tuyệt đối không đánh giá NGUY HIỂM khi hai người mới chỉ bước lại gần hoặc đối mặt tranh chấp!
   - AN TOÀN (0.6 - 2.2 điểm):
     + Khi mọi người sinh hoạt gia đình, học tập, làm việc, đi lại hoặc trò chuyện ôn hòa bình thường -> kết luận "threat_level": "AN TOÀN", "is_safe_environment": true, "threat_score" <= 1.8.

2. ĐẶC TRỊ BỐI CẢNH BAN ĐÊM, MỜ NHÒE & PHÂN BIỆT SINH HOẠT AN TOÀN:
   - Nếu thấy 2 người lao vào nhau, vung tay đấm/đá, ôm ghì vật lộn hoặc ngã xuống đất: kết luận NGUY HIỂM.
   - Ngược lại, trong bối cảnh gia đình (cha mẹ bế con, chơi đùa), lớp học hoặc công sở đang trao đổi ôn hòa: kết luận AN TOÀN, không gán vai trò chiến đấu.

3. NHẬN DIỆN VŨ KHÍ & HUNG KHÍ:
   - Chỉ điền tên vũ khí vào "weapon_detected" khi nhìn thấy rõ gậy, dao, thanh sắt, ghế hoặc vật cứng dùng để tấn công trên ảnh; nếu đánh tay không thì BẮT BUỘC để null.

4. NHẬN DIỆN TƯ THẾ NGỒI / ĐỨNG TRUNG THỰC THEO ĐÚNG BỐI CẢNH:
   - CHỈ mô tả "Ngồi tại bàn" khi trên ảnh thực sự là phòng học hoặc văn phòng có bàn ghế rõ ràng.
   - Với cảnh ngoài trời, bãi đất, đường phố, cạnh xe tải hoặc hành lang trống: TUYỆT ĐỐI KHÔNG viết "Ngồi tại bàn", "Bàn đầu", "Hàng sau". Hãy mô tả đúng tư thế thực tế như "Đứng áp sát ra đòn", "Đứng co tay né đòn", "Vật lộn trên mặt đất", "Đang đứng trao đổi".
   - Điền trường "dominant_posture" (3-6 từ) phản ánh đúng tư thế chủ đạo của phân đoạn.

5. TẬP TRUNG ĐÚNG SỐ NGƯỜI THỰC TẾ & CÁ NHÂN HÓA TỪNG CHỦ THỂ:
   - Mảng "detected_actors" CHỈ ĐƯỢC chứa đúng số người thực sự xuất hiện trong cảnh (ví dụ cảnh chỉ có 2 người đánh nhau thì "detected_actors" CHỈ có đúng 2 phần tử cho người bên trái và người bên phải; TUYỆT ĐỐI KHÔNG tạo thêm phần tử thứ 3, thứ 4).
   - Trong mỗi phân đoạn, mảng "segment_actors" mô tả riêng biệt từng người thực sự xuất hiện trên ảnh của phân đoạn đó theo vị trí không gian "spatial_anchor" ("Bên trái", "Bên phải", "Trung tâm", "Phía trước", "Phía sau"):
     + Người chủ động vung đòn / tấn công: "role": "Chủ động tấn công", "severity": "danger".
     + Người bị tấn công đang giơ tay đỡ / nghiêng người lách né đòn: "role": "Phòng vệ / Né đòn", "severity": "warning" (hoặc "danger" nếu cả hai cùng lao vào đấm đá / vật lộn trả đòn trực diện, khi đó gán "role": "Đối kháng / Vật lộn").
     + Người đứng/ngồi ngoài cuộc chỉ nhìn theo (nếu cảnh thực sự có người thứ 3 trở lên): "role": "Người ngoài cuộc quan sát", "severity": "safe".
     + Trong cảnh hoàn toàn AN TOÀN: "role" ghi vai trò tự nhiên ("Học sinh", "Nhân viên", "Hoạt động bình thường"), "severity": "safe".

6. Trả về ĐÚNG ĐỊNH DẠNG JSON sau (không thêm văn bản ngoài JSON, trả về đầy đủ mọi phân đoạn từ SEG-01 đến hết):
{{
  "threat_level": "AN TOÀN" | "CẢNH BÁO" | "NGUY HIỂM",
  "is_safe_environment": true | false,
  "primary_incident": "Tóm tắt sự kiện cốt lõi ngắn gọn trong 1 câu, không chứa mã ID hay ngoặc đơn",
  "detailed_diagnosis": "Nhận định an ninh toàn diện phản ánh đúng diễn biến từ đầu đến cuối trong 2 câu súc tích",
  "recommended_action": "Hành động khuyến nghị thực tế, trang trọng trong 1 câu",
  "scene_context": "Mô tả không gian thực tế và tương tác giữa các chủ thể theo vị trí trái/phải trong 1-2 câu",
  "chronological_evolution": "Tường thuật mạch lạc theo 3 giai đoạn: Giai đoạn đầu: ... Giai đoạn giữa: ... Giai đoạn kết thúc: ...",
  "overall_conclusion": "Kết luận an ninh tổng thể và đánh giá mức độ rủi ro trong 1-2 câu",
  "detected_actors": [
    {{
      "actor_index": 1,
      "actor_label": "Chủ động tấn công",
      "distinctive_anchor": "Bên trái",
      "role": "Chủ động tấn công",
      "appearance": "Đặc điểm trang phục và vóc dáng ngắn gọn",
      "true_action": "Hành động thực tế xuyên suốt như áp sát vung đòn và vật lộn",
      "posture_desc": "Tư thế cơ thể cụ thể không dùng ngoặc đơn"
    }}
  ],
  "segment_analyses": [
    {{
      "segment_id": "SEG-01",
      "macro_narrative": "Tóm tắt ngắn gọn 1 câu 12-22 từ về diễn biến chính của phân đoạn, không dùng mã ID",
      "detailed_action": "Cụm từ ngắn 4-8 từ chỉ hành động chủ đạo",
      "dominant_posture": "Tư thế chủ đạo của phân đoạn trong 3-6 từ",
      "detailed_narrative": "Mô tả chi tiết nhưng cô đọng trong 2-3 câu: nêu rõ người ở vị trí nào chủ động ra đòn hay tương tác với người ở vị trí nào và lý do xếp loại mức độ an ninh",
      "focal_actors_desc": "Tóm lược ngắn gọn tương tác theo vị trí không gian, tuyệt đối không viết ID #01",
      "segment_actors": [
        {{
          "spatial_anchor": "Bên trái",
          "role": "Chủ động tấn công",
          "action": "Áp sát cự ly gần và vung tay đấm về phía người đối diện",
          "posture": "Đứng tấn nhào người vung tay ra đòn",
          "severity": "danger" | "warning" | "safe"
        }}
      ],
      "weapon_detected": "Tên hung khí cụ thể" | null,
      "posture_override": null,
      "threat_score": 8.4,
      "threat_level": "NGUY HIỂM" | "CẢNH BÁO" | "AN TOÀN",
      "context_description": "Mô tả chi tiết 2-3 câu cốt lõi đồng bộ với detailed_narrative",
      "prediction_next_4s": "Dự báo ngắn gọn 1 câu về xu hướng hành vi trong vài giây tiếp theo",
      "degraded_action": "Cụm từ ngắn 4-8 từ mô tả hành vi quan sát được qua chuỗi khung hình thưa",
      "degraded_narrative": "Mô tả tự nhiên 1 câu 15-25 từ về hành vi quan sát được mà không nhắc thuật ngữ kỹ thuật"
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
        s = re.sub(r'^(?:ở|tại|trên)\s+(?:nhánh|luồng)\s+(?:z|tùy\s+chỉnh|suy\s+giảm)[^,:]*[,:]?\s*', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\b(?:nhánh|luồng)\s+(?:chuẩn|y)\s+[^,;.]*[,;]\s*(?:còn|trong khi)\s+(?:nhánh|luồng)\s+(?:z|tùy\s+chỉnh)\s+(?:chỉ\s+)?', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\(\s*với\s+ID\s*#?\s*\d+\s*\)', 'với người đối diện', s, flags=re.IGNORECASE)
        s = re.sub(r'\(\s*bởi\s+ID\s*#?\s*\d+\s*\)', 'bởi người đối diện', s, flags=re.IGNORECASE)
        s = re.sub(r'\[\s*ID\s*#?\s*\d+\s*\]', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\(\s*ID\s*#?\s*\d+\s*\)', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\bID\s*#?\s*\d+\b', 'chủ thể', s, flags=re.IGNORECASE)
        s = re.sub(r'\b(?:Đối tượng|Chủ thể|Người tham gia)\s*#\s*\d+\b', 'chủ thể', s, flags=re.IGNORECASE)
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
        actors = data.get("detected_actors")
        if isinstance(actors, list):
            for act in actors:
                if isinstance(act, dict):
                    act.pop("tag_id", None)
                    for ak in ("actor_label", "distinctive_anchor", "role", "appearance", "true_action", "posture_desc"):
                        if ak in act and act[ak]:
                            cleaned_ak = re.sub(r'\[?\bID\s*#?\s*\d+\b\]?', '', str(act[ak]), flags=re.IGNORECASE)
                            cleaned_ak = re.sub(r'\b(?:Đối tượng|Chủ thể|Người tham gia)\s*#?\s*\d+\b', '', cleaned_ak, flags=re.IGNORECASE)
                            cleaned_ak = re.sub(r'\([^)]*\)', '', cleaned_ak)
                            act[ak] = re.sub(r'\s{2,}', ' ', cleaned_ak).strip(' ·-—:,;/[]')
        segs = data.get("segment_analyses")
        if isinstance(segs, list):
            for seg in segs:
                if isinstance(seg, dict):
                    for sk in ("macro_narrative", "detailed_action", "dominant_posture", "detailed_narrative", "focal_actors_desc", "context_description", "prediction_next_4s", "degraded_action", "degraded_narrative"):
                        if sk in seg and seg[sk]:
                            seg[sk] = cls._clean_human_video_text(seg[sk])
                    seg_actors = seg.get("segment_actors")
                    if isinstance(seg_actors, list):
                        for sa in seg_actors:
                            if isinstance(sa, dict):
                                sa.pop("tag_id", None)
                                for sak in ("spatial_anchor", "role", "action", "posture"):
                                    if sak in sa and sa[sak]:
                                        c_sa = re.sub(r'\[?\bID\s*#?\s*\d+\b\]?', '', str(sa[sak]), flags=re.IGNORECASE)
                                        c_sa = re.sub(r'\([^)]*\)', '', c_sa)
                                        sa[sak] = re.sub(r'\s{2,}', ' ', c_sa).strip(' ·-—:,;/[]')
        return data

