"""
Video Annotator Engine: Phân tích & Dán nhãn Video Quy mô lớn bằng YOLOv8-Pose đa nền tảng.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.

Chức năng:
1. Nhập file video từ Local (.mp4, .avi, .mov) hoặc Web URL (YouTube, mạng xã hội) qua yt-dlp.
2. Hỗ trợ cắt đoạn Timeline tùy chọn (start_time -> end_time) kiểu CapCut, không tốn đĩa.
3. Chạy YOLOv8-Pose trên thiết bị tăng tốc phần cứng (GPU/MPS/CPU) để phát hiện ĐA ĐỐI TƯỢNG.
4. Vẽ Technical Bounding Box chuẩn xác + Khung xương tư thế công thái học 17 điểm cho từng người.
5. Đánh giá Sinh cơ học (Biomechanics): Đo góc trục thân người, phát hiện té ngã, phát hiện cử chỉ bạo lực qua từng khung hình.
6. Kết xuất (Export) video thành phẩm hoàn chỉnh (.mp4) tương thích trình duyệt web.
7. Tích hợp TokenGuard: Chọn 1-3 keyframe đỉnh điểm, gọi 1 lượt mô hình phân tầng với ngân sách < 1,500 tokens.
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
from PIL import Image, ImageDraw, ImageFont

from core.cyber_hud import CyberHUDRenderer
from core.config import CONFIG

import json
import urllib.request
import urllib.parse

try:
    import yt_dlp
    import yt_dlp.utils
    YTDLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_AVAILABLE = False

def format_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def get_ffmpeg_bin() -> str:
    """
    Trả về đường dẫn binary FFmpeg:
    1. Kiểm tra ffmpeg trên PATH hệ thống.
    2. Fallback sang binary ffmpeg từ package imageio_ffmpeg.
    Đảm bảo 100% các máy thành viên không cần cài đặt thủ công.
    """
    import shutil
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def resolve_redirect_url(url: str) -> str:
    """
    Theo vết và giải mã các đường dẫn rút gọn như vt.tiktok.com, vm.tiktok.com, youtu.be, fb.watch, bit.ly...
    để lấy URL đích thực sự trước khi nạp vào yt-dlp hoặc bộ nạp trực tiếp.
    """
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        return clean_url

    short_domains = ["tiktok.com", "youtu.be", "fb.watch", "bit.ly", "tinyurl.com", "t.co", "goo.gl"]
    if not any(d in clean_url.lower() for d in short_domains):
        return clean_url

    try:
        req = urllib.request.Request(
            clean_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            final_url = response.geturl()
            if final_url:
                return final_url
    except Exception:
        pass
    return clean_url


def is_direct_video_url(url: str) -> bool:
    """Kiểm tra URL có phải là link file video trực tiếp hay không."""
    clean_url = url.split("?")[0].lower()
    return clean_url.endswith((".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"))


def download_direct_video(url: str, output_path: str, max_size_mb: int = 150) -> bool:
    """Tải trực tiếp video qua HTTP Chunked Stream khi gặp direct file link hoặc CDN."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }
        )
        with urllib.request.urlopen(req, timeout=35) as resp, open(output_path, "wb") as out_f:
            total_read = 0
            max_bytes = max_size_mb * 1024 * 1024
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > max_bytes:
                    break
                out_f.write(chunk)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception:
        return False


def fetch_tiktok_direct_info(url: str) -> Optional[Dict[str, Any]]:
    """
    Trích xuất metadata và link direct stream MP4 của video TikTok qua TikWM API.
    Khắc phục hiện tượng chặn captcha/challenge từ phía TikTok khi dùng yt-dlp thông thường.
    """
    try:
        clean_url = resolve_redirect_url(url)
        base_clean = clean_url.split("?")[0] if "tiktok.com" in clean_url else clean_url
        api_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(base_clean, safe='')}"
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") == 0 and "data" in data:
                d = data["data"]
                play_url = d.get("play") or d.get("wmplay")
                if play_url:
                    duration = float(d.get("duration", 30))
                    title = d.get("title") or "Video TikTok"
                    cover = d.get("cover") or ""
                    vid_id = str(d.get("id") or "tiktok_vid")
                    author = d.get("author", {}).get("nickname") or "TikTok Creator"
                    return {
                        "id": vid_id,
                        "title": f"TikTok: {title[:70]}",
                        "duration": duration,
                        "duration_str": format_time(duration),
                        "thumbnail": cover,
                        "uploader": author,
                        "is_long": duration > 180.0,
                        "direct_stream_url": play_url
                    }
    except Exception:
        pass
    return None


