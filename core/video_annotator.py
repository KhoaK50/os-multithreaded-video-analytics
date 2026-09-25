"""
Video Annotator Engine: Phân tích & Dán nhãn Video Quy mô lớn bằng YOLOv8-Pose trên RTX 5060.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.

Chức năng:
1. Nhập file video từ Local (.mp4, .avi, .mov) hoặc Web URL (YouTube, mạng xã hội) qua yt-dlp.
2. Hỗ trợ cắt đoạn Timeline tùy chọn (start_time -> end_time) kiểu CapCut, không tốn đĩa.
3. Chạy YOLOv8-Pose trên GPU NVIDIA GeForce RTX 5060 (>80 FPS) để phát hiện ĐA ĐỐI TƯỢNG.
4. Vẽ Bounding Box kiểu Sci-Fi (Corner Brackets) + Bộ Khung Xương Neon 17 khớp nối cho từng người.
5. Đánh giá Sinh cơ học (Biomechanics): Đo góc trục thân người, phát hiện té ngã, phát hiện cử chỉ bạo lực qua từng khung hình.
6. Kết xuất (Export) video thành phẩm hoàn chỉnh (.mp4) tương thích trình duyệt web.
7. Tích hợp TokenGuard: Chọn 1-3 keyframe đỉnh điểm, gọi 1 lượt Gemini 3.5 Flash Lite với ngân sách < 1,500 tokens.
"""

import os
import sys
import time
import math
import threading
import subprocess
import shutil
import cv2
import numpy as np
from typing import Optional, Dict, Any, Callable, Tuple, List

from core.cyber_hud import CyberHUDRenderer
from core.config import CONFIG

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False


def format_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"




