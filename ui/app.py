"""
Unified Web Dashboard: Giám Sát Hành Vi Video Thời Gian Thực & Phân Tích AI Đa Luồng.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.

Thiết kế giao diện chuẩn Radix Dark Theme, phân tách rõ 2 chế độ:
- Chế độ 1: 🎥 Giám Sát Trực Tiếp (Live Camera Cyber Command Center 1280x720).
- Chế độ 2: 📁 Phân Tích & Kết Xuất Video (Import Video -> Export Video Đã Dán Nhãn Bounding Box & Skeleton).
"""

import os
import sys
import time
import subprocess
import pandas as pd
import streamlit as st

# Đảm bảo đường dẫn gốc có trong sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# NVML đo VRAM card NVIDIA
try:
    import pynvml
    pynvml.nvmlInit()
    NVML_AVAILABLE = True
except Exception:
    NVML_AVAILABLE = False

import psutil
import torch
from core.config import CONFIG
from core.gemini_analyzer import GeminiVideoAnalyzer
from core.video_annotator import VideoAnnotatorEngine

# --- CẤU HÌNH TRANG STREAMLIT ---
st.set_page_config(
    page_title="Cyber Surveillance Hub - Hệ Điều Hành",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CUSTOM CSS RADIX DARK THEME (CHỐNG AI SLOP, TYPOGRAPHY CHUẨN) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Card container styles */
    .metric-card {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }

    .metric-title {
        font-size: 0.82rem;
        font-weight: 600;
        color: #8B949E;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }

    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #F0F6FC;
    }

    .metric-sub {
        font-size: 0.78rem;
        color: #58A6FF;
        margin-top: 4px;
    }

    /* Badge danger / safe */
    .badge-safe {
        background-color: rgba(46, 160, 67, 0.15);
        color: #3FB950;
        border: 1px solid rgba(46, 160, 67, 0.4);
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }

    .badge-danger {
        background-color: rgba(248, 81, 73, 0.15);
        color: #F85149;
        border: 1px solid rgba(248, 81, 73, 0.4);
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }

    /* Button styling */
    .stButton > button {
        border-radius: 6px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# Khởi tạo Session State
if "gemini" not in st.session_state:
    st.session_state.gemini = GeminiVideoAnalyzer()
if "annotator" not in st.session_state:
    st.session_state.annotator = VideoAnnotatorEngine()
if "last_analysis_report" not in st.session_state:
    st.session_state.last_analysis_report = None
if "last_annotated_video" not in st.session_state:
    st.session_state.last_annotated_video = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []


def get_live_hardware_metrics():
    """Đo đạc chỉ số HĐH chuẩn xác cho giao diện Web."""
    cpu_pct = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    
    vram_str = "N/A"
    vram_sub = "CPU Mode"
    if NVML_AVAILABLE:
        try:
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            m = pynvml.nvmlDeviceGetMemoryInfo(h)
            vram_str = f"{m.used / (1024**3):.1f} / {m.total / (1024**3):.1f} GB"
            vram_sub = f"NVIDIA RTX 5060 ({m.used/m.total*100:.0f}%)"
        except Exception:
            pass
    elif torch.cuda.is_available():
        vram_str = f"{torch.cuda.memory_reserved(0)/(1024**3):.1f} GB"
        vram_sub = "CUDA Active"

    return {
        "cpu": f"{cpu_pct:.0f}%",
        "ram": f"{ram.percent:.0f}%",
        "ram_detail": f"{ram.used / (1024**3):.1f} / {ram.total / (1024**3):.1f} GB",
        "vram": vram_str,
        "vram_sub": vram_sub
    }


# --- HEADER DASHBOARD ---
st.markdown("## 🛡️ Hệ Thống Giám Sát Hành Vi Video & Phân Tích AI Đa Luồng")
st.caption("Đồ án môn học: **Hệ Điều Hành** — GVHD: **Thầy Nguyễn Tấn Duẩn** | Kiến trúc Đa tầng: **RTX 5060 Edge + Gemini 3.5 Flash Lite**")

# --- HÀNG METRICS HỆ ĐIỀU HÀNH ---
hw = get_live_hardware_metrics()
col_m1, col_m2, col_m3, col_m4 = st.columns(4)

with col_m1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">CPU Toàn Hệ Thống</div>
        <div class="metric-value">{hw['cpu']}</div>
        <div class="metric-sub">Đa luồng Producer - Consumer</div>
    </div>
    """, unsafe_allow_html=True)

with col_m2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Bộ Nhớ RAM</div>
        <div class="metric-value">{hw['ram']}</div>
        <div class="metric-sub">{hw['ram_detail']}</div>
    </div>
    """, unsafe_allow_html=True)

with col_m3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">GPU VRAM (RTX 5060)</div>
        <div class="metric-value">{hw['vram']}</div>
        <div class="metric-sub">{hw['vram_sub']}</div>
    </div>
    """, unsafe_allow_html=True)

with col_m4:
    st.markdown("""
    <div class="metric-card">
        <div class="metric-title">Cơ Chế Điều Phối HĐH</div>
        <div class="metric-value">Active</div>
        <div class="metric-sub">Drop-Frame Flow Control (0ms delay)</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- TABS PHÂN CHIA 2 CHẾ ĐỘ RÕ RỆT ---
tab_live, tab_import = st.tabs([
    "🎥 CHẾ ĐỘ 1: GIÁM SÁT LIVE CAMERA (THỜI GIAN THỰC)",
    "📁 CHẾ ĐỘ 2: IMPORT VIDEO & XUẤT VIDEO DÁN NHÃN THÀNH PHẨM (QUY MÔ LỚN)"
])


# ==============================================================================
# TAB 1: LIVE CAMERA SURVEILLANCE
# ==============================================================================
with tab_live:
    col_live_info, col_live_act = st.columns([3, 2])

    with col_live_info:
        st.markdown("### 🖥️ Trung Tâm Giám Sát Điều Hành Cyber Command Center")
        st.markdown("""
        Chế độ chạy camera trực tiếp với giao diện chuyên dụng **1280x720 HD Widescreen**:
        - **Khung xương AI 17 khớp nối (YOLOv8-Pose)**: Theo dõi cử động cơ thể mượt mà ở **113 FPS** trên card RTX 5060.
        - **Biomechanical Threat Engine**: Tự động đo góc trục thân người và vận tốc cổ tay để **phát hiện té ngã / gục xuống bàn / bạo lực trong 0.05 giây**.
        - **Gemini 3.5 Flash Lite**: Chẩn đoán chi tiết ngữ cảnh và hành vi người thật, bảo vệ Free-tier tuyệt đối (tối đa 14 RPM).
        - **Cố định đường dẫn file**: Khởi chạy trực tiếp file gốc `main.py`, không bao giờ bị Windows hỏi lại quyền camera.
        """)

        st.info("💡 **Gợi ý kiểm chứng nhanh:** Bạn có thể giả vờ gục đầu xuống bàn $\\rightarrow$ Hệ thống sẽ lập tức đổi màu màn hình sang Đỏ rực và kích hoạt còi báo động té ngã!")

    with col_live_act:
        st.markdown("### 🚀 Khởi Chạy 1-Click")
        st.write("Bấm nút bên dưới để mở cửa sổ camera giám sát công nghệ cao:")
        
        btn_launch_cam = st.button("🔴 BẬT LIVE CAMERA CYBER HUD (1280x720)", type="primary", use_container_width=True)
        if btn_launch_cam:
            st.toast("Đang khởi động Camera qua main.py...")
            subprocess.Popen([sys.executable, "main.py", "--mode", "hud"])
            st.success("Đã gửi lệnh bật Camera! Vui lòng nhìn vào cửa sổ hiển thị trên thanh Taskbar của bạn.")

        st.markdown("---")
        st.markdown("#### ⌨️ Phím Tắt Điều Khiển Cửa Sổ Camera:")
        st.markdown("""
        - `[Q]`: Thoát và đóng camera an toàn.
        - `[R]`: Ép Gemini chẩn đoán khung hình ngay lập tức.
        - `[S]`: Chụp snapshot lưu bằng chứng an ninh vào thư mục `recordings/alerts/`.
        """)


# ==============================================================================
# TAB 2: IMPORT VIDEO & EXPORT ANNOTATED VIDEO
# ==============================================================================
with tab_import:
    st.markdown("### 📁 Phân Tích Video File & Kết Xuất Video Thành Phẩm Đã Dán Nhãn")
    st.caption("Nhận diện quy mô lớn: Quét Bounding Box & Bộ Khung Xương cho TẤT CẢ mọi người xuất hiện trong video.")

    col_up1, col_up2 = st.columns([3, 2])
    
    with col_up1:
        uploaded_video = st.file_uploader("Tải lên video kiểm tra (.mp4, .avi, .mov):", type=["mp4", "avi", "mov"])
    
    with col_up2:
        st.write("**Hoặc sử dụng video mẫu có sẵn trong hệ thống:**")
        use_sample = st.button("🎬 Dùng Video Mẫu Kiểm Thử (demo_synthetic.mp4)", use_container_width=True)

    target_video_path = None
    if uploaded_video is not None:
        target_video_path = os.path.join("recordings", f"input_{uploaded_video.name}")
        os.makedirs("recordings", exist_ok=True)
        with open(target_video_path, "wb") as f:
            f.write(uploaded_video.read())
    elif use_sample:
        target_video_path = "demo_synthetic.mp4"

    if target_video_path and os.path.exists(target_video_path):
        st.success(f"Đã nạp file video: `{target_video_path}`")
        
        # Nút kích hoạt phân tích toàn diện
        btn_process = st.button("⚡ BẮT ĐẦU PHÂN TÍCH & DÁN NHÃN KẾT XUẤT VIDEO", type="primary", use_container_width=True)

        if btn_process:
            progress_bar = st.progress(0, text="Khởi động Engine phân tích đa tầng...")
            progress_status = st.empty()
            
            # Callback cập nhật tiến độ
            def update_progress(cur, total, fps_val):
                pct = int((cur / max(1, total)) * 100)
                progress_bar.progress(pct, text=f"Đang phân tích khung hình {cur}/{total} ({pct}%) | Tốc độ xử lý: {fps_val:.0f} FPS trên GPU RTX 5060...")

            # 1. Bước 1: Xử lý video bằng YOLOv8-Pose trên GPU RTX 5060 & xuất video thành phẩm
            output_annotated_path = os.path.join("recordings", f"labeled_{int(time.time())}.mp4")
            
            with st.spinner("Đang chạy YOLOv8-Pose và Biomechanics trên card đồ họa RTX 5060..."):
                annot_res = st.session_state.annotator.process_video(
                    input_path=target_video_path,
                    output_path=output_annotated_path,
                    progress_callback=update_progress
                )
            
            progress_bar.progress(85, text="YOLOv8-Pose hoàn tất! Đang gọi Gemini 3.5 Flash Lite thẩm định bối cảnh chuyên sâu...")
            
            # 2. Bước 2: Gọi Gemini phân tích toàn diện video
            gemini_report = {}
            if st.session_state.gemini.is_available():
                with st.spinner("Gemini đang phân tích diễn biến và trả lời câu hỏi..."):
                    gemini_report = st.session_state.gemini.analyze_full_video(target_video_path)
            
            progress_bar.progress(100, text="Hoàn tất xử lý toàn bộ video!")
            time.sleep(0.5)
            progress_bar.empty()

            # Lưu vào Session State
            st.session_state.last_annotated_video = output_annotated_path
            st.session_state.last_analysis_report = {
                "annot": annot_res,
                "gemini": gemini_report,
                "input_path": target_video_path
            }

    # HIỂN THỊ KẾT QUẢ PHÂN TÍCH VÀ VIDEO THÀNH PHẨM (NẾU ĐÃ CÓ KẾT QUẢ)
    if st.session_state.last_analysis_report is not None:
        rep = st.session_state.last_analysis_report
        annot_info = rep["annot"]
        g_info = rep.get("gemini", {})

        st.markdown("---")
        st.markdown("## 🎬 KẾT QUẢ SO SÁNH & THÀNH PHẨM DÁN NHÃN")

        # SO SÁNH SONG SONG 2 VIDEO
        col_vid_orig, col_vid_annot = st.columns(2)
        with col_vid_orig:
            st.markdown("#### 📹 1. Video Gốc (Original)")
            if os.path.exists(rep["input_path"]):
                st.video(rep["input_path"])
        
        with col_vid_annot:
            st.markdown("#### 🎯 2. Video Thành Phẩm Đã Dán Nhãn (Labeled Output)")
            if os.path.exists(annot_info["output_path"]):
                st.video(annot_info["output_path"])
                
                # Nút tải xuống video thành phẩm
                with open(annot_info["output_path"], "rb") as vf:
                    st.download_button(
                        label="⬇️ TẢI XUỐNG VIDEO THÀNH PHẨM ĐÃ DÁN NHÃN (.mp4)",
                        data=vf.read(),
                        file_name=os.path.basename(annot_info["output_path"]),
                        mime="video/mp4",
                        type="primary",
                        use_container_width=True
                    )

        # THẺ BÁO CÁO MỨC ĐỘ NGUY HIỂM TỔNG QUAN
        st.markdown("### 📊 Báo Cáo Chẩn Đoán Chi Tiết (Output 1 & 2)")
        
        d_level = g_info.get("overall_danger_level", annot_info.get("overall_danger_level", "AN TOAN"))
        d_score = max(g_info.get("danger_score", 0), annot_info.get("max_danger_score", 0))
        d_reason = g_info.get("danger_reasons", annot_info.get("peak_danger_reason", "Bình thường"))

        col_res1, col_res2 = st.columns([1, 2])
        with col_res1:
            badge_class = "badge-danger" if "NGUY" in d_level else "badge-safe"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Đánh Giá An Ninh</div>
                <div class="metric-value"><span class="{badge_class}">{d_level}</span></div>
                <div class="metric-sub">Thang điểm rủi ro: <strong>{d_score} / 10</strong></div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_res2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Diễn Giải Rủi Ro & Bối Cảnh</div>
                <div style="font-size: 0.95rem; color: #E6EDF3; line-height: 1.5; margin-top: 4px;">
                    {d_reason}
                </div>
                <div class="metric-sub">Tổng thời lượng: {annot_info['duration_seconds']}s ({annot_info['total_frames']} frames) | Tốc độ xử lý: {annot_info['overall_fps']} FPS</div>
            </div>
            """, unsafe_allow_html=True)

        # BIỂU ĐỒ % THỐNG KÊ HÀNH VI
        col_chart, col_time = st.columns([3, 2])
        with col_chart:
            st.markdown("#### 📈 Thống Kê Phân Loại Hành Vi (%)")
            pct_data = g_info.get("statistics_percentages") or annot_info.get("action_percentages", {})
            if pct_data:
                df_chart = pd.DataFrame(list(pct_data.items()), columns=["Nhóm Hành Vi", "Tỷ Lệ (%)"]).set_index("Nhóm Hành Vi")
                st.bar_chart(df_chart, color="#00F0FF")

        with col_time:
            st.markdown("#### 🕒 Dòng Thời Gian Sự Kiện (Timeline)")
            t_data = g_info.get("timeline") or annot_info.get("timeline", [])
            if t_data:
                st.dataframe(pd.DataFrame(t_data), use_container_width=True)
            else:
                st.info("Không có biến cố nguy hiểm nào xảy ra trong suốt video.")

        # KHUNG CHAT SEMANTIC Q&A VỚI GEMINI VỀ VIDEO
        st.markdown("---")
        st.markdown("### 💬 Trợ Lý AI Semantic Q&A (Hỏi Đáp Tự Nhiên Về Video)")
        st.caption("Đặt bất kỳ câu hỏi nào về các nhân vật, hành động, hoặc sự cố xuất hiện trong video.")

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_q = st.chat_input("Hỏi AI (Ví dụ: 'Trong video có hành vi té ngã hay xô xát nào không?')...")
        if user_q:
            st.session_state.chat_messages.append({"role": "user", "content": user_q})
            with st.chat_message("user"):
                st.markdown(user_q)

            with st.chat_message("assistant"):
                with st.spinner("Gemini đang tra cứu diễn biến video..."):
                    context_prompt = f"Video được phân tích: {g_info.get('summary', 'Video giám sát')}. Các sự kiện: {t_data}."
                    answer = st.session_state.gemini.ask_about_events(user_q, [{"action": context_prompt}])
                    st.markdown(answer)
                    st.session_state.chat_messages.append({"role": "assistant", "content": answer})
