"""
Cyber Surveillance Command Center HUD Renderer.
Xây dựng giao diện HUD tương lai (Sci-Fi / Command Center 1280x720 Widescreen).
Hỗ trợ Unicode tiếng Việt đầy đủ bằng Pillow, loại bỏ lỗi font và hiện tượng đè che mặt.
"""

import cv2
import numpy as np
import time
from PIL import Image, ImageDraw, ImageFont


class CyberHUDRenderer:
    def __init__(self, width=1280, height=720, viewport_w=900, sidebar_w=380):
        self.width = width
        self.height = height
        self.viewport_w = viewport_w
        self.viewport_h = height
        self.sidebar_w = sidebar_w

        # Bảng màu chuẩn Cyberpunk / Radix Dark Theme (RGB cho PIL, BGR cho OpenCV)
        self.COLORS = {
            "bg_dark": (15, 20, 28),          # Nền kính đen sidebar
            "card_bg": (23, 32, 44),          # Nền thẻ thông số
            "card_border": (45, 55, 72),      # Viền thẻ
            "neon_cyan": (0, 240, 255),       # Xanh neon chủ đạo
            "safe_green": (16, 185, 129),     # Xanh lá an toàn
            "warn_yellow": (245, 158, 11),    # Vàng cam cảnh báo
            "danger_red": (239, 68, 68),      # Đỏ rực nguy hiểm
            "text_white": (245, 247, 250),    # Trắng sáng
            "text_muted": (156, 163, 175),    # Xám phụ đề
            "text_cyan": (125, 211, 252),     # Xanh nhạt
            "led_off": (40, 48, 60),          # Đèn LED tắt
        }

        # Khởi tạo font chữ hệ thống hỗ trợ tiếng Việt Unicode
        self.font_title = self._load_font(["segoeui.ttf", "arial.ttf"], 18, bold=True)
        self.font_sub = self._load_font(["segoeui.ttf", "arial.ttf"], 12)
        self.font_section = self._load_font(["segoeuib.ttf", "arialbd.ttf", "arial.ttf"], 13, bold=True)
        self.font_body = self._load_font(["segoeui.ttf", "arial.ttf"], 13)
        self.font_body_bold = self._load_font(["segoeuib.ttf", "arialbd.ttf", "arial.ttf"], 13, bold=True)
        self.font_caption = self._load_font(["segoeui.ttf", "arial.ttf"], 11)

    def _load_font(self, font_names, size, bold=False):
        for name in font_names:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                pass
        return ImageFont.load_default()

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
        """Vẽ bộ khung xương AI Neural Skeleton 17 khớp nối kiểu Cyberpunk Neon (tinh tế, không che mặt)."""
        if kpts is None or len(kpts) == 0:
            return

        # 1. Vẽ các đường xương phát sáng trên cơ thể
        for (i, j) in self.SKELETON_PAIRS:
            if i < len(kpts) and j < len(kpts):
                p1, p2 = kpts[i], kpts[j]
                conf1 = p1[2] if len(p1) > 2 else 1.0
                conf2 = p2[2] if len(p2) > 2 else 1.0
                if conf1 > 0.40 and conf2 > 0.40:
                    pt1 = (int(p1[0]), int(p1[1]))
                    pt2 = (int(p2[0]), int(p2[1]))
                    # Đường phát sáng thanh mảnh
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

    def draw_corner_bracket_bbox(self, img, x1, y1, x2, y2, color_bgr, label="", score=0.0):
        """Vẽ khung Bounding Box kiểu góc ngoặc Sci-Fi (Corner Brackets)."""
        w = x2 - x1
        h = y2 - y1
        corner_len = max(12, min(int(min(w, h) * 0.25), 25))
        thickness = 2

        # 1. Vẽ 4 góc ngoặc công nghệ
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

        # 2. Khung viền mờ nối các góc
        cv2.rectangle(img, (x1, y1), (x2, y2), color_bgr, 1, lineType=cv2.LINE_4)

        # 3. Tâm ngắm tâm điểm nhẹ
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.drawMarker(img, (cx, cy), color_bgr, cv2.MARKER_CROSS, 8, 1)

        # 4. Nhãn đính kèm nổi phía trên
        if label:
            tag_text = f"[{label.upper()} {int(score * 100)}%]" if score > 0 else f"[{label.upper()}]"
            font_scale = 0.42
            (tw, th), _ = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 8, y1), (15, 20, 28), -1)
            cv2.rectangle(img, (x1, max(0, y1 - th - 8)), (x1 + tw + 8, y1), color_bgr, 1)
            cv2.putText(img, tag_text, (x1 + 4, max(th + 2, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, color_bgr, 1, cv2.LINE_AA)

    def draw_camera_decorations(self, frame_vp, fps=30.0, is_ai_busy=False, danger_level="AN TOAN"):
        """Vẽ các chỉ số HUD phụ xung quanh vùng camera nhưng không che đối tượng."""
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

        # 4. Nếu đang gửi ảnh cho AI Gemini phân tích, hiển thị radar nhỏ ở đáy camera
        if is_ai_busy:
            cv2.rectangle(frame_vp, (w // 2 - 95, h - 35), (w // 2 + 95, h - 10), (15, 20, 28), -1)
            cv2.rectangle(frame_vp, (w // 2 - 95, h - 35), (w // 2 + 95, h - 10), (0, 240, 255), 1)
            cv2.circle(frame_vp, (w // 2 - 75, h - 23), 5, (0, 240, 255), -1)
            cv2.putText(frame_vp, "AI CLOUD ANALYZING...", (w // 2 - 60, h - 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 240, 255), 1, cv2.LINE_AA)

        # 5. Viền cảnh báo động toàn màn hình nếu nguy hiểm
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
        draw.text((pad_x, y), "CYBER-SURVEILLANCE HUD", font=self.font_title, fill=self.COLORS["neon_cyan"])
        y += 24
        draw.text((pad_x, y), "ĐỒ ÁN HỆ ĐIỀU HÀNH - GVHD: NGUYỄN TẤN DUẨN", font=self.font_caption, fill=self.COLORS["text_muted"])
        y += 18

        # Status Pill: ONLINE
        draw.rounded_rectangle([pad_x, y, pad_x + 155, y + 22], radius=4, fill=self.COLORS["card_bg"], outline=self.COLORS["card_border"])
        draw.ellipse([pad_x + 8, y + 7, pad_x + 16, y + 15], fill=self.COLORS["safe_green"])
        draw.text((pad_x + 22, y + 3), "ONLINE  ●  LOCK-ON", font=self.font_caption, fill=self.COLORS["safe_green"])
        y += 32

        # --- SECTION 1: THREAT MATRIX & DANGER RADAR ---
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
        draw.text((pad_x + 12, y + 8), "THREAT MATRIX (RỦI RO)", font=self.font_caption, fill=self.COLORS["text_muted"])
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

        # --- SECTION 2: HUMAN-LIKE AI DIAGNOSIS (GEMINI 3.5 FLASH LITE) ---
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
        draw.text((pad_x + 12, y + 128), "Mô hình: YOLOv8 (Edge RTX) + Gemini 3.5 Flash (Cloud 4s)", font=self.font_caption, fill=(80, 140, 180))

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
        cpu_val = metrics.get("cpu_percent", 0.0)
        self._draw_metric_bar(draw, pad_x + 12, y + 32, "CPU Utilization:", f"{cpu_val:.0f}%", cpu_val / 100.0)

        # Đo vẽ RAM
        ram_val = metrics.get("ram_percent", 0.0)
        self._draw_metric_bar(draw, pad_x + 12, y + 58, "RAM Usage:", f"{ram_val:.0f}%", ram_val / 100.0)

        # Đo vẽ GPU RTX 5060 VRAM
        vram_used = metrics.get("gpu_vram_used", 0.0)
        vram_total = metrics.get("gpu_vram_total", 8.0)
        vram_ratio = min(1.0, max(0.0, vram_used / max(1.0, vram_total)))
        self._draw_metric_bar(draw, pad_x + 12, y + 84, "GPU VRAM (RTX 5060):", f"{vram_used:.1f}/{vram_total:.1f} GB", vram_ratio)

        # Thông số luồng & Hàng đợi
        buf_size = metrics.get("queue_size", 0)
        max_buf = metrics.get("queue_max", 5)
        dropped = metrics.get("dropped_frames", 0)
        y_q = y + 114
        draw.text((pad_x + 12, y_q), f"Hàng đợi Buffer: {buf_size}/{max_buf} frames", font=self.font_caption, fill=self.COLORS["text_white"])
        draw.text((pad_x + 12, y_q + 16), f"Khung hình Drop: {dropped} frames (Flow Control)", font=self.font_caption, fill=self.COLORS["text_muted"])
        draw.text((pad_x + 12, y_q + 32), "Luồng HĐH: 1 Producer | 2 Consumers (YOLO+AI)", font=self.font_caption, fill=(100, 160, 200))
        y += card_os_h + 10

        # --- SECTION 5: SHORTCUTS ---
        draw.text((pad_x, self.height - 22), "[Q]: Thoát  |  [R]: Ép AI phân tích  |  [S]: Lưu ảnh",
                  font=self.font_caption, fill=self.COLORS["neon_cyan"])

        # Chuyển Pillow RGB sang OpenCV BGR
        return cv2.cvtColor(np.array(sidebar_img), cv2.COLOR_RGB2BGR)

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
