"""
Deep Video Diagnosis & Semantic Q&A with Google Gemini 2.0 Flash.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

Đáp ứng 100% yêu cầu của Thầy Nguyễn Tấn Duẩn:
1. Nhận dạng tự do mọi hành vi trong video (không bị gò bó danh mục).
2. Phân loại theo nhóm: Hành vi làm việc, Thể thao, Sinh hoạt, Nguy hiểm.
3. Đánh giá Mức độ nguy hiểm (AN TOÀN / CẢNH BÁO / NGUY HIỂM) kèm thang điểm và lý do.
4. Thống kê tỷ lệ % thời lượng từng nhóm hành vi (Output 2).
5. Hỏi đáp tự nhiên: Người dùng hỏi "Có hành vi nguy hiểm nào không?", AI trả lời chi tiết mốc thời gian.
"""

import argparse
import json
import os
import sys

# Đảm bảo UTF-8 console output trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.gemini_analyzer import GeminiVideoAnalyzer


def main():
    parser = argparse.ArgumentParser(description="Chẩn đoán Video chuyên sâu & Hỏi đáp với Gemini Flash")
    parser.add_argument("--input", "-i", type=str, default="demo_synthetic.mp4", help="Đường dẫn file video cần chẩn đoán")
    parser.add_argument("--question", "-q", type=str, default="Có hành vi nguy hiểm nào trong video này không?", help="Câu hỏi cần AI trả lời")
    parser.add_argument("--api-key", "-k", type=str, default=None, help="Gemini API Key (hoặc đọc từ .env)")
    args = parser.parse_args()

    print("=" * 70)
    print("  HỆ THỐNG AI CHẨN ĐOÁN VIDEO TỰ DO & ĐÁNH GIÁ NGUY HIỂM (GEMINI 2.0 FLASH)")
    print("  Đề tài HĐH - GVHD: Thầy Nguyễn Tấn Duẩn")
    print("=" * 70)

    analyzer = GeminiVideoAnalyzer(api_key=args.api_key)

    if not analyzer.is_available():
        print("\n[!] CHƯA CẤU HÌNH GEMINI_API_KEY!")
        print("    Bạn có thể lấy API Key hoàn toàn MIỄN PHÍ tại: https://aistudio.google.com/")
        print("    Sau đó chạy lại với tham số:")
        print(f"    python tests/test_gemini_video.py --input {args.input} --api-key YOUR_API_KEY")
        print("    Hoặc lưu vào file .env: GEMINI_API_KEY=YOUR_API_KEY\n")
        return

    print(f"\n[+] Video đầu vào : {args.input}")
    print(f"[+] Câu hỏi yêu cầu: \"{args.question}\"")
    print("[+] Đang tải video lên Google Gemini và bắt đầu chẩn đoán...")

    report = analyzer.analyze_full_video(args.input, question=args.question)

    if "error" in report:
        print(f"\n[!] Lỗi từ Gemini: {report['error']}")
        return

    print("\n" + "=" * 70)
    print("  KẾT QUẢ CHẨN ĐOÁN HÀNH VI & ĐÁNH GIÁ NGUY HIỂM (OUTPUT 1 & 2 & 3)")
    print("=" * 70)

    # 1. Tóm tắt tổng quan
    print(f"\n📝 TỔNG QUAN VIDEO:")
    print(f"   {report.get('summary', 'Không có tóm tắt.')}")

    # 2. Đánh giá Mức độ nguy hiểm
    danger_level = report.get("overall_danger_level", "CHƯA RÕ")
    danger_score = report.get("danger_score", 0)
    icon = "🟢" if "TOAN" in danger_level else ("🟡" if "CANH" in danger_level else "🔴")
    print(f"\n⚠️ MỨC ĐỘ NGUY HIỂM: {icon} {danger_level} (Điểm rủi ro: {danger_score}/10)")
    print(f"   Lý do: {report.get('danger_reasons', 'N/A')}")

    # 3. Thống kê tỷ lệ % các nhóm hành vi
    print(f"\n📊 THỐNG KÊ PHÂN LOẠI HÀNH VI (TỶ LỆ %):")
    stats = report.get("statistics_percentages", {})
    if stats:
        for cat, pct in stats.items():
            bar = "█" * int(pct // 5)
            print(f"   - {cat.ljust(25)}: {pct:5.1f}%  |{bar}")

    # 4. Timeline chi tiết từng sự kiện
    print(f"\n🕒 TIMELINE CÁC SỰ KIỆN THEO THỜI GIAN:")
    timeline = report.get("timeline", [])
    if timeline:
        for ev in timeline:
            t_str = ev.get("timestamp", "N/A")
            act = ev.get("action", "N/A")
            cat = ev.get("category", "")
            d_level = ev.get("danger_level", "")
            print(f"   * [{t_str}] {act} ({cat}) -> Mức: {d_level}")
            if ev.get("notes"):
                print(f"     Ghi chú: {ev['notes']}")
    else:
        print("   Chưa có sự kiện chi tiết.")

    # 5. Câu trả lời tự nhiên (Semantic Q&A)
    print(f"\n💬 TRẢ LỜI CÂU HỎI:")
    print(f"   Hỏi: \"{args.question}\"")
    print(f"   AI: {report.get('user_answer', 'Gemini không có câu trả lời cụ thể.')}")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
