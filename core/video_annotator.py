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
    def __init__(self, max_missing_frames: int = 90, match_dist_ratio: float = 0.35, max_k: int = 4):
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
            if 1 <= c_id <= self.max_k and c_id not in occupied:
                self._record_track(c_id, bbox, cx, cy, h, aspect, frame_idx, raw_id)
                occupied.add(c_id)
                self._record_concurrency(frame_idx)
                return c_id

        # 2. Tìm kiếm trong các track canonical hợp lệ (1 <= cid <= max_k) chưa xuất hiện ở frame hiện tại
        best_cid = None
        min_cost = 999999.0
        threshold_dist = self.match_dist_ratio * diag
        available_cids = [cid for cid in self.active_tracks if cid not in occupied and (1 <= cid <= self.max_k)]

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
            # Nếu chưa có track phù hợp, kiểm tra xem còn slot ID nào chưa tạo trong [1..max_k] không
            created_cids = set(self.active_tracks.keys())
            free_cids = [i for i in range(1, self.max_k + 1) if i not in created_cids]
            if free_cids:
                c_id = min(free_cids)
            else:
                # Toàn bộ max_k ID đã được tạo: chọn canonical ID chưa occupied trong frame
                unoccupied_cids = [i for i in range(1, self.max_k + 1) if i not in occupied]
                if unoccupied_cids:
                    c_id = min(unoccupied_cids, key=lambda i: math.hypot(cx - self.active_tracks[i]["cx"], cy - self.active_tracks[i]["cy"]) if i in self.active_tracks else 99999)
                else:
                    # Nếu đã occupied hết cả max_k ID trong frame
                    c_id = min(range(1, self.max_k + 1), key=lambda i: math.hypot(cx - self.active_tracks[i]["cx"], cy - self.active_tracks[i]["cy"]) if i in self.active_tracks else 99999)

        # Ràng buộc chặt chẽ: c_id luôn nằm trong [1..max_k]
        c_id = max(1, min(self.max_k, c_id))
        self.raw_to_canonical[raw_id] = c_id
        self._record_track(c_id, bbox, cx, cy, h, aspect, frame_idx, raw_id)
        occupied.add(c_id)
        self._record_concurrency(frame_idx)
        return c_id

    def _record_concurrency(self, frame_idx: int):
        current_ids = list(self.frame_canonical_occupancy.get(frame_idx, set()))
        if len(current_ids) > self.max_concurrent_seen:
            self.max_concurrent_seen = min(self.max_k, len(current_ids))
        for i in range(len(current_ids)):
            for j in range(i + 1, len(current_ids)):
                pair = tuple(sorted((current_ids[i], current_ids[j])))
                self.concurrent_pairs.add(pair)

    def get_dominant_canonical_ids(self, max_limit: int = 4) -> List[int]:
        """
        Lấy danh sách các canonical ID đại diện cho đúng số người thực tế (K <= 4).
        Chắc chắn ID luôn thuộc [1..max_limit].
        """
        limit = min(self.max_k, max_limit)
        valid_counts = {cid: cnt for cid, cnt in self.canonical_counts.items() if 1 <= cid <= limit and cnt >= 5}
        if not valid_counts:
            valid_counts = {cid: cnt for cid, cnt in self.canonical_counts.items() if 1 <= cid <= limit}
        if not valid_counts:
            return [1]

        sorted_cids = sorted(valid_counts.keys(), key=lambda c: valid_counts[c], reverse=True)
        target_k = min(limit, max(1, self.max_concurrent_seen))
        target_k = max(target_k, min(len(sorted_cids), limit))
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

            # A. Kinetic velocity spike (Vận tốc dịch chuyển khớp xương)
            kinetic_spike = 0.0
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
            det["posture_anomaly"] = posture_anomaly
            det["interaction_score"] = 0.0

        # 2. Tính toán tương tác vật lý (Physical Interaction) giữa các cặp trong frame
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

                if iou > 0.10 or dist < 0.65 * avg_h:
                    if (det_a["kinetic_spike"] > 1.2 or det_b["kinetic_spike"] > 1.2 or 
                        det_a.get("threat_score", 0) > 4.0 or det_b.get("threat_score", 0) > 4.0 or
                        det_a.get("person_danger") or det_b.get("person_danger")):
                        inter_boost = 5.0
                        det_a["interaction_score"] = max(det_a["interaction_score"], inter_boost)
                        det_b["interaction_score"] = max(det_b["interaction_score"], inter_boost)

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

                            # 2. Phân loại Tư thế Sinh cơ học Thực tế (Xóa bỏ hoàn toàn đoán mò ngồi/khoanh tay)
                            if not person_danger:
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
                        if torso_angle >= 75.0:
                            posture_distribution["upright"] += 1
                        elif 45.0 <= torso_angle < 75.0:
                            posture_distribution["bent"] += 1
                        else:
                            posture_distribution["slouched"] += 1

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

        # Thống kê Phân bổ Rủi ro & Tư thế Đa chiều (Multi-dimensional Behavior & Risk Analytics)
        safe_cnt = 0
        warn_cnt = 0
        danger_cnt = 0
        for slot in heatmap_data:
            sc = slot.get("score", 0.0)
            if sc >= 8.0:
                danger_cnt += 1
            elif sc >= 4.0:
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
        sitting_ratio = action_counts.get("Ngồi làm việc / Thao tác tay", 0) / max(1, sum(action_counts.values()))
        continuous_sitting_sec = round(sitting_ratio * (processed_count / input_fps), 1)

        if ergo_score >= 82.0:
            ergo_advice = "Tư thế sinh hoạt và lao động trong phân đoạn đạt chuẩn Tốt. Cột sống và các khớp duy trì góc độ giải phẫu học tự nhiên."
        elif ergo_score >= 65.0:
            ergo_advice = "Ghi nhận góc nghiêng cột sống lệch chuẩn trong một số thời điểm. Nên điều chỉnh độ cao mặt bàn hoặc thay đổi tư thế định kỳ."
        else:
            ergo_advice = "Cảnh báo công thái học: Xuất hiện tư thế gập sâu bất đối xứng hoặc dấu hiệu té ngã. Cần kiểm tra an toàn lập tức."

        behavior_analytics = {
            "risk_breakdown": {
                "safe_count": safe_cnt,
                "warning_count": warn_cnt,
                "danger_count": danger_cnt,
                "safe_pct": safe_pct,
                "warning_pct": warn_pct,
                "danger_pct": danger_pct,
                "dominant_risk": "safe" if safe_cnt >= warn_cnt and safe_cnt >= danger_cnt else ("warning" if warn_cnt >= danger_cnt else "danger")
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
            "behavior_analytics": behavior_analytics,
            "gemini_report": gemini_result
        }

