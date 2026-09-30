"""
Hệ Thống Giám Sát Thị Giác Đa Luồng - OS Video Surveillance HUD Renderer.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng Thời gian thực.
Khung hiển thị viễn trắc HĐH thời gian thực chuẩn học thuật (1280x720 Widescreen).
Hỗ trợ Unicode tiếng Việt đầy đủ bằng Pillow, loại bỏ lỗi font và hiện tượng đè che mặt.
"""

import os
import cv2
import numpy as np
import time
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont


class CyberHUDRenderer:
    def __init__(self, width=1280, height=720, viewport_w=900, sidebar_w=380):
        self.width = width
        self.height = height
        self.viewport_w = viewport_w
        self.viewport_h = height
        self.sidebar_w = sidebar_w

        # Bảng màu chuẩn Radix Slate (Độ tương phản cao, chuẩn học thuật Hệ Điều Hành)
        self.COLORS = {
            "bg_dark": (15, 20, 28),          # Nền kính đen sidebar
            "card_bg": (23, 32, 44),          # Nền thẻ thông số
            "card_border": (45, 55, 72),      # Viền thẻ
            "neon_cyan": (0, 240, 255),       # Xanh cyan kỹ thuật
            "safe_green": (16, 185, 129),     # Xanh lá an toàn
            "warn_yellow": (245, 158, 11),    # Vàng cam cảnh báo
            "danger_red": (239, 68, 68),      # Đỏ rực nguy cơ cao
            "text_white": (245, 247, 250),    # Trắng sáng
            "text_muted": (156, 163, 175),    # Xám phụ đề
            "text_cyan": (125, 211, 252),     # Xanh nhạt
            "led_off": (40, 48, 60),          # Đèn LED tắt
        }

        # Khởi tạo font chữ hệ thống hỗ trợ tiếng Việt Unicode đa nền tảng
        self.font_title = self._load_font(["segoeuib.ttf", "arialbd.ttf", "segoeui.ttf", "arial.ttf"], 15, bold=True)
        self.font_sub = self._load_font(["segoeui.ttf", "arial.ttf"], 12)
        self.font_section = self._load_font(["segoeuib.ttf", "arialbd.ttf", "arial.ttf"], 13, bold=True)
        self.font_body = self._load_font(["segoeui.ttf", "arial.ttf"], 13)
        self.font_body_bold = self._load_font(["segoeuib.ttf", "arialbd.ttf", "arial.ttf"], 13, bold=True)
        self.font_caption = self._load_font(["segoeui.ttf", "arial.ttf"], 11)

    def _load_font(self, font_names, size, bold=False):
        """Hỗ trợ đa nền tảng Windows, Linux Ubuntu/Colab, MacOS cho tiếng Việt Unicode."""
        candidates = list(font_names) if font_names else []

        # 1. Windows Fonts (Hệ điều hành Windows)
        windir = os.environ.get("WINDIR", "C:/Windows")
        if bold:
            candidates.extend([
                f"{windir}/Fonts/segoeuib.ttf",
                f"{windir}/Fonts/arialbd.ttf",
                f"{windir}/Fonts/calibrib.ttf",
                f"{windir}/Fonts/tahomabd.ttf",
                f"{windir}/Fonts/segoeui.ttf",
                f"{windir}/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf"
            ])
        else:
            candidates.extend([
                f"{windir}/Fonts/segoeui.ttf",
                f"{windir}/Fonts/arial.ttf",
                f"{windir}/Fonts/calibri.ttf",
                f"{windir}/Fonts/tahoma.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibri.ttf",
                "C:/Windows/Fonts/tahoma.ttf"
            ])

        # 2. Linux / Google Colab Fonts (Ubuntu/Debian)
        if bold:
            candidates.extend([
                "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
                "/usr/share/fonts/truetype/roboto/unhinted/Roboto-Bold.ttf",
                "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            ])
        else:
            candidates.extend([
                "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                "/usr/share/fonts/truetype/roboto/unhinted/Roboto-Regular.ttf",
                "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            ])

        # 3. MacOS Fonts (Apple Silicon / Intel Mac)
        candidates.extend([
            "/System/Library/Fonts/SFProText-Regular.otf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
        ])

        # Nạp font hợp lệ đầu tiên tìm thấy
        for name in candidates:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                pass

        # Quét thư mục font hệ thống để tìm bất kỳ font TrueType nào, không bao giờ dùng 1-bit ASCII cho tiếng Việt
        search_dirs = [
            f"{windir}/Fonts",
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            "/Library/Fonts",
            "/System/Library/Fonts"
        ]
        for s_dir in search_dirs:
            if os.path.exists(s_dir):
                for root, _, files in os.walk(s_dir):
                    for f in files:
                        if f.lower().endswith(".ttf") or f.lower().endswith(".otf"):
                            try:
                                return ImageFont.truetype(os.path.join(root, f), size)
                            except Exception:
                                continue

        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()

    def draw_unicode_text(
        self,
        img: np.ndarray,
        text: str,
        pos: Tuple[int, int],
        font: ImageFont.ImageFont,
        color_bgr: Tuple[int, int, int] = (245, 247, 250),
        bg_color_bgr: Optional[Tuple[int, int, int]] = None,
        padding: int = 4
    ):
        """
        Vẽ chuỗi văn bản tiếng Việt Unicode mượt mà lên mảng hình ảnh OpenCV BGR bằng Pillow.
        Loại bỏ 100% hiện tượng vỡ font, ký tự rác hoặc dấu '?' của cv2.putText.
        """
        if not text:
            return
        x, y = pos
        h, w = img.shape[:2]
        if x >= w or y >= h:
            return

        try:
            bbox = font.getbbox(text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w = len(text) * 8
            text_h = 16

        patch_w = text_w + padding * 2
        patch_h = text_h + padding * 2
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x1 + patch_w)
        y2 = min(h, y1 + patch_h)

        if x2 <= x1 or y2 <= y1:
            return

        roi = img[y1:y2, x1:x2]
        pil_patch = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_patch)

        color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])

        if bg_color_bgr is not None:
            bg_rgb = (bg_color_bgr[2], bg_color_bgr[1], bg_color_bgr[0])
            draw.rectangle([0, 0, x2 - x1, y2 - y1], fill=bg_rgb)

        draw.text((padding, padding), text, font=font, fill=color_rgb)

        res_bgr = cv2.cvtColor(np.array(pil_patch), cv2.COLOR_RGB2BGR)
        img[y1:y2, x1:x2] = res_bgr


    # Các đường nối khung xương cơ thể chuẩn (bỏ qua nối mắt-mũi để không che mặt)
    SKELETON_PAIRS = [
        (5, 6),                                     # Vai trái - vai phải
        (5, 7), (7, 9),                             # Tay trái: vai - khuỷu - cổ tay
        (6, 8), (8, 10),                            # Tay phải: vai - khuỷu - cổ tay
        (5, 11), (6, 12), (11, 12),                 # Thân người: vai - hông
        (11, 13), (13, 15),                         # Chân trái: hông - gối - cổ chân
        (12, 14), (14, 16)                          # Chân phải: hông - gối - cổ chân
    ]

    def draw_cyber_skeleton(self, img, kpts, color_bgr):
        """Vẽ khung xương tư thế công thái học 17 điểm chuẩn hóa (Ergonomic Posture Skeleton)."""
        if kpts is None or len(kpts) == 0:
            return

        # 1. Vẽ các đường xương cơ thể
        for (i, j) in self.SKELETON_PAIRS:
            if i < len(kpts) and j < len(kpts):
                p1, p2 = kpts[i], kpts[j]
                conf1 = p1[2] if len(p1) > 2 else 1.0
                conf2 = p2[2] if len(p2) > 2 else 1.0
                if conf1 > 0.40 and conf2 > 0.40:
                    pt1 = (int(p1[0]), int(p1[1]))
                    pt2 = (int(p2[0]), int(p2[1]))
                    cv2.line(img, pt1, pt2, (color_bgr[0]//3, color_bgr[1]//3, color_bgr[2]//3), 3, cv2.LINE_AA)
                    cv2.line(img, pt1, pt2, color_bgr, 1, cv2.LINE_AA)

        # 2. Vẽ các điểm khớp xương cơ thể (từ vai trở xuống: idx >= 5)
        for idx, pt in enumerate(kpts):
            if idx < 5:
                continue  # Bỏ qua mắt mũi để không che mặt người
            conf = pt[2] if len(pt) > 2 else 1.0
            if conf > 0.40:
                px, py = int(pt[0]), int(pt[1])
                cv2.circle(img, (px, py), 4, color_bgr, 1, cv2.LINE_AA)
                cv2.circle(img, (px, py), 2, (255, 255, 255), -1, cv2.LINE_AA)

    # Alias học thuật chuẩn HĐH
    draw_ergonomic_skeleton = draw_cyber_skeleton

    def draw_technical_bbox(self, img, x1, y1, x2, y2, color_bgr, label="", score=0.0):
        """Vẽ khung định vị đối tượng chuẩn kỹ thuật (Technical Bounding Box) kèm nhãn tiếng Việt Unicode."""
        w = x2 - x1
        h = y2 - y1
        corner_len = max(12, min(int(min(w, h) * 0.25), 25))
        thickness = 2

        # 1. Khung chữ nhật bao quanh đối tượng
        cv2.rectangle(img, (x1, y1), (x2, y2), color_bgr, 1, lineType=cv2.LINE_AA)

        # 2. Các điểm định vị góc kỹ thuật (Technical corner indicators)
        # Góc trên-trái
        cv2.line(img, (x1, y1), (x1 + corner_len, y1), color_bgr, thickness)
        cv2.line(img, (x1, y1), (x1, y1 + corner_len), color_bgr, thickness)
        # Góc trên-phải
        cv2.line(img, (x2, y1), (x2 - corner_len, y1), color_bgr, thickness)
        cv2.line(img, (x2, y1), (x2, y1 + corner_len), color_bgr, thickness)
        # Góc dưới-trái
        cv2.line(img, (x1, y2), (x1 + corner_len, y2), color_bgr, thickness)
        cv2.line(img, (x1, y2), (x1, y2 - corner_len), color_bgr, thickness)
        # Góc dưới-phải
        cv2.line(img, (x2, y2), (x2 - corner_len, y2), color_bgr, thickness)
        cv2.line(img, (x2, y2), (x2, y2 - corner_len), color_bgr, thickness)

        # 3. Tâm điểm định vị
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.drawMarker(img, (cx, cy), color_bgr, cv2.MARKER_CROSS, 6, 1)

        # 4. Nhãn đính kèm vẽ bằng Pillow Unicode (hỗ trợ 100% tiếng Việt)
        if label:
            tag_text = f"[{label.upper()} {int(score * 100)}%]" if score > 0 else f"[{label.upper()}]"
            tag_y = max(0, y1 - 22)
            self.draw_unicode_text(
                img,
                tag_text,
                (x1, tag_y),
                font=self.font_caption,
                color_bgr=color_bgr,
                bg_color_bgr=(15, 20, 28),
                padding=2
            )

    # Tương thích ngược với các module gọi hàm cũ
    draw_corner_bracket_bbox = draw_technical_bbox

    def draw_camera_decorations(self, frame_vp, fps=30.0, is_ai_busy=False, danger_level="AN TOAN"):
        """Vẽ các chỉ số viễn trắc phụ xung quanh khung hình camera."""
        h, w = frame_vp.shape[:2]

        # 1. Đèn REC nhấp nháy góc trên-trái
        is_blink = int(time.time() * 2) % 2 == 0
        rec_color = (0, 0, 255) if is_blink else (0, 0, 150)
        cv2.circle(frame_vp, (22, 22), 6, rec_color, -1)
        cv2.putText(frame_vp, f"LIVE REC | {fps:.1f} FPS", (36, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (230, 230, 230), 1, cv2.LINE_AA)

        # 2. Camera ID & Timestamp góc trên-phải
        curr_time = time.strftime("%Y-%m-%d  %H:%M:%S")
        cv2.putText(frame_vp, f"CAM-01 [HD 720p]  {curr_time}", (w - 290, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 240, 255), 1, cv2.LINE_AA)

        # 3. Dấu chữ thập trung tâm (Crosshair) mờ nhẹ
        cx, cy = w // 2, h // 2
        cv2.line(frame_vp, (cx - 15, cy), (cx + 15, cy), (80, 100, 120), 1)
        cv2.line(frame_vp, (cx, cy - 15), (cx, cy + 15), (80, 100, 120), 1)
        cv2.circle(frame_vp, (cx, cy), 22, (80, 100, 120), 1)

        # 4. Khi luồng Consumer AI Cloud đang xử lý: hiển thị đèn LED trạng thái công nghiệp + nhãn Unicode
        if is_ai_busy:
            ai_text = "ĐIỀU PHỐI AI CLOUD (CHU KỲ 4S)"
            box_w = 260
            box_h = 28
            box_x = (w - box_w) // 2
            box_y = h - 38
            cv2.rectangle(frame_vp, (box_x, box_y), (box_x + box_w, box_y + box_h), (15, 20, 28), -1)
            cv2.rectangle(frame_vp, (box_x, box_y), (box_x + box_w, box_y + box_h), (0, 240, 255), 1)

            # Đèn LED trạng thái chuyên nghiệp (chấm tròn LED nhỏ 4px, không dùng đồ họa radar viễn tưởng)
            led_blink = int(time.time() * 4) % 2 == 0
            led_color = (0, 240, 255) if led_blink else (0, 150, 180)
            cv2.circle(frame_vp, (box_x + 16, box_y + 14), 4, led_color, -1)

            # Dán nhãn tiếng Việt Unicode mượt mà bằng Pillow
            self.draw_unicode_text(
                frame_vp,
                ai_text,
                (box_x + 28, box_y + 6),
                font=self.font_caption,
                color_bgr=(0, 240, 255),
                bg_color_bgr=None,
                padding=0
            )

        # 5. Viền cảnh báo động toàn màn hình nếu nguy cơ cao
        if "NGUY" in danger_level:
            cv2.rectangle(frame_vp, (0, 0), (w - 1, h - 1), (0, 0, 239), 4)
        elif "CANH" in danger_level:
            cv2.rectangle(frame_vp, (0, 0), (w - 1, h - 1), (11, 158, 245), 3)

    def render_sidebar_pil(self, diagnosis, entities, metrics, danger_score, danger_level, biomechanics=None):
        """Render toàn bộ cột bên phải (380x720) với font tiếng Việt Unicode mượt mà bằng Pillow."""
        sidebar_img = Image.new("RGB", (self.sidebar_w, self.height), color=self.COLORS["bg_dark"])
        draw = ImageDraw.Draw(sidebar_img)

        # Đường viền phân cách bên trái
        draw.line([(0, 0), (0, self.height)], fill=self.COLORS["card_border"], width=2)
        draw.line([(0, 0), (0, self.height)], fill=self.COLORS["neon_cyan"], width=1)

        pad_x = 18
        y = 16

        # --- SECTION 0: HEADER ---
        draw.text((pad_x, y), "HỆ THỐNG GIÁM SÁT THỊ GIÁC ĐA LUỒNG", font=self.font_title, fill=self.COLORS["neon_cyan"])
        y += 24
        draw.text((pad_x, y), "HỆ ĐIỀU HÀNH - PIPELINE ĐIỀU PHỐI ĐA LUỒNG", font=self.font_caption, fill=self.COLORS["text_muted"])
        y += 18

        # Status Pill: Producer Thread Active
        draw.rounded_rectangle([pad_x, y, pad_x + 200, y + 22], radius=4, fill=self.COLORS["card_bg"], outline=self.COLORS["card_border"])
        draw.ellipse([pad_x + 8, y + 7, pad_x + 16, y + 15], fill=self.COLORS["safe_green"])
        draw.text((pad_x + 22, y + 3), "LUỒNG PRODUCER: HOẠT ĐỘNG", font=self.font_caption, fill=self.COLORS["safe_green"])
        y += 32

        # --- SECTION 1: ĐÁNH GIÁ NGUY CƠ & AN TOÀN ---
        is_danger = "NGUY" in danger_level or (biomechanics and biomechanics.get("is_danger", False))
        is_warning = "CANH" in danger_level or (biomechanics and biomechanics.get("is_warning", False))

        if is_danger:
            status_text = "[ NGUY HIỂM ]"
            theme_color = self.COLORS["danger_red"]
        elif is_warning:
            status_text = "[ CẢNH BÁO ]"
            theme_color = self.COLORS["warn_yellow"]
        else:
            status_text = "[ AN TOÀN ]"
            theme_color = self.COLORS["safe_green"]

        card_h = 100
        draw.rounded_rectangle([pad_x, y, self.sidebar_w - pad_x, y + card_h],
                               radius=6, fill=self.COLORS["card_bg"], outline=theme_color, width=1)

        # Tiêu đề Card
        draw.text((pad_x + 12, y + 8), "ĐÁNH GIÁ NGUY CƠ & AN TOÀN", font=self.font_caption, fill=self.COLORS["text_muted"])
        # Badge mức độ kèm chấm đèn tròn
        draw.ellipse([pad_x + 14, y + 30, pad_x + 22, y + 38], fill=theme_color)
        draw.text((pad_x + 28, y + 26), status_text, font=self.font_body_bold, fill=theme_color)
        draw.text((self.sidebar_w - pad_x - 70, y + 26), f"{danger_score}/10 ĐIỂM", font=self.font_body_bold, fill=theme_color)

        # 10-Segment LED Meter Bar
        bar_x = pad_x + 12
        bar_y = y + 54
        total_segs = 10
        seg_w = (self.sidebar_w - 2 * pad_x - 24 - (total_segs - 1) * 3) // total_segs
        for i in range(total_segs):
            seg_rect = [bar_x + i * (seg_w + 3), bar_y, bar_x + i * (seg_w + 3) + seg_w, bar_y + 10]
            if i < danger_score:
                draw.rectangle(seg_rect, fill=theme_color)
            else:
                draw.rectangle(seg_rect, fill=self.COLORS["led_off"])

        # Diễn giải rủi ro
        reason = diagnosis.get("danger_reason", "Bình thường")
        if biomechanics and biomechanics.get("alert"):
            reason = biomechanics["alert"]
        if len(reason) > 40:
            reason = reason[:38] + "..."
        draw.text((pad_x + 12, y + 74), f"Ghi chú: {reason}", font=self.font_caption, fill=self.COLORS["text_muted"])
        y += card_h + 14

        # --- SECTION 2: ĐIỀU PHỐI AI CLOUD PHÂN TẦNG ---
        card_diag_h = 150
        draw.rounded_rectangle([pad_x, y, self.sidebar_w - pad_x, y + card_diag_h],
                               radius=6, fill=self.COLORS["card_bg"], outline=self.COLORS["card_border"])

        draw.text((pad_x + 12, y + 8), "CHẨN ĐOÁN HÀNH VI TỰ NHIÊN", font=self.font_section, fill=self.COLORS["neon_cyan"])
        ts = diagnosis.get("timestamp", time.strftime("%H:%M:%S"))
        draw.text((self.sidebar_w - pad_x - 65, y + 10), ts, font=self.font_caption, fill=self.COLORS["text_muted"])

        # Nội dung hành động (Action) - Tự động bẻ dòng thông minh
        act_text = diagnosis.get("action", "Đang theo dõi...")
        wrapped_act_lines = self._wrap_text(act_text, max_chars=34)

        text_y = y + 32
        draw.text((pad_x + 12, text_y), "Hành động:", font=self.font_caption, fill=self.COLORS["text_cyan"])
        text_y += 16
        for line in wrapped_act_lines[:3]:
            draw.text((pad_x + 12, text_y), line, font=self.font_body, fill=self.COLORS["text_white"])
            text_y += 18

        # Ngữ cảnh (Context)
        ctx_text = diagnosis.get("context", "Trong phòng làm việc")
        if len(ctx_text) > 36:
            ctx_text = ctx_text[:34] + "..."
        text_y = max(text_y + 4, y + 105)
        draw.text((pad_x + 12, text_y), f"Ngữ cảnh: {ctx_text}", font=self.font_caption, fill=self.COLORS["text_muted"])

        # Dynamic Model Tier Badge Display
        tier_display = self.resolve_model_tier_display(diagnosis, metrics)
        draw.text((pad_x + 12, y + 128), f"Mô hình: Edge YOLOv8 + {tier_display}", font=self.font_caption, fill=self.COLORS["text_cyan"])

        y += card_diag_h + 14

        # --- SECTION 3: DETECTED OBJECTS & TARGETS ---
        card_obj_h = 70
        draw.rounded_rectangle([pad_x, y, self.sidebar_w - pad_x, y + card_obj_h],
                               radius=6, fill=self.COLORS["card_bg"], outline=self.COLORS["card_border"])

        draw.text((pad_x + 12, y + 8), "ĐỐI TƯỢNG PHÁT HIỆN (YOLOv8 EDGE)", font=self.font_caption, fill=self.COLORS["text_muted"])
        person_cnt = entities.get("person", 0)
        laptop_cnt = entities.get("laptop", 0)

        obj_str1 = f"NGƯỜI (Khung xương): {person_cnt}    LAPTOP: {laptop_cnt}"
        draw.text((pad_x + 12, y + 26), obj_str1, font=self.font_body_bold, fill=self.COLORS["text_white"])

        if biomechanics and "angle" in biomechanics:
            bio_str = f"Trục thân: {biomechanics['angle']:.0f}° | Tư thế: {biomechanics.get('posture', 'Bình thường')}"
            bio_color = self.COLORS["danger_red"] if is_danger else self.COLORS["text_cyan"]
            draw.text((pad_x + 12, y + 46), bio_str, font=self.font_caption, fill=bio_color)
        else:
            phone_cnt = entities.get("cell phone", 0)
            bottle_cnt = entities.get("bottle", 0) + entities.get("cup", 0)
            obj_str2 = f"ĐIỆN THOẠI: {phone_cnt}      CHAI/CỐC: {bottle_cnt}"
            draw.text((pad_x + 12, y + 46), obj_str2, font=self.font_body, fill=self.COLORS["text_muted"])

        y += card_obj_h + 14



        # --- SECTION 4: OS MULTITHREADED TELEMETRY (TRỌNG TÂM HĐH) ---
        card_os_h = 165
        draw.rounded_rectangle([pad_x, y, self.sidebar_w - pad_x, y + card_os_h],
                               radius=6, fill=self.COLORS["card_bg"], outline=self.COLORS["card_border"])

        draw.text((pad_x + 12, y + 8), "TÀI NGUYÊN HỆ ĐIỀU HÀNH (OS TELEMETRY)", font=self.font_section, fill=self.COLORS["neon_cyan"])

        # Đo vẽ CPU
        cpu_val = metrics.get("cpu_percent", metrics.get("cpu_total_pct", 0.0))
        self._draw_metric_bar(draw, pad_x + 12, y + 32, "CPU Utilization:", f"{cpu_val:.0f}%", cpu_val / 100.0)

        # Đo vẽ RAM
        ram_val = metrics.get("ram_percent", 0.0)
        self._draw_metric_bar(draw, pad_x + 12, y + 58, "RAM Usage:", f"{ram_val:.0f}%", ram_val / 100.0)

        # Đo vẽ GPU VRAM (Nhận diện chính xác phần cứng thực tế, không đoán mò)
        vram_used = metrics.get("gpu_vram_used", 0.0)
        vram_total = metrics.get("gpu_vram_total", 0.0)
        vram_ratio = min(1.0, max(0.0, vram_used / max(0.1, vram_total))) if vram_total > 0 else 0.0
        gpu_name = metrics.get("gpu_name")
        if not gpu_name or gpu_name.lower() in ("none", "cpu only", "unknown"):
            from core.metrics import get_hardware_gpu_name
            gpu_name = get_hardware_gpu_name()

        if gpu_name == "CPU":
            self._draw_metric_bar(draw, pad_x + 12, y + 84, f"Thiết bị ({gpu_name}):", "CPU Host (No GPU)", 0.0)
        else:
            self._draw_metric_bar(draw, pad_x + 12, y + 84, f"GPU VRAM ({gpu_name}):", f"{vram_used:.1f}/{vram_total:.1f} GB", vram_ratio)

        # Thông số luồng & Hàng đợi
        buf_size = metrics.get("queue_size", 0)
        max_buf = metrics.get("queue_max", 32)
        dropped = metrics.get("dropped_frames", 0)
        y_q = y + 114
        draw.text((pad_x + 12, y_q), f"Hàng đợi Bounded Buffer: {buf_size}/{max_buf} frames", font=self.font_caption, fill=self.COLORS["text_white"])
        draw.text((pad_x + 12, y_q + 16), f"Khung hình Drop: {dropped} frames (Flow Control)", font=self.font_caption, fill=self.COLORS["text_muted"])
        draw.text((pad_x + 12, y_q + 32), "Luồng HĐH: 1 Producer | 2 Consumers (YOLO+AI)", font=self.font_caption, fill=(100, 160, 200))
        y += card_os_h + 10

        # --- SECTION 5: SHORTCUTS ---
        draw.text((pad_x, self.height - 22), "[Q]: Thoát  |  [R]: Làm mới AI  |  [S]: Lưu ảnh",
                  font=self.font_caption, fill=self.COLORS["neon_cyan"])

        # Chuyển Pillow RGB sang OpenCV BGR
        return cv2.cvtColor(np.array(sidebar_img), cv2.COLOR_RGB2BGR)

    @staticmethod
    def resolve_model_tier_display(diagnosis: dict, metrics: dict) -> str:
        """Phân giải chuỗi hiển thị phân tầng mô hình (Tier-1 / Tier-2 / Tier-3) theo thời gian thực."""
        tier_str = diagnosis.get("model_tier_str") or metrics.get("model_tier_str")
        if tier_str:
            return tier_str if tier_str.startswith("●") else f"● {tier_str}"

        tier_val = (
            diagnosis.get("model_tier")
            or metrics.get("model_tier")
            or metrics.get("active_model_tier")
            or metrics.get("active_tier_name")
        )
        if tier_val:
            s = str(tier_val).strip()
            s_lower = s.lower()
            if "tier_1" in s_lower or "tier-1" in s_lower or "gemini 2" in s_lower or "gemini-2" in s_lower:
                return "● Tier-1 Gemini 2.0"
            elif "tier_2" in s_lower or "tier-2" in s_lower or "gemini 1" in s_lower or "gemini-1" in s_lower:
                return "● Tier-2 Gemini 1.5 Failover"
            elif "tier_3" in s_lower or "tier-3" in s_lower or "heuristic" in s_lower or "arbiter" in s_lower or "tự hành" in s_lower:
                return "● AI Tự Hành (Local Heuristic)"
            else:
                return s if s.startswith("●") else f"● {s}"

        return "● Tier-1 Gemini 2.0"

    def _draw_metric_bar(self, draw, x, y, label, val_str, ratio):
        draw.text((x, y), label, font=self.font_caption, fill=self.COLORS["text_muted"])
        draw.text((self.sidebar_w - 30 - 60, y), val_str, font=self.font_caption, fill=self.COLORS["text_white"])

        bar_y = y + 14
        bar_w = self.sidebar_w - 60
        bar_h = 5
        draw.rounded_rectangle([x, bar_y, x + bar_w, bar_y + bar_h], radius=2, fill=self.COLORS["led_off"])
        fill_w = int(bar_w * max(0.0, min(1.0, ratio)))
        fill_color = self.COLORS["neon_cyan"] if ratio < 0.75 else self.COLORS["warn_yellow"]
        if ratio > 0.90:
            fill_color = self.COLORS["danger_red"]
        if fill_w > 0:
            draw.rounded_rectangle([x, bar_y, x + fill_w, bar_y + bar_h], radius=2, fill=fill_color)

    def _wrap_text(self, text, max_chars=34):
        """Bẻ dòng văn bản tiếng Việt theo từ một cách mượt mà."""
        words = text.split()
        lines = []
        curr_line = []
        curr_len = 0
        for w in words:
            if curr_len + len(w) + 1 <= max_chars:
                curr_line.append(w)
                curr_len += len(w) + 1
            else:
                if curr_line:
                    lines.append(" ".join(curr_line))
                curr_line = [w]
                curr_len = len(w)
        if curr_line:
            lines.append(" ".join(curr_line))
        return lines

    def assemble_canvas(self, frame_camera, diagnosis, entities, metrics, danger_score, danger_level, fps=30.0, is_ai_busy=False):
        """Lắp ráp canvas 1280x720 Widescreen hoàn chỉnh (Left: Viewport, Right: Glass Sidebar)."""
        # 1. Resize khung camera sang 900x720 chính xác
        cam_vp = cv2.resize(frame_camera, (self.viewport_w, self.viewport_h))

        # 2. Vẽ trang trí HUD và cảnh báo lên Camera Viewport
        self.draw_camera_decorations(cam_vp, fps=fps, is_ai_busy=is_ai_busy, danger_level=danger_level)

        # 3. Render bảng điều khiển kính đen bên phải bằng Pillow
        sidebar_bgr = self.render_sidebar_pil(diagnosis, entities, metrics, danger_score, danger_level)

        # 4. Ghép ngang 2 vùng thành màn hình 1280x720
        canvas = np.hstack([cam_vp, sidebar_bgr])
        return canvas


# Tương thích ngược với các module gọi tên lớp HUD cũ và mới
SurveillanceHUDRenderer = CyberHUDRenderer
VideoHUDRenderer = CyberHUDRenderer