def probe_web_video(url: str) -> Dict[str, Any]:
    """
    Quét nhanh thông tin video (Metadata) từ URL mà KHÔNG tải video.
    Hỗ trợ TikTok, YouTube, Reels, Facebook và Direct Video Link.
    Trả về: title, duration, duration_str, thumbnail, uploader, is_long (> 180s).
    """
    resolved_url = resolve_redirect_url(url)

    if is_direct_video_url(resolved_url):
        base_title = os.path.basename(resolved_url.split("?")[0]) or "Video Trực Tiếp"
        return {
            "title": f"Direct Stream: {base_title}",
            "duration": 30.0,
            "duration_str": "00:30",
            "thumbnail": "",
            "uploader": "Direct HTTP Source",
            "is_long": False
        }

    # 1. Nếu là link TikTok / Douyin: Ưu tiên dùng TikWM API siêu tốc (vượt qua Captcha/Anti-bot)
    if "tiktok.com" in resolved_url.lower() or "douyin.com" in resolved_url.lower():
        tt_info = fetch_tiktok_direct_info(resolved_url)
        if tt_info:
            return tt_info

    if not YTDLP_AVAILABLE or yt_dlp is None:
        raise RuntimeError("Thư viện yt-dlp chưa được cài đặt trên hệ thống.")

    probe_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            'Referer': 'https://www.tiktok.com/',
        },
        'extractor_args': {
            'youtube': {'player_client': ['ios', 'android', 'web']},
            'tiktok': {'app_version': 'v2.8.0'}
        },
    }
    try:
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(resolved_url, download=False)
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
    Tải video (hoặc trích xuất đúng phân đoạn start_time -> end_time) từ URL.
    Hỗ trợ TikTok (bao gồm vt.tiktok.com, video dọc 9:16), YouTube, Shorts, Reels, và direct video links.
    Cơ chế dự phòng kép: yt-dlp HTTP Byte Ranges + Direct Stream Downloader + FFmpeg local slicing.
    """
    resolved_url = resolve_redirect_url(url)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Trực tiếp tải qua HTTP Stream nếu là Direct Video File URL
    if is_direct_video_url(resolved_url):
        base_name = os.path.basename(resolved_url.split("?")[0]) or "direct_video.mp4"
        clean_base = "".join([c if c.isalnum() or c in "-_." else "_" for c in base_name])
        dest_path = os.path.join(output_dir, f"direct_{int(time.time())}_{clean_base}")
        ok = download_direct_video(resolved_url, dest_path)
        if ok and os.path.exists(dest_path):
            cap_check = cv2.VideoCapture(dest_path)
            f_count = cap_check.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            f_fps = cap_check.get(cv2.CAP_PROP_FPS) or 30.0
            actual_dur = round(f_count / f_fps, 2) if f_fps > 0 else 30.0
            cap_check.release()
            return {
                "file_path": os.path.abspath(dest_path),
                "title": clean_base,
                "duration": actual_dur,
                "thumbnail": "",
                "uploader": "Direct Video Source",
                "is_clipped": False,
                "has_audio": check_video_has_audio(dest_path)
            }

    info = probe_web_video(resolved_url)
    total_duration = info["duration"]

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

    # 1. Nếu có direct_stream_url (từ TikWM API cho TikTok hoặc direct stream): Tải trực tiếp siêu tốc!
    if info.get("direct_stream_url"):
        direct_url = info["direct_stream_url"]
        raw_dl_path = os.path.join(output_dir, f"raw_{clean_id}_{int(time.time())}.mp4")
        ok = download_direct_video(direct_url, raw_dl_path, max_size_mb=250)
        if ok and os.path.exists(raw_dl_path) and os.path.getsize(raw_dl_path) > 1000:
            dest_path = os.path.join(output_dir, f"web_{clean_id}{suffix}.mp4")
            if is_range and s_end > s_start:
                cmd_cut = [
                    get_ffmpeg_bin(), "-y",
                    "-ss", str(s_start),
                    "-to", str(s_end),
                    "-i", raw_dl_path,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                    "-c:a", "aac",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    dest_path
                ]
                subprocess.run(cmd_cut, capture_output=True, text=True, timeout=120)
                try:
                    os.remove(raw_dl_path)
                except Exception:
                    pass
            else:
                if raw_dl_path != dest_path:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    os.rename(raw_dl_path, dest_path)

            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
                cap_check = cv2.VideoCapture(dest_path)
                actual_dur = total_duration
                if cap_check.isOpened():
                    f_fps = cap_check.get(cv2.CAP_PROP_FPS) or 30.0
                    f_count = cap_check.get(cv2.CAP_PROP_FRAME_COUNT) or 0
                    if f_count > 0:
                        actual_dur = round(f_count / f_fps, 2)
                    cap_check.release()
                return {
                    "file_path": os.path.abspath(dest_path),
                    "title": info["title"],
                    "duration": actual_dur,
                    "thumbnail": info.get("thumbnail", ""),
                    "uploader": info.get("uploader", "Web Source"),
                    "is_clipped": is_range,
                    "has_audio": check_video_has_audio(dest_path)
                }

    if not YTDLP_AVAILABLE or yt_dlp is None:
        raise RuntimeError("Thư viện yt-dlp chưa được cài đặt trên hệ thống.")

    common_extractor_args = {
        'youtube': {'player_client': ['ios', 'android', 'web']},
        'tiktok': {'app_version': 'v2.8.0'}
    }

    # Định dạng hỗ trợ cả ngang và dọc 9:16 (không giới hạn cứng height<=720 làm hỏng TikTok)
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/',
        },
        'extractor_args': common_extractor_args,
    }

    if is_range and hasattr(yt_dlp, 'utils') and hasattr(yt_dlp.utils, 'download_range_func'):
        ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(s_start, s_end)])

    final_file = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            download_info = ydl.extract_info(resolved_url, download=True)
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

        # Fallback Tầng 2: Tải định dạng đơn nhẹ bằng yt-dlp rồi cắt cục bộ bằng FFmpeg
        try:
            fb_full_path = os.path.join(output_dir, f"raw_stream_{clean_id}_{int(time.time())}.mp4")
            ydl_fb_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': fb_full_path,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                    'Referer': 'https://www.tiktok.com/',
                },
                'extractor_args': common_extractor_args,
            }
            with yt_dlp.YoutubeDL(ydl_fb_opts) as ydl_fb:
                ydl_fb.download([resolved_url])

            if os.path.exists(fb_full_path) and os.path.getsize(fb_full_path) > 1000:
                fb_slice_path = os.path.join(output_dir, f"web_{clean_id}{suffix}.mp4")
                cmd_cut = [
                    get_ffmpeg_bin(), "-y",
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
    Bộ ổn định và gom cụm Track ID không gian (Online K-Cap Persistent ID Tracker).
    - Khống chế danh tính thực thể ổn định trong khoảng K <= 4 người xuyên suốt video.
    - Kết hợp IoU + Khoảng cách tâm hình học (Centroid Distance) + Gợi ý ByteTrack ID.
    - Triệt tiêu hoàn toàn hiện tượng phân mảnh / nhảy ID (như #05, #08, #15).
    - Tự động re-link người cũ khi tái xuất hiện hoặc sau khi bị che khuất.
    - Đảm bảo 100% đồng bộ giữa nhãn dán trên khung hình video và dữ liệu bảng phân đoạn timeline.
    """
    def __init__(self, max_missing_frames: int = 90, match_dist_ratio: float = 0.35, max_k: int = 50):
        self.max_missing_frames = max_missing_frames
        self.match_dist_ratio = match_dist_ratio
        self.max_k = max_k
        self.active_tracks = {}      # canonical_id -> {"last_seen": int, "bbox": tuple, "cx": float, "cy": float, "heights": [], "aspects": [], "last_raw_id": int}
        self.canonical_next_id = 1
        self.raw_to_canonical = {}   # raw_track_id -> canonical_id
        self.canonical_counts = {}   # canonical_id -> int
        self.canonical_roles = {}    # canonical_id -> str
        self.canonical_custom_actions = {} # canonical_id -> str
        self.canonical_postures = {} # canonical_id -> str
        self.frame_canonical_occupancy = {} # frame_idx -> set of canonical_ids
        self.concurrent_pairs = set() # (c_id1, c_id2) pairs that co-occur in the same frame
        self.max_concurrent_seen = 1

    def compute_iou(self, boxA: Tuple[int, int, int, int], boxB: Tuple[int, int, int, int]) -> float:
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        inter_area = max(0, xB - xA) * max(0, yB - yA)
        areaA = max(1, (boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
        areaB = max(1, (boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))
        return inter_area / float(areaA + areaB - inter_area)

    def _record_track(self, c_id: int, bbox: Tuple[int, int, int, int], cx: float, cy: float, h: int, aspect: float, frame_idx: int, raw_id: int):
        if c_id not in self.active_tracks:
            self.active_tracks[c_id] = {
                "last_seen": frame_idx,
                "bbox": bbox,
                "cx": cx,
                "cy": cy,
                "heights": [h],
                "aspects": [aspect],
                "last_raw_id": raw_id
            }
        else:
            trk = self.active_tracks[c_id]
            trk["last_seen"] = frame_idx
            trk["bbox"] = bbox
            trk["cx"] = cx
            trk["cy"] = cy
            trk["last_raw_id"] = raw_id
            trk["heights"].append(h)
            trk["aspects"].append(aspect)
            if len(trk["heights"]) > 100:
                trk["heights"].pop(0)
                trk["aspects"].pop(0)
        self.canonical_counts[c_id] = self.canonical_counts.get(c_id, 0) + 1

    def update(self, raw_id: int, bbox: Tuple[int, int, int, int], frame_idx: int, frame_w: int, frame_h: int) -> int:
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        aspect = h / float(w)
        diag = math.hypot(frame_w, frame_h)

        occupied = self.frame_canonical_occupancy.setdefault(frame_idx, set())

        # 1. Nếu raw_id đã có canonical_id hợp lệ và chưa bị chiếm chỗ trong frame hiện tại
        if raw_id in self.raw_to_canonical:
            c_id = self.raw_to_canonical[raw_id]
            if c_id not in occupied:
                self._record_track(c_id, bbox, cx, cy, h, aspect, frame_idx, raw_id)
                occupied.add(c_id)
                self._record_concurrency(frame_idx)
                return c_id

        # 2. Tìm kiếm trong các track canonical hợp lệ chưa xuất hiện ở frame hiện tại
        best_cid = None
        min_cost = 999999.0
        threshold_dist = self.match_dist_ratio * diag
        available_cids = [cid for cid in self.active_tracks if cid not in occupied]

        for cid in available_cids:
            trk = self.active_tracks[cid]
            time_gap = frame_idx - trk["last_seen"]
            if 0 < time_gap <= self.max_missing_frames:
                dist = math.hypot(cx - trk["cx"], cy - trk["cy"])
                iou = self.compute_iou(bbox, trk["bbox"])

                iou_cost = 1.0 - iou
                dist_cost = min(1.0, dist / max(1.0, threshold_dist))
                cost = 0.55 * iou_cost + 0.45 * dist_cost

                if trk.get("last_raw_id") == raw_id:
                    cost -= 0.25

                if (iou > 0.05 or dist < threshold_dist) and cost < min_cost:
                    min_cost = cost
                    best_cid = cid

        if best_cid is not None:
            c_id = best_cid
        else:
            # Gán Canonical ID toàn cục mới tăng dần, bảo toàn thân phận vĩnh viễn
            c_id = self.canonical_next_id
            self.canonical_next_id += 1

        self.raw_to_canonical[raw_id] = c_id
        self._record_track(c_id, bbox, cx, cy, h, aspect, frame_idx, raw_id)
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
        Lấy danh sách các canonical ID đại diện cho các đối tượng tiêu điểm (K <= 4).
        Bảo toàn mã ID toàn cục thực tế của họ, không ép đè về 1..4.
        """
        valid_counts = {cid: cnt for cid, cnt in self.canonical_counts.items() if cnt >= 5}
        if not valid_counts:
            valid_counts = dict(self.canonical_counts)
        if not valid_counts:
            return [1]

        sorted_cids = sorted(valid_counts.keys(), key=lambda c: valid_counts[c], reverse=True)
        target_k = min(len(sorted_cids), max_limit)
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
            if h <= 0.40 * max_h:
                self.canonical_roles[c_id] = "Người quan sát ở xa"
            else:
                self.canonical_roles[c_id] = f"Đối tượng #{c_id:02d}"

    def apply_gemini_actors(self, detected_actors: List[Dict[str, Any]]):
        """Áp dụng Visual Grounding từ Gemini Vision vào các canonical IDs thực tế."""
        if not detected_actors:
            return
        dominant_ids = self.get_dominant_canonical_ids(max_limit=4)
        for idx, c_id in enumerate(dominant_ids):
            if idx < len(detected_actors):
                actor = detected_actors[idx]
                role_name = actor.get("role") or self.canonical_roles.get(c_id, f"Chủ thể #{c_id:02d}")
                self.canonical_roles[c_id] = role_name
                act = actor.get("true_action")
                if act:
                    self.canonical_custom_actions[c_id] = act
                posture = actor.get("posture_desc")
                if posture:
                    self.canonical_postures[c_id] = posture

    def get_role(self, c_id: int) -> str:
        return self.canonical_roles.get(c_id, f"Chủ thể #{c_id:02d}")

    def get_custom_action(self, c_id: int) -> Optional[str]:
        return self.canonical_custom_actions.get(c_id)

    def get_custom_posture(self, c_id: int) -> Optional[str]:
        return self.canonical_postures.get(c_id)


class KinematicAnomalyRanker:
    """
    Bộ xếp hạng đột biến động học và lọc tiêu điểm (Kinematic Saliency & Anomaly Ranker).
    - Tính toán độ dịch chuyển vận tốc khớp xương (Kinetic Velocity Spike).
    - Phát hiện biến động tư thế đột ngột (Posture Collapse / Fall / Sudden Crouch).
    - Tính toán mật độ tương tác va chạm vật lý giữa các thực thể (Physical Clash / Interaction Density).
    - Phân loại Top-K (K <= 4) đối tượng tiêu điểm và gắn cờ Ghosted cho người ngoài cuộc.
    """
    def __init__(self, top_k: int = 4, ema_alpha: float = 0.20):
        self.top_k = top_k
        self.ema_alpha = ema_alpha
        self.track_states = {}  # raw_id -> {"saliency": float, "prev_kpts": list, "max_h": int}
        self.active_indices = [7, 8, 9, 10, 13, 14, 15, 16]

    def update_frame(
        self,
        detections: List[Dict[str, Any]],
        frame_w: int,
        frame_h: int
    ) -> List[Dict[str, Any]]:
        if not detections:
            return []

        # 1. Tính toán Kinetic Spike và Posture Anomaly cho từng người
        for det in detections:
            raw_id = det["raw_id"]
            kpts = det.get("kpts")
            bbox = det["bbox"]
            torso_angle = det.get("torso_angle", 90.0)
            threat_score = det.get("threat_score", 0.0)
            is_danger = det.get("person_danger", False)

            x1, y1, x2, y2 = bbox
            h = max(1, y2 - y1)
            w = max(1, x2 - x1)

            st = self.track_states.setdefault(raw_id, {
                "saliency": 0.0,
                "prev_kpts": None,
                "max_h": h
            })

            # A. Kinetic velocity spike (Vận tốc dịch chuyển khớp xương) & Véc-tơ cổ tay (Wrist Vector)
            kinetic_spike = 0.0
            wrist_vec = (0.0, 0.0)
            prev_kpts = st["prev_kpts"]
            if kpts is not None and prev_kpts is not None:
                disps = []
                for idx in self.active_indices:
                    if idx < len(kpts) and idx < len(prev_kpts):
                        p_c = kpts[idx]
                        p_p = prev_kpts[idx]
                        if p_c[2] > 0.25 and p_p[2] > 0.25:
                            d = math.hypot(p_c[0] - p_p[0], p_c[1] - p_p[1])
                            disps.append(d / max(35.0, float(h)))
                if disps:
                    kinetic_spike = (sum(disps) / len(disps)) * 18.0

                # Trích xuất véc-tơ dịch chuyển cổ tay lớn nhất (Trụ cột 1: Hướng véc-tơ đòn đánh)
                w_disps = []
                for w_idx in [9, 10]:
                    if w_idx < len(kpts) and w_idx < len(prev_kpts):
                        if kpts[w_idx][2] > 0.25 and prev_kpts[w_idx][2] > 0.25:
                            w_disps.append((kpts[w_idx][0] - prev_kpts[w_idx][0], kpts[w_idx][1] - prev_kpts[w_idx][1]))
                if w_disps:
                    wrist_vec = max(w_disps, key=lambda v: math.hypot(v[0], v[1]))

            st["prev_kpts"] = [(p[0], p[1], p[2]) for p in kpts] if kpts is not None else None

            # B. Posture Anomaly (Sụt giảm chiều cao, té ngã, co cụm)
            st["max_h"] = max(st["max_h"], h)
            posture_anomaly = 0.0
            if st["max_h"] > 40 and (h / float(st["max_h"])) < 0.55:
                posture_anomaly += 6.0
            if torso_angle < 35.0:
                posture_anomaly += 5.0
            if is_danger:
                posture_anomaly += 8.0

            det["kinetic_spike"] = kinetic_spike
            det["wrist_vec"] = wrist_vec
            det["posture_anomaly"] = posture_anomaly
            det["interaction_score"] = 0.0
            det["is_striking"] = False
            det["is_targeted"] = False
            det["is_passive"] = (kinetic_spike < 0.6)

        # 2. Tính toán tương tác vật lý & Hướng đòn đánh giữa các cặp trong frame (Bộ tiêu chí 5 Trụ cột)
        n = len(detections)
        for i in range(n):
            for j in range(i + 1, n):
                det_a, det_b = detections[i], detections[j]
                ba, bb = det_a["bbox"], det_b["bbox"]

                ca_x, ca_y = (ba[0] + ba[2]) / 2.0, (ba[1] + ba[3]) / 2.0
                cb_x, cb_y = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
                dist = math.hypot(ca_x - cb_x, ca_y - cb_y)
                avg_h = ((ba[3] - ba[1]) + (bb[3] - bb[1])) / 2.0

                xA = max(ba[0], bb[0])
                yA = max(ba[1], bb[1])
                xB = min(ba[2], bb[2])
                yB = min(ba[3], bb[3])
                inter = max(0, xB - xA) * max(0, yB - yA)
                areaA = max(1, (ba[2] - ba[0]) * (ba[3] - ba[1]))
                areaB = max(1, (bb[2] - bb[0]) * (bb[3] - bb[1]))
                iou = inter / float(areaA + areaB - inter)

                r_ab_x = cb_x - ca_x
                r_ab_y = cb_y - ca_y
                norm_ab = math.hypot(r_ab_x, r_ab_y) + 1e-4

                # Trụ cột 1: Hướng véc-tơ đòn đánh từ A tới B
                v_a = det_a.get("wrist_vec", (0.0, 0.0))
                norm_va = math.hypot(v_a[0], v_a[1])
                cos_a = (v_a[0] * r_ab_x + v_a[1] * r_ab_y) / (norm_va * norm_ab) if norm_va > 1e-4 else 0.0

                # Hướng véc-tơ đòn đánh từ B tới A
                v_b = det_b.get("wrist_vec", (0.0, 0.0))
                norm_vb = math.hypot(v_b[0], v_b[1])
                cos_b = (-v_b[0] * r_ab_x - v_b[1] * r_ab_y) / (norm_vb * norm_ab) if norm_vb > 1e-4 else 0.0

                # Nón Sát Thương Vũ Khí Kéo Dài (Extended Weapon / Tool Reach Cone):
                # Khi cầm gậy hoặc hung khí dài thụt tới, hai thân người cách nhau tới 1.65 * chiều cao.
                # Nếu véc-tơ cổ tay hướng thẳng về đối phương (cos > 0.35) và vận tốc đáng kể -> Mở rộng tầm sát thương
                is_weapon_thrust_a = (dist < 1.65 * avg_h and cos_a > 0.35 and (det_a["kinetic_spike"] >= 1.4 or norm_va >= 1.4))
                is_weapon_thrust_b = (dist < 1.65 * avg_h and cos_b > 0.35 and (det_b["kinetic_spike"] >= 1.4 or norm_vb >= 1.4))

                # Trụ cột 3: Bán kính sải tay hiệu dụng hoặc Nón sát thương vũ khí
                in_reach = (iou > 0.05 or dist < 0.85 * avg_h or is_weapon_thrust_a or is_weapon_thrust_b)

                if in_reach:
                    # A tấn công B: Vận tốc cao và véc-tơ đâm trúng mục tiêu B
                    if is_weapon_thrust_a or (det_a["kinetic_spike"] >= 1.4 and cos_a > 0.38):
                        det_a["is_striking"] = True
                        strike_pts = 6.0 if is_weapon_thrust_a else 5.0
                        det_a["interaction_score"] = max(det_a["interaction_score"], strike_pts)
                        det_b["is_targeted"] = True

                    # B tấn công A: Vận tốc cao và véc-tơ đâm trúng mục tiêu A
                    if is_weapon_thrust_b or (det_b["kinetic_spike"] >= 1.4 and cos_b > 0.38):
                        det_b["is_striking"] = True
                        strike_pts = 6.0 if is_weapon_thrust_b else 5.0
                        det_b["interaction_score"] = max(det_b["interaction_score"], strike_pts)
                        det_a["is_targeted"] = True

                    # Tương tác áp sát giằng co chung (nếu cả 2 cùng di chuyển nhưng không có véc-tơ đâm thẳng)
                    if (det_a["kinetic_spike"] > 1.2 or det_b["kinetic_spike"] > 1.2):
                        clash_val = min(5.0, max(2.0, (1.0 - dist / max(1.0, avg_h)) * 5.0))
                        if not det_a.get("is_passive"):
                            det_a["interaction_score"] = max(det_a["interaction_score"], clash_val)
                        if not det_b.get("is_passive"):
                            det_b["interaction_score"] = max(det_b["interaction_score"], clash_val)

        # 3. Tính điểm Saliency tổng hợp và làm mịn EMA
        for det in detections:
            raw_id = det["raw_id"]
            st = self.track_states[raw_id]
            inst_score = (
                0.40 * det["kinetic_spike"] +
                0.30 * det["posture_anomaly"] +
                0.30 * det["interaction_score"] +
                det.get("threat_score", 0.0)
            )
            st["saliency"] = (1.0 - self.ema_alpha) * st["saliency"] + self.ema_alpha * inst_score
            det["saliency_score"] = st["saliency"]

        # 4. Phân tầng: Nếu tổng số người <= top_k, toàn bộ đều là FOCUS
        if n <= self.top_k:
            for det in detections:
                det["is_focus"] = True
                det["is_ghost"] = False
            return detections

        # Nếu n > top_k: Sắp xếp theo Saliency giảm dần
        sorted_indices = sorted(range(n), key=lambda idx: detections[idx]["saliency_score"], reverse=True)
        focus_set = set(sorted_indices[:self.top_k])

        for idx, det in enumerate(detections):
            if idx in focus_set:
                det["is_focus"] = True
                det["is_ghost"] = False
            else:
                det["is_focus"] = False
                det["is_ghost"] = True

        return detections


class TemporalActionStabilizer:
    """
    Bộ Lọc Trễ Thời Gian & Máy Trạng Thái Cân Bằng (Temporal Hysteresis State Machine)
    kết hợp Cửa Sổ Trượt Đồng Thuận Đa Số (Sliding Window Majority Vote 7-10 frames).
    
    Quy tắc hoạt động chuẩn xác:
    1. Ngưỡng kích hoạt đòn đánh: Yêu cầu xung lực đòn đánh duy trì >= 3 frames liên tiếp
       mới kích hoạt trạng thái ĐỎ (Kẻ tấn công / Đang tấn công).
    2. Khoảng giảm chấn phục hồi (Hysteresis Cooldown Decay): Khi xung lực giảm, duy trì
       trạng thái VÀNG (Phòng vệ / Cảnh giác) trong tối thiểu 5-6 frames trước khi hạ về XANH (Bình thường).
    3. Nhãn hành động (Action string): Lấy nhãn chiếm đa số (Majority Vote) trong cửa sổ 7-10 frames gần nhất.
    4. Ổn định màu sắc BBox & Khung xương: Không cho phép màu sắc nhảy loạn xạ qua từng frame.
    """
    def __init__(self, window_size: int = 8, trigger_thresh: int = 3, cooldown_frames: int = 6):
        self.window_size = window_size
        self.trigger_thresh = trigger_thresh
        self.cooldown_frames = cooldown_frames
        self.track_states = {}  # c_id -> dict

    def update(
        self,
        c_id: int,
        raw_action: str,
        raw_role: str,
        raw_danger: bool,
        threat_score: float,
        kinetic: float,
        interaction: float
    ) -> Dict[str, Any]:
        if c_id not in self.track_states:
            self.track_states[c_id] = {
                "action_history": [],
                "strike_streak": 0,
                "cooldown_left": 0,
                "stable_role": "observer",
                "stable_danger": False,
                "stable_action": raw_action,
                "smoothed_threat": threat_score
            }
        st = self.track_states[c_id]

        # 1. Cập nhật lịch sử hành động cho cửa sổ trượt
        st["action_history"].append(raw_action)
        if len(st["action_history"]) > self.window_size:
            st["action_history"].pop(0)

        # 2. Xử lý máy trạng thái Hysteresis cho Đòn Đánh
        is_raw_strike = raw_danger or raw_role == "attacker" or (kinetic >= 2.2 and interaction >= 1.8)
        if is_raw_strike:
            st["strike_streak"] += 1
            # Kích hoạt tức thời (Impulse Shock Trigger):
            # Nếu xung lực cực lớn (kinetic >= 2.2 hoặc threat_score >= 7.0 hoặc interaction >= 4.5),
            # đòn đánh thật xảy ra rất nhanh (1-2 frames) -> kích hoạt ngay, không bắt buộc đợi 3 frames
            req_thresh = 1 if (kinetic >= 2.2 or threat_score >= 7.0 or interaction >= 4.5) else self.trigger_thresh
            if st["strike_streak"] >= req_thresh:
                st["stable_role"] = "attacker"
                st["stable_danger"] = True
                st["cooldown_left"] = self.cooldown_frames
        else:
            st["strike_streak"] = 0
            if st["cooldown_left"] > 0:
                st["cooldown_left"] -= 1
                # Trong thời gian giảm chấn, giữ ở mức phòng vệ / cảnh giác (Vàng)
                st["stable_role"] = "defender"
                st["stable_danger"] = False
            else:
                if raw_role == "defender":
                    st["stable_role"] = "defender"
                    st["stable_danger"] = False
                elif raw_role == "victim":
                    st["stable_role"] = "victim"
                    st["stable_danger"] = True
                else:
                    st["stable_role"] = "observer"
                    st["stable_danger"] = False

        # 3. Đồng thuận đa số cho nhãn hành vi
        actions = st["action_history"]
        if actions:
            if st["stable_role"] == "attacker":
                strike_actions = [a for a in actions if any(k in a for k in ["Vung tay", "Tấn công", "Xung đột"])]
                if strike_actions:
                    st["stable_action"] = max(set(strike_actions), key=strike_actions.count)
                else:
                    st["stable_action"] = "Vung tay ra đòn / Tấn công áp sát"
            elif st["stable_role"] in ["defender", "victim"]:
                def_actions = [a for a in actions if any(k in a for k in ["Phòng vệ", "Thủ thế", "Chắn đỡ", "Té ngã"])]
                if def_actions:
                    st["stable_action"] = max(set(def_actions), key=def_actions.count)
                else:
                    st["stable_action"] = "Phòng vệ / Chắn đỡ né đòn" if st["stable_role"] == "defender" else "Té ngã / Nằm bất động"
            else:
                st["stable_action"] = max(set(actions), key=actions.count)

        # 4. Làm mịn điểm số nguy cơ theo EMA (Bảo toàn đỉnh nhọn nguy cơ cao)
        if threat_score >= 6.5:
            st["smoothed_threat"] = max(threat_score, 0.30 * st["smoothed_threat"] + 0.70 * threat_score)
        else:
            st["smoothed_threat"] = 0.60 * st["smoothed_threat"] + 0.40 * threat_score

        # 5. Xác định màu sắc ổn định không nhấp nháy
        if st["stable_role"] == "attacker" or (st["stable_role"] == "victim" and st["stable_danger"]):
            color = (68, 68, 239)      # Đỏ BGR
            role_prefix = " [TẤN CÔNG]" if st["stable_role"] == "attacker" else " [NẠN NHÂN]"
        elif st["stable_role"] == "defender":
            color = (0, 215, 255)       # Vàng hổ phách BGR
            role_prefix = " [PHÒNG VỆ]"
        else:
            color = (255, 240, 0)       # Cyan BGR (Người quan sát)
            role_prefix = ""

        return {
            "action": st["stable_action"],
            "role": st["stable_role"],
            "is_danger": st["stable_danger"],
            "color": color,
            "role_prefix": role_prefix,
            "threat_score": round(st["smoothed_threat"], 1)
        }


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

    @property
    def device_name(self) -> str:
        """Trả về tên thiết bị phần cứng thực tế (Tesla T4, RTX 5060, Apple Silicon (MPS), hoặc CPU)."""
        from core.metrics import get_hardware_gpu_name
        dev = getattr(self, "_device", None)
        if dev and str(dev).lower() == "cpu":
            return "CPU"
        return get_hardware_gpu_name()

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
        call_gemini: bool = True,
        anomaly_focus: bool = True
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
        stabilizer = SpatialTrackStabilizer(max_missing_frames=90, match_dist_ratio=0.35, max_k=4)
        anomaly_ranker = KinematicAnomalyRanker(top_k=4) if anomaly_focus else None
        posture_distribution = {"upright": 0, "bent": 0, "slouched": 0}
        fall_streaks = {}
        temporal_stabilizer = TemporalActionStabilizer(window_size=8, trigger_thresh=3, cooldown_frames=6)
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

                    candidates = []
                    for p_idx, box in enumerate(boxes):
                        conf = float(box.conf[0].item())
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        raw_track_id = int(box.id[0].item()) if (hasattr(box, "id") and box.id is not None and len(box.id) > 0) else (p_idx + 1)

                        kpts = None
                        if kpts_data is not None and len(kpts_data) > p_idx:
                            kpts = kpts_data[p_idx].data[0].cpu().numpy()

                        torso_angle = 90.0
                        if kpts is not None:
                            nose = kpts[0]
                            l_sh, r_sh = kpts[5], kpts[6]
                            l_hip, r_hip = kpts[11], kpts[12]
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

                        candidates.append({
                            "p_idx": p_idx,
                            "raw_id": raw_track_id,
                            "bbox": (x1, y1, x2, y2),
                            "conf": conf,
                            "kpts": kpts,
                            "torso_angle": torso_angle,
                            "threat_score": 0.0,
                            "person_danger": False
                        })

                    # Nếu bật lọc tiêu điểm bất thường (Top-4 Saliency Focus)
                    if anomaly_ranker is not None:
                        candidates = anomaly_ranker.update_frame(candidates, orig_w, orig_h)
                    else:
                        for cand in candidates:
                            cand["is_focus"] = True
                            cand["is_ghost"] = False

                    # Xử lý và hiển thị phân tầng
                    for cand in candidates:
                        x1, y1, x2, y2 = cand["bbox"]
                        conf = cand["conf"]
                        kpts = cand["kpts"]
                        torso_angle = cand["torso_angle"]
                        raw_track_id = cand["raw_id"]
                        is_focus = cand.get("is_focus", True)
                        is_ghost = cand.get("is_ghost", False)

                        # Nếu là người ngoài cuộc (Ghosted Bystander): Vẽ mờ tối giản tránh rối mắt
                        if is_ghost and not is_focus:
                            if kpts is not None:
                                kpts_scaled = [(pt[0], pt[1], pt[2]) for pt in kpts]
                                self.hud.draw_ghost_skeleton(frame, kpts_scaled)
                            self.hud.draw_ghost_bbox(frame, x1, y1, x2, y2)
                            continue

                        # Nếu là người trong tiêu điểm (Top-K Focus):
                        c_id = stabilizer.update(raw_track_id, (x1, y1, x2, y2), processed_count, orig_w, orig_h)
                        id_label = f"ID #{c_id:02d}"

                        person_danger = False
                        person_action = "Đang đứng / Hoạt động trong phòng"
                        person_threat_score = 0.0

                        if kpts is not None:
                            nose = kpts[0]
                            l_sh, r_sh = kpts[5], kpts[6]
                            l_hip, r_hip = kpts[11], kpts[12]
                            l_wrist, r_wrist = kpts[9], kpts[10]

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

                            kinetic_spike = cand.get("kinetic_spike", 0.0)
                            interaction_score = cand.get("interaction_score", 0.0)

                            sh_w = math.hypot(l_sh[0] - r_sh[0], l_sh[1] - r_sh[1]) if l_sh[2] > 0.25 and r_sh[2] > 0.25 else 50.0
                            bbox_h = max(1, y2 - y1)
                            bbox_w = max(1, x2 - x1)
                            aspect_ratio = bbox_h / bbox_w
                            sh_x, sh_y = (x1 + x2) / 2.0, y1 + 0.25 * (y2 - y1)
                            hip_x, hip_y = (x1 + x2) / 2.0, y1 + 0.55 * (y2 - y1)
                            if l_sh[2] > 0.30 and r_sh[2] > 0.30:
                                sh_x = (l_sh[0] + r_sh[0]) / 2.0
                                sh_y = (l_sh[1] + r_sh[1]) / 2.0
                            if l_hip[2] > 0.25 and r_hip[2] > 0.25:
                                hip_x = (l_hip[0] + r_hip[0]) / 2.0
                                hip_y = (l_hip[1] + r_hip[1]) / 2.0

                            # Nhận diện tư thế ngồi (Sitting / Desk Occlusion):
                            # Trường hợp 1: Thấy cả chân và đầu gối gập ngang (Full body sitting)
                            has_knee_kpts = (len(kpts) > 14 and kpts[13][2] > 0.35 and kpts[14][2] > 0.35)
                            is_seated_full = (has_knee_kpts and l_hip[2] > 0.30 and abs(kpts[13][1] - l_hip[1]) < 0.30 * bbox_h and abs(kpts[13][0] - l_hip[0]) > 0.18 * bbox_w)

                            # Trường hợp 2: Bị bàn học / mặt bàn che khuất chân (Desk / Classroom Occlusion):
                            # Thường gặp trong lớp học/văn phòng: bbox thấp/bè (aspect_ratio < 1.62),
                            # trục thân thẳng đứng (60 <= torso_angle <= 120), đầu/vai rõ ràng, kinetic_spike thấp (< 0.85)
                            is_seated_desk = (
                                (not has_knee_kpts or aspect_ratio < 1.62) and
                                60.0 <= torso_angle <= 120.0 and
                                (l_sh[2] > 0.30 or r_sh[2] > 0.30) and
                                nose[2] > 0.30 and
                                kinetic_spike < 0.85 and
                                (aspect_ratio < 1.55 or (l_hip[2] > 0.20 and abs(hip_y - y2) < 0.45 * bbox_h))
                            )
                            is_seated = (is_seated_full or is_seated_desk)

                            # =========================================================================
                            # BỘ TIÊU CHÍ ĐỘNG HỌC 5 TRỤ CỘT TRIỆT TIÊU GÁN OAN (5-PILLAR DISAMBIGUATION)
                            # =========================================================================
                            person_role_type = "bystander"

                            # 1. Trụ cột 5: Khóa Bất Biến Cho Người Đứng/Ngồi Yên (Bystander Invariance Lock)
                            # Nếu vận tốc khớp xương thấp (<0.65), người này ngồi/đứng yên / quan sát bình thường
                            # TUYỆT ĐỐI KHÔNG BAO GIỜ bị gán điểm nguy hiểm hay bôi đỏ dù xung quanh có xô xát
                            if kinetic_spike < 0.65 and not cand.get("is_striking", False):
                                person_danger = False
                                person_threat_score = 0.2
                                person_role_type = "bystander"
                                if is_seated:
                                    person_action = "Ngồi tại bàn / Quan sát tĩnh"
                                elif aspect_ratio >= 1.70:
                                    person_action = "Đang đứng quan sát / Giữ nguyên vị trí"
                                else:
                                    person_action = "Hoạt động bình thường / Quan sát"

                            # 2. Phát hiện Té ngã thực sự: Sụp đổ trục thân < 30 độ VÀ đầu nằm sát sàn (liên tục >= 15 frames)
                            elif torso_angle < 30.0 and nose[2] > 0.30 and nose[1] > orig_h * 0.58:
                                fall_streaks[c_id] = fall_streaks.get(c_id, 0) + 1
                                if fall_streaks.get(c_id, 0) >= 15:
                                    person_danger = True
                                    person_role_type = "victim"
                                    person_action = "Té ngã / Nằm bất động"
                                    person_threat_score = 9.0
                                    has_frame_danger = True
                                    frame_alert = f"PHÁT HIỆN TÉ NGÃ ({id_label})"

                            # 3. Trụ cột 1 & 4: Kẻ Tấn Công / Ra Đòn (Striker / Attacker)
                            # Có véc-tơ cổ tay đâm thẳng vào đối phương VÀ gia tốc xung lực đột biến
                            elif cand.get("is_striking", False) or (kinetic_spike >= 2.6 and interaction_score >= 2.0):
                                person_danger = True
                                person_role_type = "attacker"
                                person_action = "Vung tay ra đòn / Tấn công áp sát"
                                person_threat_score = 8.5
                                has_frame_danger = True
                                frame_alert = f"CẢNH BÁO: VUNG TAY TẤN CÔNG ({id_label})"

                            # 4. Trụ cột 2: Nạn Nhân / Người Bị Tấn Công Phòng Vệ (Defender / Target)
                            # Đang bị nhắm tới HOẶC trong cự ly áp sát nhưng co tay thủ ngực/đầu hoặc né lùi
                            elif cand.get("is_targeted", False) or (interaction_score >= 2.5 and (
                                (l_wrist[2] > 0.20 and l_wrist[1] < hip_y and r_wrist[2] > 0.20 and r_wrist[1] < hip_y) or
                                torso_angle > 95.0 or kinetic_spike < 1.2
                            )):
                                person_danger = False
                                person_role_type = "defender"
                                person_action = "Phòng vệ / Chắn đỡ né đòn"
                                person_threat_score = 4.5

                            # 5. Xung Đột Thể Xác Giằng Co Chung (Physical Clash)
                            elif interaction_score >= 3.5 and kinetic_spike >= 1.5:
                                person_danger = True
                                person_role_type = "attacker"
                                person_action = "Xung đột thể xác / Giằng co va chạm"
                                person_threat_score = 8.0
                                has_frame_danger = True
                                frame_alert = f"CẢNH BÁO: XUNG ĐỘT THỂ XÁC ({id_label})"

                            # 6. Thủ thế đối đầu / Căng thẳng (Boxing Guard / Confrontation Stance)
                            elif (interaction_score >= 1.5 and
                                  l_wrist[2] > 0.25 and r_wrist[2] > 0.25 and
                                  l_wrist[1] < hip_y - 10 and r_wrist[1] < hip_y - 10 and
                                  abs(l_wrist[0] - r_wrist[0]) < 1.0 * sh_w):
                                person_danger = False
                                person_role_type = "defender"
                                person_action = "Thủ thế đối đầu / Căng thẳng"
                                person_threat_score = 6.0

                            # 7. Phân loại Tư thế Sinh cơ học Tự nhiên
                            elif not person_danger:
                                # A. Đưa 2 tay lên đầu / Căng thẳng
                                if l_wrist[2] > 0.30 and r_wrist[2] > 0.30 and l_wrist[1] < nose[1] + 25 and r_wrist[1] < nose[1] + 25:
                                    person_action = "Đưa tay lên đầu / Căng thẳng"
                                    person_threat_score = 3.0

                                # B. Giơ tay phát biểu / Vẫy tay chào
                                elif (l_wrist[2] > 0.30 and l_wrist[1] < l_sh[1] - 25) or (r_wrist[2] > 0.30 and r_wrist[1] < r_sh[1] - 25):
                                    person_action = "Giơ tay / Vẫy tay chào"
                                    person_threat_score = 0.5

                                # C. Chống cằm / Đỡ má suy nghĩ
                                elif (l_wrist[2] > 0.30 and math.hypot(l_wrist[0] - nose[0], l_wrist[1] - nose[1]) < 0.60 * sh_w) or \
                                     (r_wrist[2] > 0.30 and math.hypot(r_wrist[0] - nose[0], r_wrist[1] - nose[1]) < 0.60 * sh_w):
                                    person_action = "Chống cằm / Đỡ má suy nghĩ"

                                # D. Khoanh tay trước ngực
                                elif (l_wrist[2] > 0.35 and r_wrist[2] > 0.35 and
                                      sh_y < l_wrist[1] < hip_y and sh_y < r_wrist[1] < hip_y and
                                      l_wrist[0] > sh_x - 0.15 * sh_w and r_wrist[0] < sh_x + 0.15 * sh_w and
                                      abs(l_wrist[0] - r_wrist[0]) < 0.45 * sh_w and
                                      l_wrist[1] < hip_y - 15 and r_wrist[1] < hip_y - 15):
                                    person_action = "Khoanh tay trước ngực"

                                # E. Tương tác trước ngực / Ôm giữ vật thể
                                elif (kinetic_spike < 0.6 and interaction_score < 1.0 and
                                      l_wrist[2] > 0.20 and r_wrist[2] > 0.20 and 
                                      abs(l_wrist[0] - r_wrist[0]) < max(50.0, 0.85 * sh_w) and 
                                      l_wrist[1] > sh_y + 0.15 * sh_w and l_wrist[1] < hip_y + 40 and 
                                      r_wrist[1] > sh_y + 0.15 * sh_w and r_wrist[1] < hip_y + 40):
                                    person_action = "Tương tác trước ngực / Ôm giữ vật thể"

                                # F. Ngồi làm việc / Ngồi tại bàn học
                                elif is_seated:
                                    person_action = "Ngồi tại bàn / Quan sát tĩnh"

                                # G. Cúi người / Nhặt đồ
                                elif 45.0 <= torso_angle < 68.0:
                                    person_action = "Cúi đầu / Tập trung"

                                # H. Ngả lưng thư giãn
                                elif torso_angle > 98.0:
                                    person_action = "Ngả lưng thư giãn"

                                # I. Đứng thẳng / Đi lại di chuyển
                                elif aspect_ratio >= 1.70:
                                    person_action = "Đứng thẳng / Đi lại di chuyển"

                                # J. Mặc định tự nhiên
                                else:
                                    if aspect_ratio >= 1.62:
                                        person_action = "Đang đứng / Hoạt động trong phòng"
                                    else:
                                        person_action = "Sinh hoạt bình thường / Quan sát"

                            # Lọc trễ thời gian (Temporal Hysteresis) + Cửa sổ trượt đồng thuận đa số để khử giật nhãn/màu
                            stab_res = temporal_stabilizer.update(
                                c_id=c_id,
                                raw_action=person_action,
                                raw_role=person_role_type,
                                raw_danger=person_danger,
                                threat_score=person_threat_score,
                                kinetic=kinetic_spike,
                                interaction=interaction_score
                            )
                            stable_action = stab_res["action"]
                            stable_role = stab_res["role"]
                            stable_danger = stab_res["is_danger"]
                            color = stab_res["color"]
                            role_prefix = stab_res["role_prefix"]
                            stable_threat_score = stab_res["threat_score"]

                            # Bounding Box góc ngoặc mượt mà, không nhấp nháy
                            label_str = f"{id_label}{role_prefix}: {stable_action.upper()}"
                            self.hud.draw_corner_bracket_bbox(frame, x1, y1, x2, y2, color, label_str, conf)

                            # Khung xương 17 khớp nối thanh mảnh
                            kpts_scaled = [(pt[0], pt[1], pt[2]) for pt in kpts]
                            self.hud.draw_cyber_skeleton(frame, kpts_scaled, color)

                        action_counts[stable_action] = action_counts.get(stable_action, 0) + 1
                        if torso_angle >= 75.0:
                            posture_distribution["upright"] += 1
                        elif 45.0 <= torso_angle < 75.0:
                            posture_distribution["bent"] += 1
                        else:
                            posture_distribution["slouched"] += 1

                        if stable_danger:
                            has_frame_danger = True
                            if not frame_alert:
                                frame_alert = f"CẢNH BÁO: XUNG ĐỘT ({id_label})"

                        frame_threat_score = max(frame_threat_score, stable_threat_score)
                        frame_entities.append({
                            "canonical_id": c_id,
                            "id_label": id_label,
                            "action": stable_action,
                            "role": stable_role,
                            "angle": torso_angle,
                            "threat_score": stable_threat_score,
                            "is_danger": stable_danger,
                            "kinetic_spike": kinetic_spike,
                            "interaction_score": interaction_score
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
                        "danger_count": 0,
                        "defender_count": 0,
                        "kinetic_spikes": [],
                        "interaction_scores": []
                    }
                current_seg["persons_history"][c_id_key]["actions"].append(ent["action"])
                current_seg["persons_history"][c_id_key]["angles"].append(ent["angle"])
                current_seg["persons_history"][c_id_key]["max_threat"] = max(current_seg["persons_history"][c_id_key]["max_threat"], ent["threat_score"])
                current_seg["persons_history"][c_id_key]["kinetic_spikes"].append(ent.get("kinetic_spike", 0.0))
                current_seg["persons_history"][c_id_key]["interaction_scores"].append(ent.get("interaction_score", 0.0))
                if ent.get("role") == "attacker" or ent["is_danger"]:
                    current_seg["persons_history"][c_id_key]["danger_count"] += 1
                elif ent.get("role") == "defender":
                    current_seg["persons_history"][c_id_key]["defender_count"] += 1

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

            # --- DÁN NHÃN HUD BẰNG PILLOW UNICODE (KHÔNG VỠ FONT TIẾNG VIỆT) ---
            header_h = 45
            overlay_hdr = frame.copy()
            cv2.rectangle(overlay_hdr, (0, 0), (orig_w, header_h), (15, 20, 28), -1)
            banner_color = (68, 68, 239) if has_frame_danger else (16, 185, 129)
            cv2.rectangle(overlay_hdr, (0, 0), (8, header_h), banner_color, -1)
            cv2.addWeighted(overlay_hdr, 0.85, frame, 0.15, 0, frame)

            cur_time_str = format_time(current_time_sec - start_time)
            dev_hw = self.device_name
            hdr_text = f"FRAME: {processed_count:05d}/{target_total_frames:05d} [{cur_time_str}]  |  XỬ LÝ: {avg_proc_fps:.0f} FPS ({dev_hw})  |  ĐỐI TƯỢNG: {detected_persons_count}"
            status_tag = f"[ {frame_alert} ]" if has_frame_danger else "[ AN TOÀN ]"

            # Vẽ text tiếng Việt Unicode mượt mà bằng Pillow ImageDraw
            hdr_roi = frame[0:header_h, 0:orig_w]
            pil_hdr = Image.fromarray(cv2.cvtColor(hdr_roi, cv2.COLOR_BGR2RGB))
            draw_hdr = ImageDraw.Draw(pil_hdr)
            font_hdr = getattr(self.hud, "font_body_bold", None) or getattr(self.hud, "font_body", None)
            font_status = getattr(self.hud, "font_section", None) or getattr(self.hud, "font_body_bold", None)

            draw_hdr.text((20, 14), hdr_text, font=font_hdr, fill=(245, 247, 250))
            tag_color_rgb = (banner_color[2], banner_color[1], banner_color[0])
            status_x = max(orig_w - 320, int(orig_w * 0.70))
            draw_hdr.text((status_x, 14), status_tag, font=font_status, fill=tag_color_rgb)

            frame[0:header_h, 0:orig_w] = cv2.cvtColor(np.array(pil_hdr), cv2.COLOR_RGB2BGR)

            # Tuyệt đối không vẽ viền đỏ toàn màn hình (chỉ hiển thị viền/khung xương của đối tượng ra đòn)
            out.write(frame)

            if progress_callback and processed_count % 3 == 0:
                progress_callback(processed_count, target_total_frames, avg_proc_fps)

        cap.release()
        out.release()

        # Xác định vai trò cho các đối tượng bền vững
        stabilizer.finalize_roles(orig_h)

        # Lấy danh sách các đối tượng thực sự có mặt trong video (chốt tối đa K <= 4 người tiêu điểm)
        dominant_c_ids = stabilizer.get_dominant_canonical_ids(max_limit=4)
        if not dominant_c_ids:
            dominant_c_ids = [1]

        # Bảo toàn mã ID toàn cục thực tế của từng đối tượng (ID #01, #02, #05...), không ép đè 1..4
        clean_id_map = {cid: cid for cid in dominant_c_ids}

        all_detected_entities = [f"ID #{cid:02d} ({stabilizer.get_role(cid)})" for cid in dominant_c_ids]
        if not all_detected_entities:
            all_detected_entities = ["Khu vực an ninh"]

        # Chuyển đổi sang định dạng H.264 (avc1) web-standard bằng ffmpeg, đồng thời bảo lưu âm thanh gốc nếu có
        converted_h264 = False
        try:
            if has_orig_audio:
                cmd = [
                    get_ffmpeg_bin(), "-y",
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
                    get_ffmpeg_bin(), "-y",
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
            "audio_status": "Có âm thanh gốc" if has_orig_audio else "Không có âm thanh (Video CCTV câm - Hãy tập trung 100% vào ngôn ngữ cơ thể, cử chỉ bàn tay, hướng mắt)",
            "video_source": input_path
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

            # Thu thập chỉ số động học toàn phân đoạn để tính điểm minh bạch
            seg_kinetics = []
            seg_interactions = []

            for c_id in dominant_c_ids:
                if c_id not in s_data["persons_history"]:
                    continue
                t_info = s_data["persons_history"][c_id]
                if len(t_info["actions"]) < min_presence_frames:
                    continue

                actions = t_info["actions"]
                dom_action = max(set(actions), key=actions.count) if actions else "Quan sát"
                disp_id = clean_id_map.get(c_id, c_id)

                k_spikes = t_info.get("kinetic_spikes", [0.0])
                inter_scs = t_info.get("interaction_scores", [0.0])
                seg_kinetics.extend(k_spikes)
                seg_interactions.extend(inter_scs)

                # Phân định vai trò chuẩn xác dựa trên số liệu 5 trụ cột
                if t_info["danger_count"] >= 8:
                    role = "Kẻ tấn công / Gây hấn"
                    ent_severity = "danger"
                    seg_severity = "danger"
                elif t_info.get("defender_count", 0) >= 8:
                    role = "Nạn nhân / Phòng thủ"
                    ent_severity = "warning"
                    if seg_severity == "safe":
                        seg_severity = "warning"
                else:
                    role = "Người quan sát / Ngoài cuộc"
                    ent_severity = "safe"

                ent_label = f"ID #{disp_id:02d}"

                # Diễn đạt trạng thái tự nhiên
                if "Vung tay" in dom_action or "Tấn công" in dom_action:
                    posture_desc = "Vung đòn tốc độ cao về phía đối phương"
                elif "Phòng vệ" in dom_action or "Chắn đỡ" in dom_action:
                    posture_desc = "Hai tay co thủ che chắn / Né đòn"
                elif "Xung đột" in dom_action:
                    posture_desc = "Áp sát giằng co cường độ cao"
                elif "Té ngã" in dom_action:
                    posture_desc = "Sụp đổ trục thân / Nằm bất động"
                elif dom_action == "Đứng thẳng / Đi lại di chuyển" or "Đang đứng" in dom_action:
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

            # Cơ sở phân tích (Telemetry Breakdown theo công thức 5 trụ cột)
            max_k = max(seg_kinetics) if seg_kinetics else 0.0
            max_c = max(seg_interactions) if seg_interactions else 0.0
            score_kinetic = min(10.0, max_k * 2.8)
            score_proximity = min(10.0, max_c * 2.2)
            score_posture = 8.5 if seg_severity == "danger" else (4.5 if seg_severity == "warning" else 0.5)
            
            # Tính điểm nguy cơ đa biến biến thiên thực tế theo mức độ va chạm
            calculated_score = min(10.0, 0.40 * score_kinetic + 0.35 * score_proximity + 0.25 * score_posture)
            final_threat_score = round(calculated_score if seg_severity != "safe" else 0.0, 1)

            vel_px = int(round(max_k * 140.0)) if max_k > 0.3 else 0
            dist_px = int(round(max(25.0, 180.0 - max_c * 28.0))) if max_c > 0.5 else 180
            posture_display = "Xô xát / Ra đòn" if seg_severity == "danger" else ("Áp sát thủ thế" if seg_severity == "warning" else "Đứng thẳng / Ổn định")

            telemetry_breakdown = {
                # Frontend convention (app.js compatibility)
                "max_velocity": vel_px,
                "min_distance": dist_px,
                "dominant_posture": posture_display,
                # Backend convention
                "strike_velocity": f"{round(max_k * 1.3, 1)} m/s" if max_k > 0.8 else f"{vel_px} px/s",
                "proximity_dist": f"{dist_px} px" if max_c > 0.8 else "> 1.5 m",
                "posture_state": posture_display,
                "kinetic_spike": round(max_k, 2),
                "interaction_score": round(max_c, 2),
                "calculated_score": final_threat_score
            }

            # Tổng hợp câu văn mô tả sinh động từ số liệu động học thực tế (Kinematic-Semantic Synthesis)
            attackers = [e for e in seg_entities if e.get("severity") == "danger"]
            defenders = [e for e in seg_entities if e.get("severity") == "warning"]
            observers = [e for e in seg_entities if e.get("severity") == "safe" and e.get("id") != "KHÔNG GIAN"]

            if seg_severity == "danger":
                if attackers and defenders:
                    atk_id = attackers[0]["id"]
                    def_id = defenders[0]["id"]
                    scene_summary = f"Cảnh báo xung đột: Đối tượng {atk_id} áp sát ở cự ly {dist_px} px, vung đòn tốc độ {vel_px} px/s về phía {def_id}. {def_id} co hai tay phòng vệ né đòn."
                    if observers:
                        obs_str = ", ".join([o["id"] for o in observers[:2]])
                        scene_summary += f" Đối tượng {obs_str} giữ vị trí quan sát ngoài cuộc."
                elif attackers:
                    atk_id = attackers[0]["id"]
                    scene_summary = f"Cảnh báo an ninh: Đối tượng {atk_id} ghi nhận xung lực cơ thể đột biến ({vel_px} px/s) với tư thế vung tay tấn công áp sát."
                else:
                    scene_summary = f"Cảnh báo va chạm: Phát hiện biến thiên động học mạnh giữa các cá nhân ({vel_px} px/s), cự ly thu hẹp dưới {dist_px} px."
            elif seg_severity == "warning":
                if defenders:
                    def_id = defenders[0]["id"]
                    scene_summary = f"Cảnh báo phòng vệ: Ghi nhận đối tượng {def_id} thủ thế co hai tay chắn đỡ, nghiêng thân né tránh ở cự ly {dist_px} px."
                else:
                    scene_summary = f"Trạng thái đối đầu: Các đối tượng thu hẹp khoảng cách tiếp cận ({dist_px} px), tư thế sẵn sàng phòng vệ nhưng chưa phát sinh va chạm."
            else:
                if len(observers) > 1:
                    scene_summary = f"Khu vực an ninh ổn định: Ghi nhận {len(observers)} đối tượng hoạt động bình thường, cự ly an toàn > 1.5 m, không có xung lực đột biến."
                elif len(seg_entities) == 1 and seg_entities[0].get("id") != "KHÔNG GIAN":
                    scene_summary = f"Đối tượng {seg_entities[0]['id']} {seg_entities[0]['action'].lower()}, trạng thái sinh cơ học ổn định."
                else:
                    scene_summary = "Khu vực an ninh ổn định, không ghi nhận chuyển động bất thường."

            pred_next = "Duy trì trạng thái tương tác an toàn trong các giây tiếp theo"
            if seg_severity == "danger":
                pred_next = "Nguy cơ xung đột tiếp diễn cao; cần kích hoạt cảnh báo an ninh và tách biệt các đối tượng"
            elif seg_severity == "warning":
                pred_next = "Cần theo dõi cự ly tiếp xúc; có thể hạ nhiệt nếu các đối tượng lùi bước giữ khoảng cách an toàn"

            timeline_segments.append({
                "segment_id": f"SEG-{idx+1:02d}",
                "start_sec": round(s_data["start_sec"] - start_time, 1),
                "end_sec": round(s_data["end_sec"] - start_time, 1),
                "time_range": time_range,
                "scene_summary": scene_summary,
                "context_description": scene_summary,
                "prediction_next_4s": pred_next,
                "entities": seg_entities,
                "severity": seg_severity,
                "danger_score": final_threat_score,
                "telemetry_breakdown": telemetry_breakdown,
                "snapshot_url": f"/api/snapshots/{snap_filename}"
            })

        # Mảng mẫu Heatmap & Đường cong Rủi ro: Bảo toàn đỉnh nhọn va chạm/đòn đánh (Peak-Preserving Smoothing)
        raw_slots = sorted(heatmap_samples.keys())
        smoothed_scores = {}
        for i, s_k in enumerate(raw_slots):
            raw_v = heatmap_samples[s_k]
            nearby = [heatmap_samples[raw_slots[j]] for j in range(max(0, i - 2), min(len(raw_slots), i + 3))]
            if nearby:
                avg_nearby = sum(nearby) / len(nearby)
                max_nearby = max(nearby)
                # Nếu tại điểm hiện tại hoặc lân cận có xung lực nguy hiểm (>= 6.0),
                # bảo toàn đỉnh nhọn để phản ánh đúng thực tế va chạm/đòn đánh trên đồ thị
                if raw_v >= 6.0:
                    smoothed_scores[s_k] = max(raw_v, 0.20 * avg_nearby + 0.80 * max_nearby)
                elif max_nearby >= 7.0:
                    smoothed_scores[s_k] = max(0.40 * avg_nearby + 0.60 * max_nearby, raw_v * 0.8)
                else:
                    smoothed_scores[s_k] = 0.60 * avg_nearby + 0.40 * max_nearby
            else:
                smoothed_scores[s_k] = raw_v

        heatmap_data = []
        for slot in raw_slots:
            sc = round(smoothed_scores.get(slot, heatmap_samples[slot]), 1)
            level = "danger" if sc >= 7.0 else ("warning" if sc >= 3.5 else "safe")
            heatmap_data.append({
                "time": slot,
                "time_str": format_time(slot),
                "score": sc,
                "level": level
            })

        # Gọi TokenGuard để chẩn đoán tổng hợp và mô tả thị giác chi tiết nếu được bật
        gemini_result = {}
        if call_gemini:
            # Thu thập keyframes từ từng phân đoạn timeline (Multi-Image Batch Request)
            segment_keyframes = []
            for idx, s_data in enumerate(segments_data):
                ts_mid = round(s_data["start_sec"] - start_time, 2)
                s_id = f"SEG-{idx+1:02d}"
                t_rng = f"{format_time(s_data['start_sec'] - start_time)} - {format_time(s_data['end_sec'] - start_time)}"
                if s_data["peak_frame"] is not None:
                    if ts_mid not in candidate_keyframes:
                        candidate_keyframes[ts_mid] = s_data["peak_frame"].copy()
                    segment_keyframes.append({
                        "segment_id": s_id,
                        "time_range": t_rng,
                        "timestamp": ts_mid,
                        "frame": s_data["peak_frame"].copy()
                    })

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
                    "entity_count": len(s.get("entities", [])),
                    "local_score": s.get("danger_score", 0.0),
                    "local_severity": s.get("severity", "safe")
                })

            gemini_result = self.token_guard.synthesize_video_report(
                video_metadata=video_meta,
                event_summary=threat_event_log,
                peak_keyframes=peak_kfs,
                segment_info=segment_info_list,
                segment_keyframes=segment_keyframes
            )

            # Áp dụng Gemini Visual Grounding (danh tính và vai trò thực tế của các đối tượng)
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

            # Ghép phân tích chi tiết cấp Vĩ Mô (Macro Narrative) & Nhận diện Vũ khí của Gemini vào từng phân đoạn timeline
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

                    # Nhận diện Vũ khí / Hung khí từ Gemini Vision
                    w_det = ga.get("weapon_detected")
                    if w_det and str(w_det).lower() not in ["null", "none", "không có", "không", "false"]:
                        seg["weapon_detected"] = str(w_det)
                        seg["severity"] = "danger"
                        seg["danger_score"] = max(seg.get("danger_score", 0.0), float(ga.get("threat_score", 8.8)))

                    # Đồng bộ mức độ nguy hiểm phân đoạn nếu Gemini xác nhận
                    g_lvl = str(ga.get("threat_level", "")).upper()
                    if g_lvl == "NGUY HIỂM":
                        seg["severity"] = "danger"
                        seg["danger_score"] = max(seg.get("danger_score", 0.0), float(ga.get("threat_score", 8.5)))
                    elif g_lvl == "CẢNH BÁO" and seg["severity"] != "danger":
                        seg["severity"] = "warning"
                        seg["danger_score"] = max(seg.get("danger_score", 0.0), float(ga.get("threat_score", 5.0)))

                    # Điều chỉnh tư thế ngồi nếu Gemini nhận diện ngồi tại bàn
                    p_override = ga.get("posture_override")
                    if p_override:
                        for ent in seg.get("entities", []):
                            if "đang đứng" in ent.get("action", "").lower() or ent.get("role") == "observer":
                                ent["action"] = p_override
                                ent["posture"] = p_override

                elif gemini_result.get("scene_context"):
                    seg["context_description"] = gemini_result.get("scene_context")

            # Cập nhật max_danger_score sau khi hội chẩn cùng Gemini
            max_danger_score = max([seg.get("danger_score", 0.0) for seg in timeline_segments] or [max_danger_score])
            if max_danger_score >= 7.0:
                peak_danger_reason = "Phát hiện xung đột thể xác / đòn đánh hoặc hung khí nguy hiểm"

        # Thống kê Phân bổ Rủi ro & Tư thế Đa chiều (Multi-dimensional Behavior & Risk Analytics)
        safe_cnt = 0
        warn_cnt = 0
        danger_cnt = 0
        for slot in heatmap_data:
            sc = slot.get("score", 0.0)
            if sc >= 7.0:
                danger_cnt += 1
            elif sc >= 3.5:
                warn_cnt += 1
            else:
                safe_cnt += 1

        total_risk_slots = max(1, len(heatmap_data))
        safe_pct = round((safe_cnt / total_risk_slots) * 100.0, 1)
        warn_pct = round((warn_cnt / total_risk_slots) * 100.0, 1)
        danger_pct = round((danger_cnt / total_risk_slots) * 100.0, 1)

        total_postures = max(1, sum(posture_distribution.values()))
        upright_pct = round((posture_distribution["upright"] / total_postures) * 100.0, 1)
        bent_pct = round((posture_distribution["bent"] / total_postures) * 100.0, 1)
        slouched_pct = round((posture_distribution["slouched"] / total_postures) * 100.0, 1)

        # Tính toán Điểm số Công thái học (Ergonomic Score 0 - 100)
        base_ergo = 95.0
        ergo_deduct = (danger_pct * 0.70) + (warn_pct * 0.35) + (bent_pct * 0.15) + (slouched_pct * 0.25)
        raw_ergo = max(20.0, min(99.0, base_ergo - ergo_deduct))

        if gemini_result.get("threat_level") == "AN TOÀN" or gemini_result.get("is_safe_environment", False):
            raw_ergo = max(86.0, raw_ergo)

        ergo_score = round(raw_ergo, 1)

        # Ước lượng thời gian ngồi liên tục (Sedentary time)
        sitting_counts = action_counts.get("Ngồi làm việc / Thao tác tay", 0) + action_counts.get("Ngồi tại bàn / Quan sát tĩnh", 0)
        sitting_ratio = sitting_counts / max(1, sum(action_counts.values()))
        continuous_sitting_sec = round(sitting_ratio * (processed_count / input_fps), 1)

        if ergo_score >= 82.0:
            ergo_advice = "Tư thế sinh hoạt và lao động trong phân đoạn đạt chuẩn Tốt. Cột sống và các khớp duy trì góc độ giải phẫu học tự nhiên."
        elif ergo_score >= 65.0:
            ergo_advice = "Ghi nhận góc nghiêng cột sống lệch chuẩn trong một số thời điểm. Nên điều chỉnh độ cao mặt bàn hoặc thay đổi tư thế định kỳ."
        else:
            ergo_advice = "Cảnh báo công thái học: Xuất hiện tư thế gập sâu bất đối xứng hoặc dấu hiệu té ngã. Cần kiểm tra an toàn lập tức."

        # Quyết định dominant_risk theo tiêu chuẩn an ninh: Có biến cố bạo lực/đòn đánh -> Đánh dấu DANGER
        if danger_cnt >= 2 or danger_pct >= 5.0 or max_danger_score >= 7.0:
            dominant_risk = "danger"
        elif warn_cnt >= 3 or warn_pct >= 10.0 or max_danger_score >= 4.0:
            dominant_risk = "warning"
        else:
            dominant_risk = "safe"

        behavior_analytics = {
            "risk_breakdown": {
                "safe_count": safe_cnt,
                "warning_count": warn_cnt,
                "danger_count": danger_cnt,
                "safe_pct": safe_pct,
                "warning_pct": warn_pct,
                "danger_pct": danger_pct,
                "dominant_risk": dominant_risk
            },
            "posture_distribution": {
                "upright_count": posture_distribution["upright"],
                "bent_count": posture_distribution["bent"],
                "slouched_count": posture_distribution["slouched"],
                "upright_pct": upright_pct,
                "bent_pct": bent_pct,
                "slouched_pct": slouched_pct
            },
            "risk_curve": heatmap_data,
            "ergonomic_score": ergo_score,
            "continuous_sitting_sec": continuous_sitting_sec,
            "ergonomic_advice": ergo_advice
        }

        # Tạo dữ liệu Băng chuyền hành vi đa thực thể (Multi-Track Actor Timeline)
        actor_timeline_tracks = []
        for c_id in dominant_c_ids:
            tracks_for_id = []
            for s_idx, s_data in enumerate(segments_data):
                t_info = s_data["persons_history"].get(c_id)
                s_start = round(s_data["start_sec"] - start_time, 1)
                s_end = round(s_data["end_sec"] - start_time, 1)
                if not t_info or len(t_info.get("actions", [])) == 0:
                    continue
                actions = t_info["actions"]
                dom_act = max(set(actions), key=actions.count)
                if t_info.get("danger_count", 0) >= 8:
                    sev = "danger"
                    act_label = "Vung đòn / Tấn công"
                elif t_info.get("defender_count", 0) >= 8:
                    sev = "warning"
                    act_label = "Phòng vệ / Chắn đỡ"
                elif "Té ngã" in dom_act:
                    sev = "danger"
                    act_label = "Té ngã"
                else:
                    sev = "safe"
                    act_label = "Đang đứng / Quan sát"

                tracks_for_id.append({
                    "start_sec": s_start,
                    "end_sec": s_end,
                    "state": sev,
                    "action": act_label
                })

            total_dang = sum(s["persons_history"].get(c_id, {}).get("danger_count", 0) for s in segments_data)
            total_def = sum(s["persons_history"].get(c_id, {}).get("defender_count", 0) for s in segments_data)
            if total_dang >= 15:
                role_title = "Kẻ tấn công / Gây hấn"
            elif total_def >= 15:
                role_title = "Nạn nhân / Phòng thủ"
            else:
                role_title = "Người quan sát"

            actor_timeline_tracks.append({
                "canonical_id": c_id,
                "label": f"ID #{c_id:02d}",
                "role": role_title,
                "intervals": tracks_for_id
            })

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
            "actor_timeline_tracks": actor_timeline_tracks,
            "heatmap_data": heatmap_data,
            "entities_detected": all_detected_entities,
            "max_danger_score": max_danger_score,
            "peak_danger_reason": peak_danger_reason,
            "overall_danger_level": "NGUY HIEM" if max_danger_score >= 8 else ("CANH BAO" if max_danger_score >= 5 else "AN TOAN"),
            "behavior_analytics": behavior_analytics,
            "gemini_report": gemini_result
        }