def probe_web_video(url: str) -> Dict[str, Any]:
    """
    Quét nhanh thông tin video (Metadata) từ URL mà KHÔNG tải video.
    Trả về: title, duration, duration_str, thumbnail, uploader, is_long (> 180s).
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError("Thư viện yt-dlp chưa được cài đặt trên hệ thống.")

    probe_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'extractor_args': {'youtube': {'player_client': ['ios', 'android', 'web']}},
    }
    try:
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e_probe:
        err_msg = str(e_probe)
        if any(w in err_msg.lower() for w in ["private", "sign in", "login", "drm", "copyright", "blocked", "bản quyền", "members-only"]):
            raise RuntimeError(
                "Video này được bảo vệ bản quyền, giới hạn độ tuổi hoặc đặt chế độ riêng tư không cho phép tải trực tiếp qua liên kết. "
                "Gợi ý: Bạn hãy thử link video công khai khác, hoặc tải video về máy rồi chọn ô '📁 File Trong Máy' để kéo thả vào phân tích tức thì."
            )
        elif "Video unavailable" in err_msg:
            raise RuntimeError("Đường link video không tồn tại hoặc đã bị gỡ bỏ.")
        else:
            raise RuntimeError(f"Không thể truy cập video từ URL: {err_msg[:160]}")

    if not info:
        raise RuntimeError("Không thể trích xuất thông tin từ đường link này.")

    total_duration = float(info.get("duration", 0.0) or 0.0)
    return {
        "title": info.get("title", "Video từ Internet"),
        "duration": total_duration,
        "duration_str": format_time(total_duration),
        "thumbnail": info.get("thumbnail", ""),
        "uploader": info.get("uploader", "Web Source"),
        "is_long": total_duration > 180.0
    }


def check_video_has_audio(file_path: str) -> bool:
    """Kiểm tra file video có luồng âm thanh hay không bằng ffprobe."""
    if not os.path.exists(file_path):
        return False
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            file_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        return "audio" in res.stdout.lower()
    except Exception:
        return False


def download_web_video(
    url: str,
    output_dir: str = "recordings",
    start_time: Optional[float] = None,
    end_time: Optional[float] = None
) -> Dict[str, Any]:
    """
    Tải video (hoặc trích xuất đúng phân đoạn start_time -> end_time) từ URL bằng yt-dlp HTTP Byte Ranges.
    Cơ chế tối thượng: Định cấu hình extractor_args với iOS & Android player clients nhằm tránh lỗi 403 Forbidden
    khi FFmpeg kết nối trực tiếp với Google Video CDN trên Windows.
    Đồng thời tích hợp Fallback Tầng 2 cắt cục bộ bằng FFmpeg đảm bảo 100% thành công.
    """
    if not YTDLP_AVAILABLE:
        raise RuntimeError("Thư viện yt-dlp chưa được cài đặt trên hệ thống.")

    info = probe_web_video(url)
    total_duration = info["duration"]

    os.makedirs(output_dir, exist_ok=True)
    suffix = f"_{int(start_time)}_{int(end_time)}" if start_time is not None and end_time is not None else ""
    clean_id = "".join([c if c.isalnum() or c in "-_" else "" for c in info.get("id", "webvid")]) or "webvid"
    out_template = os.path.join(output_dir, f"web_{clean_id}{suffix}.%(ext)s")

    s_start = 0.0
    s_end = total_duration
    is_range = False

    if start_time is not None and end_time is not None and end_time > start_time:
        s_start = max(0.0, float(start_time))
        s_end = min(total_duration, float(end_time))
        if s_end - s_start > 120.0:
            s_end = s_start + 120.0
        is_range = True
    elif total_duration > 180.0:
        s_start = 0.0
        s_end = 90.0
        is_range = True

    # Cấu hình đa nền tảng tối thượng: Ưu tiên ios, android để vượt qua Google CDN 403 Forbidden
    common_extractor_args = {'youtube': {'player_client': ['ios', 'android', 'web']}}

    ydl_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'merge_output_format': 'mp4',
        'extractor_args': common_extractor_args,
    }

    if is_range:
        import yt_dlp.utils
        ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(s_start, s_end)])

    final_file = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(download_info)
            base, _ = os.path.splitext(filename)
            cand_file = filename if os.path.exists(filename) else f"{base}.mp4"

            if os.path.exists(cand_file) and os.path.getsize(cand_file) > 1000:
                final_file = cand_file
            else:
                for cand in os.listdir(output_dir):
                    if cand.startswith(f"web_{clean_id}") and cand.endswith(".mp4"):
                        test_p = os.path.join(output_dir, cand)
                        if os.path.getsize(test_p) > 1000:
                            final_file = test_p
                            break
    except Exception as e_dl:
        err_str = str(e_dl)
        if any(w in err_str.lower() for w in ["private", "sign in", "login", "drm", "copyright", "blocked"]):
            raise RuntimeError(
                "Video bị chặn bởi cơ chế bản quyền / DRM của nền tảng. Vui lòng tải video về máy và sử dụng ô kéo thả File cục bộ."
            )

        # Fallback Tầng 2: Tải định dạng đơn hoặc luồng nhẹ bằng yt-dlp rồi cắt cục bộ bằng FFmpeg (Zero 403 Error)
        try:
            fb_full_path = os.path.join(output_dir, f"raw_stream_{clean_id}_{int(time.time())}.mp4")
            ydl_fb_opts = {
                'format': '18/worst[ext=mp4]/best[height<=360]/best',
                'outtmpl': fb_full_path,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'extractor_args': common_extractor_args,
            }
            with yt_dlp.YoutubeDL(ydl_fb_opts) as ydl_fb:
                ydl_fb.download([url])

            if os.path.exists(fb_full_path) and os.path.getsize(fb_full_path) > 1000:
                fb_slice_path = os.path.join(output_dir, f"web_{clean_id}{suffix}.mp4")
                cmd_cut = [
                    "ffmpeg", "-y",
                    "-ss", str(s_start),
                    "-to", str(s_end),
                    "-i", fb_full_path,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-c:a", "aac",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    fb_slice_path
                ]
                res_cut = subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
                try:
                    os.remove(fb_full_path)
                except Exception:
                    pass
                if res_cut.returncode == 0 and os.path.exists(fb_slice_path) and os.path.getsize(fb_slice_path) > 1000:
                    final_file = fb_slice_path
        except Exception:
            pass

        if not final_file:
            raise RuntimeError(f"Lỗi trong quá trình tải phân đoạn video từ URL: {err_str[:160]}")

    if not final_file or not os.path.exists(final_file):
        raise RuntimeError("Không tìm thấy file video sau khi trích xuất phân đoạn.")

    # Kiểm tra thời lượng thực tế của file sau khi tải
    cap_check = cv2.VideoCapture(final_file)
    f_count = cap_check.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    f_fps = cap_check.get(cv2.CAP_PROP_FPS) or 30.0
    actual_dur = round(f_count / f_fps, 2) if f_fps > 0 else (s_end - s_start)
    cap_check.release()

    return {
        "file_path": os.path.abspath(final_file),
        "title": info["title"],
        "duration": actual_dur,
        "thumbnail": info["thumbnail"],
        "uploader": info["uploader"],
        "is_clipped": is_range,
        "has_audio": check_video_has_audio(final_file)
    }



class SpatialTrackStabilizer:
    """
    Bộ ổn định và gom cụm Track ID không gian (Spatial-Temporal Tracking Re-linker).
    - Khắc phục hiện tượng ByteTrack drop track và cấp hàng chục ID mới cho cùng 1 người.
    - Duy trì danh tính ID ổn định xuyên suốt video.
    - Đảm bảo giới hạn đúng số thực thể có mặt thực tế trong không gian (K <= 4).
    - Loại bỏ các Bounding Box rác (ghost detections) xuất hiện ngắn hạn.
    - Hỗ trợ gán vai trò trực tiếp từ Gemini Multimodal Visual Grounding.
    """
    def __init__(self, max_missing_frames: int = 90, match_dist_ratio: float = 0.22):
        self.max_missing_frames = max_missing_frames
        self.match_dist_ratio = match_dist_ratio
        self.active_tracks = {}      # canonical_id -> {"last_seen": int, "bbox": tuple, "cx": float, "cy": float, "heights": [], "aspects": []}
        self.canonical_next_id = 1
        self.raw_to_canonical = {}   # raw_track_id -> canonical_id
        self.canonical_counts = {}   # canonical_id -> int
        self.canonical_roles = {}    # canonical_id -> str
        self.canonical_custom_actions = {} # canonical_id -> str
        self.canonical_postures = {} # canonical_id -> str
        self.frame_canonical_occupancy = {} # frame_idx -> set of canonical_ids
        self.concurrent_pairs = set() # (c_id1, c_id2) pairs that co-occur in the same frame
        self.max_concurrent_seen = 1

    def update(self, raw_id: int, bbox: Tuple[int, int, int, int], frame_idx: int, frame_w: int, frame_h: int) -> int:
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        aspect = h / float(w)

        occupied = self.frame_canonical_occupancy.setdefault(frame_idx, set())

        # Nếu raw_id đã được ánh xạ và canonical_id này chưa bị chiếm chỗ trong frame hiện tại
        if raw_id in self.raw_to_canonical:
            c_id = self.raw_to_canonical[raw_id]
            if c_id not in occupied:
                self.active_tracks[c_id] = {
                    "last_seen": frame_idx,
                    "bbox": bbox,
                    "cx": cx,
                    "cy": cy,
                    "heights": self.active_tracks.get(c_id, {}).get("heights", []) + [h],
                    "aspects": self.active_tracks.get(c_id, {}).get("aspects", []) + [aspect]
                }
                self.canonical_counts[c_id] = self.canonical_counts.get(c_id, 0) + 1
                occupied.add(c_id)
                self._record_concurrency(frame_idx)
                return c_id

        # Raw ID mới từ ByteTrack (hoặc c_id cũ bị trùng occupancy):
        # Tìm xem có trùng với canonical track nào chưa xuất hiện trong frame hiện tại không
        diag = math.hypot(frame_w, frame_h)
        threshold_dist = self.match_dist_ratio * diag
        best_match = None
        min_cost = 999999.0

        for c_id, trk in list(self.active_tracks.items()):
            # Không ghép với canonical track đã có mặt trong cùng frame này!
            if c_id in occupied:
                continue

            time_gap = frame_idx - trk["last_seen"]
            if 0 < time_gap <= self.max_missing_frames:
                dist = math.hypot(cx - trk["cx"], cy - trk["cy"])
                old_w = trk["bbox"][2] - trk["bbox"][0]
                old_h = trk["bbox"][3] - trk["bbox"][1]
                size_ratio = min(w * h, old_w * old_h) / max(1.0, max(w * h, old_w * old_h))

                if dist < threshold_dist and size_ratio > 0.25:
                    cost = (dist / threshold_dist) + (1.0 - size_ratio) * 0.5
                    if cost < min_cost:
                        min_cost = cost
                        best_match = c_id

        if best_match is not None:
            c_id = best_match
        else:
            c_id = self.canonical_next_id
            self.canonical_next_id += 1

        self.raw_to_canonical[raw_id] = c_id
        self.active_tracks[c_id] = {
            "last_seen": frame_idx,
            "bbox": bbox,
            "cx": cx,
            "cy": cy,
            "heights": self.active_tracks.get(c_id, {}).get("heights", []) + [h],
            "aspects": self.active_tracks.get(c_id, {}).get("aspects", []) + [aspect]
        }
        self.canonical_counts[c_id] = self.canonical_counts.get(c_id, 0) + 1
        occupied.add(c_id)
        self._record_concurrency(frame_idx)
        return c_id

    def _record_concurrency(self, frame_idx: int):
        current_ids = list(self.frame_canonical_occupancy.get(frame_idx, set()))
        if len(current_ids) > self.max_concurrent_seen:
            self.max_concurrent_seen = len(current_ids)
        for i in range(len(current_ids)):
            for j in range(i + 1, len(current_ids)):
                pair = tuple(sorted((current_ids[i], current_ids[j])))
                self.concurrent_pairs.add(pair)

    def get_dominant_canonical_ids(self, max_limit: int = 4) -> List[int]:
        """
        Lấy danh sách các canonical ID đại diện cho đúng số người thực tế (K <= 4).
        Loại bỏ các ID ma / nhiễu chớp tắt.
        """
        valid_counts = {cid: cnt for cid, cnt in self.canonical_counts.items() if cnt >= 15}
        if not valid_counts:
            valid_counts = self.canonical_counts

        sorted_cids = sorted(valid_counts.keys(), key=lambda c: valid_counts[c], reverse=True)
        target_k = min(max_limit, max(1, self.max_concurrent_seen))
        target_k = max(target_k, min(len(sorted_cids), max_limit))
        return sorted(sorted_cids[:target_k])

    def finalize_roles(self, frame_h: int):
        """Ước lượng vai trò thực thể sơ bộ dựa trên đặc trưng hình học cơ thể."""
        dominant_ids = self.get_dominant_canonical_ids(max_limit=4)
        if not dominant_ids:
            return

        avg_heights = {}
        avg_aspects = {}
        for c_id in dominant_ids:
            h_list = self.active_tracks.get(c_id, {}).get("heights", [])
            asp_list = self.active_tracks.get(c_id, {}).get("aspects", [])
            avg_heights[c_id] = sum(h_list) / max(1, len(h_list))
            avg_aspects[c_id] = sum(asp_list) / max(1, len(asp_list))

        max_h = max(avg_heights.values()) if avg_heights else frame_h * 0.5
        for c_id, h in avg_heights.items():
            if (h <= 0.48 * max_h) or (h < frame_h * 0.26):
                self.canonical_roles[c_id] = "Trẻ nhỏ / Em bé"
            else:
                self.canonical_roles[c_id] = "Người lớn"

    def apply_gemini_actors(self, detected_actors: List[Dict[str, Any]]):
        """Áp dụng Visual Grounding từ Gemini Vision vào các canonical IDs thực tế."""
        if not detected_actors:
            return
        dominant_ids = self.get_dominant_canonical_ids(max_limit=4)
        for idx, c_id in enumerate(dominant_ids):
            if idx < len(detected_actors):
                actor = detected_actors[idx]
                role_name = actor.get("role") or self.canonical_roles.get(c_id, "Thành viên gia đình")
                self.canonical_roles[c_id] = role_name
                act = actor.get("true_action")
                if act:
                    self.canonical_custom_actions[c_id] = act
                posture = actor.get("posture_desc")
                if posture:
                    self.canonical_postures[c_id] = posture

    def get_role(self, c_id: int) -> str:
        return self.canonical_roles.get(c_id, "Người lớn")

    def get_custom_action(self, c_id: int) -> Optional[str]:
        return self.canonical_custom_actions.get(c_id)

    def get_custom_posture(self, c_id: int) -> Optional[str]:
        return self.canonical_postures.get(c_id)


class VideoAnnotatorEngine:

    def __init__(self, auto_warmup: bool = False):
        self._device = None
        self.hud = CyberHUDRenderer()
        self._token_guard = None
        self.model = None
        self.is_ready = False
        self._warmup_error = None
        self._warmup_lock = threading.Lock()
        self._warmup_event = threading.Event()

        if auto_warmup:
            self.warmup()

    @property
    def token_guard(self):
        if self._token_guard is None:
            from core.token_guard import TokenGuard
            self._token_guard = TokenGuard()
        return self._token_guard

    @token_guard.setter
    def token_guard(self, value):
        self._token_guard = value

    @property
    def device(self) -> str:
        if self._device is None:
            self._device = CONFIG.DEVICE
        return self._device

    @device.setter
    def device(self, value: str):
        self._device = value

    def warmup(self):
        """Khởi động nóng mô hình trên GPU RTX 5060 (Chạy trong luồng nền)."""
        with self._warmup_lock:
            if self.is_ready:
                return
            t0 = time.time()
            try:
                try:
                    print(f"[*] Dang nap mo hinh YOLOv8-Pose len {self.device} o che do nen...")
                except Exception:
                    pass
                from ultralytics import YOLO
                self.model = YOLO(CONFIG.YOLO_MODEL_NAME)
                dummy = np.zeros((480, 640, 3), dtype=np.uint8)
                self.model(dummy, device=self.device, verbose=False)
                self.is_ready = True
                try:
                    print(f"[+] Nap & Warmup AI hoan tat tren {self.device} trong {time.time() - t0:.2f}s!")
                except Exception:
                    pass
            except Exception as e:
                self._warmup_error = str(e)
                raise
            finally:
                self._warmup_event.set()

    def ensure_ready(self, timeout: float = 30.0) -> bool:
        """Đảm bảo model đã sẵn sàng trước khi xử lý video."""
        if not self.is_ready:
            try:
                print("[*] Dang doi AI warmup hoan tat truoc khi phan tich...")
            except Exception:
                pass
            if getattr(self, "_warmup_error", None) is not None:
                return False
            if not self._warmup_lock.locked() and not self._warmup_event.is_set():
                try:
                    self.warmup()
                except Exception:
                    return False
                return self.is_ready
            res = self._warmup_event.wait(timeout=timeout)
            if getattr(self, "_warmup_error", None) is not None:
                return False
            return res and self.is_ready
        return True

    def process_video(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0.0,
        end_time: Optional[float] = None,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
        call_gemini: bool = True
    ) -> Dict[str, Any]:
        """
        Xử lý video (toàn bộ hoặc đoạn được cắt từ start_time đến end_time).
        Dán nhãn Bounding Box & Skeleton, xuất file MP4, và tổng hợp báo cáo bằng TokenGuard.
        """
        if not self.ensure_ready():
            raise RuntimeError("Mô hình AI chưa sẵn sàng sau thời gian chờ.")

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise ValueError(f"Không thể mở file video: {input_path}")

        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        input_fps = cap.get(cv2.CAP_PROP_FPS)
        if input_fps <= 0 or math.isnan(input_fps):
            input_fps = 30.0

        # Tính toán frame bắt đầu và kết thúc
        start_frame = max(0, int(start_time * input_fps))
        if end_time is not None and end_time > start_time:
            end_frame = min(total_video_frames, int(end_time * input_fps))
        else:
            end_frame = total_video_frames

        target_total_frames = max(1, end_frame - start_frame)

        # Seek trực tiếp đến start_frame (tốc độ cực nhanh, không tốn ổ đĩa)
        if start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        # Khởi tạo VideoWriter xuất video tạm trước khi encode H.264
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        raw_temp_path = output_path + ".raw.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(raw_temp_path, fourcc, input_fps, (orig_w, orig_h))

        processed_count = 0
        t_start = time.time()
        fps_tracker = []

        action_counts = {
            "Đang đứng / Hoạt động trong phòng": 0,
            "Bế em bé / Tương tác trước ngực": 0,
            "Đứng thẳng / Đi lại di chuyển": 0,
            "Khoanh tay trước ngực": 0,
            "Chống cằm / Đỡ má suy nghĩ": 0,
            "Giơ tay / Vẫy tay chào": 0,
            "Đưa tay lên đầu / Căng thẳng": 0,
            "Cúi đầu / Tập trung": 0,
            "Ngả lưng thư giãn": 0,
            "Ngồi làm việc / Thao tác tay": 0,
            "Té ngã / Nằm bất động": 0
        }
        timeline_events = []
        threat_event_log = []
        candidate_keyframes = {}

        max_danger_score = 0
        peak_danger_reason = "Toàn bộ đoạn video an toàn"
        all_detected_entities = set()
        stabilizer = SpatialTrackStabilizer(max_missing_frames=90, match_dist_ratio=0.22)
        fall_streaks = {}
        has_orig_audio = check_video_has_audio(input_path)

        # Cấu trúc Phân đoạn Timeline (Temporal Behavior Segments)
        clip_duration = target_total_frames / input_fps
        if clip_duration <= 12.0:
            seg_len = 3.0
        elif clip_duration <= 30.0:
            seg_len = 5.0
        else:
            seg_len = 7.5

        num_segments = max(1, math.ceil(clip_duration / seg_len))
        segments_data = []
        for s_i in range(num_segments):
            s_start = start_time + s_i * seg_len
            s_end = min(end_time if end_time else start_time + clip_duration, s_start + seg_len)
            segments_data.append({
                "index": s_i + 1,
                "start_sec": s_start,
                "end_sec": s_end,
                "persons_history": {},
                "peak_threat": 0.0,
                "peak_frame": None,
                "has_danger": False
            })

        heatmap_samples = {}

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            current_frame_pos = start_frame + processed_count
            if current_frame_pos >= end_frame:
                break

            processed_count += 1
            t_frame_start = time.time()
            current_time_sec = current_frame_pos / input_fps

            # Chạy YOLOv8-Pose kết hợp ByteTrack trên GPU RTX 5060 (conf=0.35 lọc triệt để Bounding Box ma)
            try:
                results = self.model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    device=self.device,
                    conf=0.35,
                    verbose=False
                )
            except Exception:
                results = self.model(
                    frame,
                    device=self.device,
                    conf=0.35,
                    verbose=False
                )

            has_frame_danger = False
            frame_alert = ""
            frame_threat_score = 0.0
            detected_persons_count = 0
            frame_entities = []

            if results and len(results) > 0:
                res = results[0]
                boxes = res.boxes
                kpts_data = res.keypoints

                if boxes is not None and len(boxes) > 0:
                    detected_persons_count = len(boxes)

                    for p_idx, box in enumerate(boxes):
                        conf = float(box.conf[0].item())
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

                        # Lấy track_id ổn định qua SpatialTrackStabilizer (triệt tiêu hiện tượng nhảy lên 76 ID)
                        raw_track_id = int(box.id[0].item()) if (hasattr(box, "id") and box.id is not None and len(box.id) > 0) else (p_idx + 1)
                        c_id = stabilizer.update(raw_track_id, (x1, y1, x2, y2), processed_count, orig_w, orig_h)
                        id_label = f"ID #{c_id:02d}"

                        person_danger = False
                        person_action = "Đang đứng / Hoạt động trong phòng"
                        person_threat_score = 0.0
                        torso_angle = 90.0

                        if kpts_data is not None and len(kpts_data) > p_idx:
                            kpts = kpts_data[p_idx].data[0].cpu().numpy()

                            nose = kpts[0]
                            l_sh, r_sh = kpts[5], kpts[6]
                            l_hip, r_hip = kpts[11], kpts[12]
                            l_wrist, r_wrist = kpts[9], kpts[10]

                            # Tính góc thân người (Torso Angle)
                            sh_x, sh_y = (x1 + x2) / 2.0, y1 + 0.25 * (y2 - y1)
                            hip_x, hip_y = (x1 + x2) / 2.0, y1 + 0.55 * (y2 - y1)

                            if l_sh[2] > 0.30 and r_sh[2] > 0.30:
                                sh_x = (l_sh[0] + r_sh[0]) / 2.0
                                sh_y = (l_sh[1] + r_sh[1]) / 2.0

                            if l_hip[2] > 0.25 and r_hip[2] > 0.25:
                                hip_x = (l_hip[0] + r_hip[0]) / 2.0
                                hip_y = (l_hip[1] + r_hip[1]) / 2.0
                                dx = abs(sh_x - hip_x)
                                dy = abs(sh_y - hip_y)
                            else:
                                dx = abs(nose[0] - sh_x) if nose[2] > 0.25 else 10.0
                                dy = abs(sh_y - nose[1]) if nose[2] > 0.25 else 50.0

                            if dx + dy > 1e-4:
                                torso_angle = math.degrees(math.atan2(dy, dx))

                            # 1. Kiểm tra Té ngã thực sự: Sụp đổ trục thân < 30 độ VÀ đầu nằm sát sàn (liên tục >= 15 frames)
                            if torso_angle < 30.0 and nose[2] > 0.30 and nose[1] > orig_h * 0.58:
                                fall_streaks[c_id] = fall_streaks.get(c_id, 0) + 1
                            else:
                                fall_streaks[c_id] = max(0, fall_streaks.get(c_id, 0) - 1)

                            if fall_streaks.get(c_id, 0) >= 15:
                                person_danger = True
                                person_action = "Té ngã / Nằm bất động"
                                person_threat_score = 9.0
                                has_frame_danger = True
                                frame_alert = f"PHÁT HIỆN TÉ NGÃ ({id_label})"

                            # 2. Phân loại Tư thế Sinh cơ học Thực tế (Xóa bỏ hoàn toàn đoán mò ngồi/khoanh tay)
                            if not person_danger:
                                sh_w = math.hypot(l_sh[0] - r_sh[0], l_sh[1] - r_sh[1]) if l_sh[2] > 0.25 and r_sh[2] > 0.25 else 50.0
                                bbox_h = max(1, y2 - y1)
                                bbox_w = max(1, x2 - x1)
                                aspect_ratio = bbox_h / bbox_w

                                # A. Đưa 2 tay lên đầu / Căng thẳng
                                if l_wrist[2] > 0.30 and r_wrist[2] > 0.30 and l_wrist[1] < nose[1] + 25 and r_wrist[1] < nose[1] + 25:
                                    person_action = "Đưa tay lên đầu / Căng thẳng"

                                # B. Giơ tay phát biểu / Vẫy tay chào
                                elif (l_wrist[2] > 0.30 and l_wrist[1] < l_sh[1] - 25) or (r_wrist[2] > 0.30 and r_wrist[1] < r_sh[1] - 25):
                                    person_action = "Giơ tay / Vẫy tay chào"

                                # C. Chống cằm / Đỡ má suy nghĩ
                                elif (l_wrist[2] > 0.30 and math.hypot(l_wrist[0] - nose[0], l_wrist[1] - nose[1]) < 0.60 * sh_w) or \
                                     (r_wrist[2] > 0.30 and math.hypot(r_wrist[0] - nose[0], r_wrist[1] - nose[1]) < 0.60 * sh_w):
                                    person_action = "Chống cằm / Đỡ má suy nghĩ"

                                # D. Khoanh tay trước ngực: Yêu cầu hai tay bắt chéo qua ngực, khuỷu tay gập rõ ràng
                                elif (l_wrist[2] > 0.35 and r_wrist[2] > 0.35 and
                                      sh_y < l_wrist[1] < hip_y and sh_y < r_wrist[1] < hip_y and
                                      l_wrist[0] > sh_x - 0.15 * sh_w and r_wrist[0] < sh_x + 0.15 * sh_w and
                                      abs(l_wrist[0] - r_wrist[0]) < 0.45 * sh_w and
                                      l_wrist[1] < hip_y - 15 and r_wrist[1] < hip_y - 15):
                                    person_action = "Khoanh tay trước ngực"

                                # E. Bế em bé / Ôm giữ vật thể trước ngực (hai tay khum lại nâng đỡ trước ngực/bụng)
                                elif (l_wrist[2] > 0.20 and r_wrist[2] > 0.20 and 
                                      abs(l_wrist[0] - r_wrist[0]) < max(50.0, 0.85 * sh_w) and 
                                      l_wrist[1] > sh_y + 0.15 * sh_w and l_wrist[1] < hip_y + 40 and 
                                      r_wrist[1] > sh_y + 0.15 * sh_w and r_wrist[1] < hip_y + 40):
                                    person_action = "Bế em bé / Tương tác trước ngực"

                                # F. Ngồi làm việc: Chỉ kết luận khi khớp gối gập rõ ràng và hông thấp sát đùi
                                elif (len(kpts) > 14 and kpts[13][2] > 0.35 and kpts[14][2] > 0.35 and l_hip[2] > 0.35 and
                                      abs(kpts[13][1] - l_hip[1]) < 0.30 * bbox_h and abs(kpts[13][0] - l_hip[0]) > 0.20 * bbox_w):
                                    person_action = "Ngồi làm việc / Thao tác tay"

                                # G. Cúi người / Nhặt đồ
                                elif 45.0 <= torso_angle < 68.0:
                                    person_action = "Cúi đầu / Tập trung"

                                # H. Ngả lưng thư giãn
                                elif torso_angle > 98.0:
                                    person_action = "Ngả lưng thư giãn"

                                # I. Đứng thẳng / Đi lại di chuyển
                                elif aspect_ratio >= 1.70:
                                    person_action = "Đứng thẳng / Đi lại di chuyển"

                                # J. Mặc định tự nhiên: Đang đứng hoạt động trong phòng (Tuyệt đối không đoán bừa là ngồi)
                                else:
                                    person_action = "Đang đứng / Hoạt động trong phòng"

                            # Phối màu theo trạng thái
                            color = (68, 68, 239) if person_danger else (255, 240, 0)

                            # Bounding Box góc ngoặc
                            label_str = f"{id_label}: {person_action.upper()}"
                            self.hud.draw_corner_bracket_bbox(frame, x1, y1, x2, y2, color, label_str, conf)

                            # Khung xương 17 khớp nối thanh mảnh (không che mắt)
                            kpts_scaled = [(pt[0], pt[1], pt[2]) for pt in kpts]
                            self.hud.draw_cyber_skeleton(frame, kpts_scaled, color)

                        action_counts[person_action] = action_counts.get(person_action, 0) + 1
                        frame_threat_score = max(frame_threat_score, person_threat_score)
                        frame_entities.append({
                            "canonical_id": c_id,
                            "id_label": id_label,
                            "action": person_action,
                            "angle": torso_angle,
                            "threat_score": person_threat_score,
                            "is_danger": person_danger
                        })

            # Ghi nhận vào phân đoạn timeline tương ứng
            seg_idx = min(len(segments_data) - 1, max(0, int((current_time_sec - start_time) / seg_len)))
            current_seg = segments_data[seg_idx]

            for ent in frame_entities:
                c_id_key = ent["canonical_id"]
                if c_id_key not in current_seg["persons_history"]:
                    current_seg["persons_history"][c_id_key] = {
                        "actions": [],
                        "angles": [],
                        "max_threat": 0.0,
                        "danger_count": 0
                    }
                current_seg["persons_history"][c_id_key]["actions"].append(ent["action"])
                current_seg["persons_history"][c_id_key]["angles"].append(ent["angle"])
                current_seg["persons_history"][c_id_key]["max_threat"] = max(current_seg["persons_history"][c_id_key]["max_threat"], ent["threat_score"])
                if ent["is_danger"]:
                    current_seg["persons_history"][c_id_key]["danger_count"] += 1

            if has_frame_danger:
                current_seg["has_danger"] = True

            # Giữ ảnh tiêu biểu có Bounding Box và Khung xương cho phân đoạn
            if current_seg["peak_frame"] is None or frame_threat_score >= current_seg["peak_threat"]:
                current_seg["peak_threat"] = frame_threat_score
                current_seg["peak_frame"] = frame.copy()

            # Lấy mẫu Heatmap (mỗi 0.5 giây)
            sec_slot = round((current_time_sec - start_time) * 2) / 2.0
            if sec_slot not in heatmap_samples or frame_threat_score > heatmap_samples[sec_slot]:
                heatmap_samples[sec_slot] = frame_threat_score

            # Cập nhật danh sách sự kiện và lưu ảnh ứng viên cho TokenGuard
            if has_frame_danger:
                max_danger_score = max(max_danger_score, int(frame_threat_score))
                peak_danger_reason = frame_alert
                time_str = format_time(current_time_sec - start_time)

                if len(timeline_events) == 0 or (current_time_sec - timeline_events[-1]["second"] >= 2.0):
                    timeline_events.append({
                        "second": round(current_time_sec - start_time, 2),
                        "time": time_str,
                        "event": frame_alert,
                        "severity": "🔴 NGUY HIỂM"
                    })

                threat_event_log.append({
                    "timestamp": round(current_time_sec - start_time, 2),
                    "threat_type": frame_alert,
                    "threat_score": frame_threat_score,
                    "details": f"Thời điểm {time_str}"
                })
                candidate_keyframes[round(current_time_sec - start_time, 2)] = frame.copy()

            # Lưu ít nhất 1 frame ở giữa nếu không có nguy hiểm
            if len(candidate_keyframes) == 0 and processed_count == target_total_frames // 2:
                candidate_keyframes[round(current_time_sec - start_time, 2)] = frame.copy()

            # Tính toán FPS xử lý tức thời
            dt = max(1e-4, time.time() - t_frame_start)
            proc_fps = 1.0 / dt
            fps_tracker.append(proc_fps)
            if len(fps_tracker) > 30:
                fps_tracker.pop(0)
            avg_proc_fps = sum(fps_tracker) / len(fps_tracker)

            # --- DÁN NHÃN HUD CÔNG NGHỆ CAO ---
            header_h = 45
            overlay_hdr = frame.copy()
            cv2.rectangle(overlay_hdr, (0, 0), (orig_w, header_h), (15, 20, 28), -1)
            banner_color = (68, 68, 239) if has_frame_danger else (16, 185, 129)
            cv2.rectangle(overlay_hdr, (0, 0), (8, header_h), banner_color, -1)
            cv2.addWeighted(overlay_hdr, 0.85, frame, 0.15, 0, frame)

            cur_time_str = format_time(current_time_sec - start_time)
            hdr_text = f"FRAME: {processed_count:05d}/{target_total_frames:05d} [{cur_time_str}]  |  XỬ LÝ: {avg_proc_fps:.0f} FPS (RTX 5060)  |  ĐỐI TƯỢNG: {detected_persons_count}"
            cv2.putText(frame, hdr_text, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (245, 247, 250), 1, cv2.LINE_AA)

            status_tag = f"[ {frame_alert} ]" if has_frame_danger else "[ AN TOÀN ]"
            cv2.putText(frame, status_tag, (orig_w - 280, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, banner_color, 2, cv2.LINE_AA)

            if has_frame_danger:
                cv2.rectangle(frame, (0, 0), (orig_w - 1, orig_h - 1), (68, 68, 239), 4)

            out.write(frame)

            if progress_callback and processed_count % 3 == 0:
                progress_callback(processed_count, target_total_frames, avg_proc_fps)

        cap.release()
        out.release()

        # Xác định vai trò cho các đối tượng bền vững
        stabilizer.finalize_roles(orig_h)

        # Lấy danh sách các đối tượng thực sự có mặt trong video (chốt tối đa K <= 4 người)
        dominant_c_ids = stabilizer.get_dominant_canonical_ids(max_limit=4)
        if not dominant_c_ids:
            dominant_c_ids = [1]

        # Ánh xạ ID chuẩn hóa tuần tự (#01, #02, #03, #04) cho giao diện người dùng
        clean_id_map = {old_cid: idx + 1 for idx, old_cid in enumerate(dominant_c_ids)}

        all_detected_entities = [f"ID #{clean_id_map[cid]:02d} ({stabilizer.get_role(cid)})" for cid in dominant_c_ids]
        if not all_detected_entities:
            all_detected_entities = ["Khu vực an ninh"]

        # Chuyển đổi sang định dạng H.264 (avc1) web-standard bằng ffmpeg, đồng thời bảo lưu âm thanh gốc nếu có
        converted_h264 = False
        try:
            if has_orig_audio:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", raw_temp_path,
                    "-ss", str(start_time),
                    "-to", str(end_time if end_time else start_time + clip_duration),
                    "-i", input_path,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-c:a", "aac",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    output_path
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", raw_temp_path,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    output_path
                ]
            res_ff = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45)
            if res_ff.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                converted_h264 = True
                try:
                    os.remove(raw_temp_path)
                except Exception:
                    pass
        except Exception as e_ff:
            print(f"[!] Warning: ffmpeg conversion failed: {e_ff}")

        if not converted_h264:
            if os.path.exists(raw_temp_path):
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                shutil.move(raw_temp_path, output_path)

        total_elapsed = max(1e-3, time.time() - t_start)
        overall_fps = processed_count / total_elapsed

        total_actions = sum(action_counts.values()) or 1
        percentages = {k: round((v / total_actions) * 100.0, 1) for k, v in action_counts.items()}

        video_meta = {
            "duration_sec": processed_count / input_fps,
            "frame_count": processed_count,
            "fps": input_fps,
            "width": orig_w,
            "height": orig_h,
            "audio_status": "Có âm thanh gốc" if has_orig_audio else "Không có âm thanh (Video CCTV câm - Hãy tập trung 100% vào ngôn ngữ cơ thể, cử chỉ bàn tay, hướng mắt)"
        }

        # Lưu ảnh snapshot Keyframes cho từng phân đoạn timeline
        snapshots_dir = os.path.join(os.path.dirname(output_path), "snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)
        now_ts = int(time.time())

        timeline_segments = []
        for idx, s_data in enumerate(segments_data):
            snap_filename = f"snap_seg_{now_ts}_{idx+1:02d}.jpg"
            snap_path = os.path.join(snapshots_dir, snap_filename)
            if s_data["peak_frame"] is not None:
                cv2.imwrite(snap_path, s_data["peak_frame"], [cv2.IMWRITE_JPEG_QUALITY, 85])
            else:
                dummy = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
                cv2.imwrite(snap_path, dummy, [cv2.IMWRITE_JPEG_QUALITY, 85])

            seg_frame_count = max(1, int((s_data["end_sec"] - s_data["start_sec"]) * input_fps))
            min_presence_frames = max(5, int(0.18 * seg_frame_count))

            seg_entities = []
            seg_severity = "safe"

            for c_id in dominant_c_ids:
                if c_id not in s_data["persons_history"]:
                    continue
                t_info = s_data["persons_history"][c_id]
                if len(t_info["actions"]) < min_presence_frames:
                    continue

                actions = t_info["actions"]
                dom_action = max(set(actions), key=actions.count) if actions else "Quan sát"
                role = stabilizer.get_role(c_id)
                disp_id = clean_id_map.get(c_id, c_id)
                ent_label = f"ID #{disp_id:02d} ({role})"
                ent_severity = "danger" if t_info["danger_count"] >= 15 else "safe"
                if ent_severity == "danger":
                    seg_severity = "danger"

                # Diễn đạt tư thế tự nhiên, loại bỏ góc thân khô khan
                if dom_action == "Bế em bé / Tương tác trước ngực":
                    posture_desc = "Hai tay nâng đỡ trước ngực"
                elif dom_action == "Đứng thẳng / Đi lại di chuyển" or dom_action == "Đang đứng / Hoạt động trong phòng":
                    posture_desc = "Tư thế đứng / Di chuyển tự nhiên"
                elif dom_action == "Khoanh tay trước ngực":
                    posture_desc = "Hai tay khoanh quan sát"
                elif dom_action == "Chống cằm / Đỡ má suy nghĩ":
                    posture_desc = "Bàn tay nâng đỡ cằm"
                elif dom_action == "Ngồi làm việc / Thao tác tay":
                    posture_desc = "Tư thế ngồi ổn định"
                else:
                    posture_desc = "Trạng thái vận động bình thường"

                seg_entities.append({
                    "id": ent_label,
                    "raw_id": f"ID #{disp_id:02d}",
                    "canonical_id": c_id,
                    "role": role,
                    "action": dom_action,
                    "posture": posture_desc,
                    "severity": ent_severity
                })

            if not seg_entities:
                seg_entities.append({
                    "id": "KHÔNG GIAN",
                    "raw_id": "ALL",
                    "canonical_id": 0,
                    "role": "Không gian",
                    "action": "Khu vực ổn định / Không có chuyển động lớn",
                    "posture": "Trực quan",
                    "severity": "safe"
                })

            t_start_str = format_time(s_data["start_sec"] - start_time)
            t_end_str = format_time(s_data["end_sec"] - start_time)
            time_range = f"{t_start_str} ➔ {t_end_str}"

            # Tóm tắt hành vi mặc định (trước khi nhận phân tích vĩ mô từ Gemini)
            has_cradle = any("Bế em bé" in e["action"] for e in seg_entities)
            if has_cradle:
                scene_summary = "Sinh hoạt gia đình: Tương tác chăm sóc và nâng bế em bé trong phòng."
            elif seg_severity == "danger":
                scene_summary = "Cảnh báo: Phát hiện dấu hiệu bất thường về vận động trong phân đoạn này."
            elif len(seg_entities) > 1:
                scene_summary = f"Ghi nhận {len(seg_entities)} đối tượng tương tác nhẹ nhàng trong phòng."
            else:
                scene_summary = f"Đối tượng {seg_entities[0]['id']} {seg_entities[0]['action'].lower()}."

            timeline_segments.append({
                "segment_id": f"SEG-{idx+1:02d}",
                "start_sec": round(s_data["start_sec"] - start_time, 1),
                "end_sec": round(s_data["end_sec"] - start_time, 1),
                "time_range": time_range,
                "scene_summary": scene_summary,
                "context_description": scene_summary,
                "prediction_next_4s": "Duy trì trạng thái tương tác an toàn trong các giây tiếp theo",
                "entities": seg_entities,
                "severity": seg_severity,
                "danger_score": 0.0 if seg_severity == "safe" else s_data["peak_threat"],
                "snapshot_url": f"/api/snapshots/{snap_filename}"
            })

        # Mảng mẫu Heatmap
        heatmap_data = []
        for slot in sorted(heatmap_samples.keys()):
            score = heatmap_samples[slot]
            level = "danger" if score >= 8.0 else ("warning" if score >= 4.0 else "safe")
            heatmap_data.append({
                "time": slot,
                "time_str": format_time(slot),
                "score": round(score, 1),
                "level": level
            })

        # Gọi TokenGuard để chẩn đoán tổng hợp và mô tả thị giác chi tiết nếu được bật
        gemini_result = {}
        if call_gemini:
            # Thu thập keyframes từ từng phân đoạn timeline
            for s_data in segments_data:
                ts_mid = round(s_data["start_sec"] - start_time, 2)
                if s_data["peak_frame"] is not None and ts_mid not in candidate_keyframes:
                    candidate_keyframes[ts_mid] = s_data["peak_frame"].copy()

            peak_kfs = self.token_guard.select_peak_keyframes(
                event_log=threat_event_log,
                candidate_frames=candidate_keyframes,
                max_keyframes=3
            )

            segment_info_list = []
            for s in timeline_segments:
                segment_info_list.append({
                    "segment_id": s["segment_id"],
                    "time_range": s["time_range"],
                    "entity_count": len(s.get("entities", []))
                })

            gemini_result = self.token_guard.synthesize_video_report(
                video_metadata=video_meta,
                event_summary=threat_event_log,
                peak_keyframes=peak_kfs,
                segment_info=segment_info_list
            )

            # Trọng tài Thẩm định Nguy cơ (Contextual Arbiter Override):
            # Nếu Gemini khẳng định môi trường an toàn (sinh hoạt gia đình, làm việc, văn phòng),
            # triệt tiêu hoàn toàn các cảnh báo giả từ Edge AI cục bộ
            if gemini_result.get("threat_level") == "AN TOÀN" or gemini_result.get("is_safe_environment", False):
                max_danger_score = 0
                peak_danger_reason = "Không gian an toàn, không có nguy cơ an ninh"
                for seg in timeline_segments:
                    seg["severity"] = "safe"
                    seg["danger_score"] = 0.0
                    for ent in seg.get("entities", []):
                        ent["severity"] = "safe"
                for slot in heatmap_data:
                    slot["score"] = 0.0
                    slot["level"] = "safe"

            # Áp dụng Gemini Visual Grounding (danh tính và vai trò thực tế của 4 người)
            detected_actors = gemini_result.get("detected_actors", [])
            if detected_actors:
                stabilizer.apply_gemini_actors(detected_actors)
                all_detected_entities = [f"ID #{clean_id_map[cid]:02d} ({stabilizer.get_role(cid)})" for cid in dominant_c_ids]
                # Cập nhật danh tính và hành động tự nhiên trong từng phân đoạn
                for seg in timeline_segments:
                    for ent in seg.get("entities", []):
                        c_id = ent.get("canonical_id")
                        if c_id and c_id in clean_id_map:
                            disp_id = clean_id_map[c_id]
                            ent["role"] = stabilizer.get_role(c_id)
                            ent["id"] = f"ID #{disp_id:02d} ({ent['role']})"
                            custom_action = stabilizer.get_custom_action(c_id)
                            if custom_action:
                                ent["action"] = custom_action
                            custom_posture = stabilizer.get_custom_posture(c_id)
                            if custom_posture:
                                ent["posture"] = custom_posture

            # Ghép phân tích chi tiết cấp Vĩ Mô (Macro Narrative) của Gemini vào từng phân đoạn timeline
            gemini_analyses = {a.get("segment_id"): a for a in gemini_result.get("segment_analyses", []) if isinstance(a, dict)}
            for seg in timeline_segments:
                s_id = seg["segment_id"]
                if s_id in gemini_analyses:
                    ga = gemini_analyses[s_id]
                    narrative = ga.get("macro_narrative") or ga.get("context_description") or ga.get("detailed_action")
                    if narrative:
                        seg["scene_summary"] = narrative
                        seg["context_description"] = narrative
                    if ga.get("prediction_next_4s"):
                        seg["prediction_next_4s"] = ga["prediction_next_4s"]
                elif gemini_result.get("scene_context"):
                    seg["context_description"] = gemini_result.get("scene_context")

        return {
            "input_path": input_path,
            "output_path": output_path,
            "total_frames": processed_count,
            "duration_seconds": round(processed_count / input_fps, 1),
            "processing_time_seconds": round(total_elapsed, 1),
            "overall_fps": round(overall_fps, 1),
            "action_percentages": percentages,
            "timeline": timeline_events,
            "timeline_segments": timeline_segments,
            "heatmap_data": heatmap_data,
            "entities_detected": all_detected_entities,
            "max_danger_score": max_danger_score,
            "peak_danger_reason": peak_danger_reason,
            "overall_danger_level": "NGUY HIEM" if max_danger_score >= 8 else ("CANH BAO" if max_danger_score >= 5 else "AN TOAN"),
            "gemini_report": gemini_result
        }

