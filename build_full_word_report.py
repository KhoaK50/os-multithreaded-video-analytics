# -*- coding: utf-8 -*-
"""
Script to build the comprehensive Word document: BAO_CAO_CONG_NGHE_VA_KIEN_TRUC_HE_THONG.docx
Assembles content from report_data_part1 and report_data_part2.
"""

import os
import sys
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

from report_data_part1 import (
    METADATA,
    EXECUTIVE_SUMMARY,
    SECTION_1_COMPONENTS,
    SECTION_2_COMPONENTS
)
from report_data_part2 import (
    SECTION_3_COMPONENTS,
    SECTION_4_COMPONENTS,
    SECTION_5_COMPONENTS,
    COMPARISON_MATRIX_DATA,
    CONCLUSION_PARAGRAPHS
)

def set_cell_background(cell, hex_color):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_table_borders(table, color="CBD5E1", sz="4", val="single"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideV w:val="none"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def add_callout(doc, text_list, title="ĐIỂM CỐT LÕI HỆ THỐNG", bg_color="F1F5F9", border_color="2563EB"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = tbl.cell(0, 0)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="{border_color}"/>'
        f'  <w:top w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:bottom w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    run_title = p.add_run(f"■ {title.upper()}\n")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(10.5)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(15, 23, 42)
    
    for item in text_list:
        p2 = cell.add_paragraph()
        p2.paragraph_format.space_before = Pt(1)
        p2.paragraph_format.space_after = Pt(2)
        p2.paragraph_format.line_spacing = 1.15
        run = p2.add_run(item)
        run.font.name = "Arial"
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(51, 65, 85)
        
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def format_heading_1(p, text):
    p.paragraph_format.space_before = Pt(20)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = RGBColor(15, 23, 42)

def format_heading_2(p, text):
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = "Arial"
    run.font.size = Pt(12)
    run.font.bold = True
    run.font.color.rgb = RGBColor(30, 58, 138)

def add_body_p(doc, text="", space_after=5):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    if text:
        run = p.add_run(text)
        run.font.name = "Arial"
        run.font.size = Pt(10.5)
        run.font.color.rgb = RGBColor(30, 41, 59)
    return p

def add_six_points_analysis(doc, comp_id, comp_name, p_reason, p_why_not, p_pros, p_cons, p_meaning, p_impact):
    h2 = doc.add_paragraph()
    format_heading_2(h2, f"Thành phần {comp_id}: {comp_name}")
    
    points = [
        ("📌 1. Lý do lựa chọn giải pháp:", p_reason, RGBColor(30, 64, 175)),
        ("🔄 2. Tại sao không chọn các phương án khác? (Đối soát chuyên sâu):", p_why_not, RGBColor(180, 83, 9)),
        ("⚡ 3. Ưu điểm kỹ thuật vượt trội:", p_pros, RGBColor(21, 128, 61)),
        ("⚠️ 4. Nhược điểm & Giới hạn kỹ thuật cần lưu ý:", p_cons, RGBColor(185, 28, 28)),
        ("🎯 5. Ý nghĩa kiến trúc & Giá trị học thuật Hệ Điều Hành:", p_meaning, RGBColor(109, 40, 217)),
        ("🔗 6. Tác động & Mối liên hệ chéo với các thành phần khác:", p_impact, RGBColor(14, 116, 144))
    ]
    
    for title, content, col in points:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.left_indent = Inches(0.2)
        
        run_title = p.add_run(f"{title}\n")
        run_title.font.name = "Arial"
        run_title.font.size = Pt(10)
        run_title.font.bold = True
        run_title.font.color.rgb = col
        
        run_content = p.add_run(content)
        run_content.font.name = "Arial"
        run_content.font.size = Pt(10)
        run_content.font.color.rgb = RGBColor(51, 65, 85)

def build_document():
    doc = docx.Document()
    
    # 1. Page Margins: 1 inch (72 pt) all around
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
        # Configure Header & Footer
        footer = section.footer
        p_ft = footer.paragraphs[0]
        p_ft.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_ft = p_ft.add_run("Báo cáo Kiến trúc & Công nghệ — OS Multithreaded Video Analytics")
        r_ft.font.name = "Arial"
        r_ft.font.size = Pt(8.5)
        r_ft.font.color.rgb = RGBColor(148, 163, 184)
    
    # Set default style font
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Arial'
    style_normal.font.size = Pt(10.5)
    style_normal.font.color.rgb = RGBColor(30, 41, 59)
    
    # 2. Cover / Title Block
    p_course = doc.add_paragraph()
    p_course.paragraph_format.space_before = Pt(0)
    p_course.paragraph_format.space_after = Pt(4)
    r_course = p_course.add_run(METADATA["course_title"])
    r_course.font.name = "Arial"
    r_course.font.size = Pt(11)
    r_course.font.bold = True
    r_course.font.color.rgb = RGBColor(30, 58, 138)
    
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(4)
    p_title.paragraph_format.space_after = Pt(6)
    r_title = p_title.add_run(METADATA["project_title"])
    r_title.font.name = "Arial"
    r_title.font.size = Pt(18)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(15, 23, 42)
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(12)
    r_sub = p_sub.add_run(METADATA["subtitle"])
    r_sub.font.name = "Arial"
    r_sub.font.size = Pt(11.5)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(71, 85, 105)
    
    # Meta Info Card
    meta_box = [
        f"• Đơn vị thực hiện: {METADATA['author']}",
        f"• Thời gian hoàn thành: {METADATA['date']}",
        f"• Tiêu chuẩn kiến trúc: {METADATA['version']}",
        "• Phạm vi đối soát: 100% mã nguồn backend Python, mô hình AI đa tầng và frontend giao diện web không AI-slop."
    ]
    add_callout(doc, meta_box, title="THÔNG TIN HỒ SƠ THIẾT KẾ KỸ THUẬT", bg_color="F8FAFC", border_color="0EA5E9")
    
    # 3. Lời mở đầu & Tóm tắt điều hành
    h1_exec = doc.add_paragraph()
    format_heading_1(h1_exec, "LỜI MỞ ĐẦU & TÓM TẮT ĐIỀU HÀNH (EXECUTIVE SUMMARY)")
    for p_text in EXECUTIVE_SUMMARY:
        add_body_p(doc, p_text, space_after=6)
        
    callout_pillars = [
        "Trụ cột 1: Kiến trúc Đa luồng Bounded Buffer Producer-Consumer tuân thủ nghiêm ngặt nguyên lý Hệ Điều Hành kinh điển, khống chế bộ nhớ đệm an toàn tuyệt đối và triệt tiêu độ trễ hiển thị.",
        "Trụ cột 2: Thị giác máy tính biên (Edge Vision) với YOLOv8-pose và Optical Motion Engine chạy 100% cục bộ trên GPU RTX 5060, đạt tốc độ > 80 FPS với chi phí đúng 0 token.",
        "Trụ cột 3: Điều phối mô hình Cloud AI phân tầng tự động (Hierarchical Failover: Tier-1 Gemini 3.8 -> Tier-2 Gemini 3.5 -> Tier-3 Heuristic Arbiter) với cơ chế tự phục hồi sau 60s và khống chế chi phí < 1,500 tokens/video.",
        "Trụ cột 4: Chuẩn mực giao diện người dùng bài trừ 100% AI Slop, sử dụng Micro-SVG đơn sắc, Băng chuyền dòng sự kiện toàn cảnh và hỗ trợ hai chế độ sáng/tối chuẩn WCAG 2.1 AA."
    ]
    add_callout(doc, callout_pillars, title="BỐN TRỤ CỘT KIẾN TRÚC CỐT LÕI CỦA HỆ THỐNG", bg_color="EFF6FF", border_color="2563EB")
    
    # 4. PHẦN I: TẦNG HỆ ĐIỀU HÀNH & LẬP TRÌNH ĐA LUỒNG
    h1_sec1 = doc.add_paragraph()
    format_heading_1(h1_sec1, "PHẦN I: TẦNG HỆ ĐIỀU HÀNH & LẬP TRÌNH ĐA LUỒNG (OS & CONCURRENCY LAYER)")
    add_body_p(doc, (
        "Tầng hệ điều hành đóng vai trò là 'trái tim cơ học' của toàn bộ hệ thống. Mục tiêu cốt tử là phân tách rạch ròi "
        "giữa tốc độ thu nhận khung hình I/O phần cứng cố định (Hardware I/O Pace: 30 FPS) và tốc độ suy luận trí tuệ nhân tạo (Compute Bound Pace). "
        "Dưới đây là phân tích chi tiết 4 quyết định kỹ thuật trọng tâm tại tầng này."
    ), space_after=8)
    
    for comp in SECTION_1_COMPONENTS:
        add_six_points_analysis(
            doc, comp["id"], comp["name"],
            comp["reason"], comp["why_not"], comp["pros"], comp["cons"], comp["meaning"], comp["impact"]
        )
        
    # 5. PHẦN II: TẦNG THỊ GIÁC MÁY TÍNH & ĐỘNG HỌC BIÊN
    h1_sec2 = doc.add_paragraph()
    format_heading_1(h1_sec2, "PHẦN II: TẦNG THỊ GIÁC MÁY TÍNH & ĐỘNG HỌC BIÊN (EDGE VISION & KINEMATICS LAYER)")
    add_body_p(doc, (
        "Tầng thị giác biên chịu trách nhiệm thực thi toàn bộ các tác vụ xử lý hình ảnh frame-by-frame ngay trên phần cứng cục bộ. "
        "Triết lý thiết kế cốt lõi tại tầng này là 'Zero-Guesswork' (Triệt tiêu đoán mò): Mọi kết luận về hành vi bạo lực, "
        "té ngã hay công thái học đều phải được giải thích dựa trên các quy luật cơ học động học vật lý thực nghiệm (Physics-based Explainability)."
    ), space_after=8)
    
    for comp in SECTION_2_COMPONENTS:
        add_six_points_analysis(
            doc, comp["id"], comp["name"],
            comp["reason"], comp["why_not"], comp["pros"], comp["cons"], comp["meaning"], comp["impact"]
        )
        
    # 6. PHẦN III: TẦNG TRÍ TUỆ NHÂN TẠO PHÂN TẦNG & BẢO VỆ HẠN MỨC
    h1_sec3 = doc.add_paragraph()
    format_heading_1(h1_sec3, "PHẦN III: TẦNG TRÍ TUỆ NHÂN TẠO PHÂN TẦNG & BẢO VỆ HẠN MỨC (CLOUD AI & ORCHESTRATOR LAYER)")
    add_body_p(doc, (
        "Trong khi AI biên thực hiện nhiệm vụ 'nhìn thấy các điểm ảnh', AI đám mây đóng vai trò 'hiểu được ý nghĩa câu chuyện'. "
        "Tuy nhiên, Cloud AI luôn đi kèm hai thách thức khổng lồ: Rào cản tốc độ gọi (15 RPM / lỗi 429) và chi phí token. "
        "Tầng Điều Phối Mô Hình được xây dựng để kiểm soát tuyệt đối cả hai rủi ro trên."
    ), space_after=8)
    
    for comp in SECTION_3_COMPONENTS:
        add_six_points_analysis(
            doc, comp["id"], comp["name"],
            comp["reason"], comp["why_not"], comp["pros"], comp["cons"], comp["meaning"], comp["impact"]
        )

    # 7. PHẦN IV: TẦNG MẠNG, NHẬP LIỆU & XỬ LÝ VIDEO
    h1_sec4 = doc.add_paragraph()
    format_heading_1(h1_sec4, "PHẦN IV: TẦNG MẠNG, NHẬP LIỆU & XỬ LÝ VIDEO (NETWORK & INGESTION LAYER)")
    add_body_p(doc, (
        "Hạ tầng mạng và nhập liệu đảm bảo tính linh hoạt cao nhất cho người vận hành: Từ việc cắm camera trực tiếp tại chỗ, "
        "kéo thả file video có sẵn trong máy tính, cho đến việc dán đường liên kết video từ hơn 1,000 nền tảng mạng xã hội khác nhau."
    ), space_after=8)
    
    for comp in SECTION_4_COMPONENTS:
        add_six_points_analysis(
            doc, comp["id"], comp["name"],
            comp["reason"], comp["why_not"], comp["pros"], comp["cons"], comp["meaning"], comp["impact"]
        )

    # 8. PHẦN V: TẦNG TRỰC QUAN HÓA & GIAO DIỆN NGƯỜI DÙNG
    h1_sec5 = doc.add_paragraph()
    format_heading_1(h1_sec5, "PHẦN V: TẦNG TRỰC QUAN HÓA & GIAO DIỆN NGƯỜI DÙNG (UI/UX - ANTI-AI SLOP LAYER)")
    add_body_p(doc, (
        "Giao diện người dùng là nơi hội tụ toàn bộ trí tuệ kỹ thuật của hệ thống. "
        "Dự án áp dụng bộ tiêu chuẩn thiết kế khắt khe: Triệt tiêu hoàn toàn A.I. Slop, đưa các thông số vận hành của Hệ Điều Hành "
        "lên vị trí trung tâm và cung cấp các công cụ tương tác trực giác theo dòng thời gian thực."
    ), space_after=8)
    
    for comp in SECTION_5_COMPONENTS:
        add_six_points_analysis(
            doc, comp["id"], comp["name"],
            comp["reason"], comp["why_not"], comp["pros"], comp["cons"], comp["meaning"], comp["impact"]
        )

    # 9. PHẦN VI: BẢNG TỔNG HỢP ĐỐI SOÁT TOÀN DIỆN 19 THÀNH PHẦN KỸ THUẬT
    h1_sec6 = doc.add_paragraph()
    format_heading_1(h1_sec6, "PHẦN VI: BẢNG TỔNG HỢP ĐỐI SOÁT TOÀN DIỆN 19 THÀNH PHẦN KỸ THUẬT")
    add_body_p(doc, (
        "Bảng dưới đây tổng hợp một cách cô đọng và toàn diện 19 quyết định kỹ thuật của dự án, "
        "đối chiếu trực diện với các phương án thay thế bị loại bỏ và nêu bật lý do kỹ thuật cốt lõi giải thích tại sao hệ thống lại chọn phương án đó."
    ), space_after=8)
    
    # Create Table: 4 cols
    table = doc.add_table(rows=1, cols=4)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table, color="CBD5E1", sz="4", val="single")
    
    # Header Row
    headers = [
        ("THÀNH PHẦN KIẾN TRÚC", Inches(1.4)),
        ("GIẢI PHÁP ĐƯỢC CHỌN", Inches(1.8)),
        ("PHƯƠNG ÁN LOẠI BỎ", Inches(1.5)),
        ("LÝ DO KỸ THUẬT CỐT LÕI", Inches(2.3))
    ]
    hdr_cells = table.rows[0].cells
    for i, (title, width) in enumerate(headers):
        hdr_cells[i].width = width
        set_cell_background(hdr_cells[i], "1E293B")  # Dark Slate
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=140, right=140)
        p = hdr_cells[i].paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(title)
        run.font.name = "Arial"
        run.font.size = Pt(9)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)
        
    # Populate Rows
    for row_idx, (comp_name, chosen_sol, discarded_sol, core_reason) in enumerate(COMPARISON_MATRIX_DATA):
        row_cells = table.add_row().cells
        bg_col = "F8FAFC" if (row_idx % 2 == 1) else "FFFFFF"
        for c_idx, text in enumerate([comp_name, chosen_sol, discarded_sol, core_reason]):
            row_cells[c_idx].width = headers[c_idx][1]
            set_cell_background(row_cells[c_idx], bg_col)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=120, right=120)
            p = row_cells[c_idx].paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.15
            run = p.add_run(text)
            run.font.name = "Arial"
            run.font.size = Pt(8.5)
            if c_idx == 0:
                run.font.bold = True
                run.font.color.rgb = RGBColor(15, 23, 42)
            elif c_idx == 1:
                run.font.color.rgb = RGBColor(30, 64, 175)
                run.font.bold = True
            elif c_idx == 2:
                run.font.color.rgb = RGBColor(180, 83, 9)
            else:
                run.font.color.rgb = RGBColor(51, 65, 85)
                
    doc.add_paragraph().paragraph_format.space_after = Pt(12)
    
    # 10. PHẦN VII: ĐÁNH GIÁ TOÀN DIỆN & HƯỚNG PHÁT TRIỂN TƯƠNG LAI
    h1_sec7 = doc.add_paragraph()
    format_heading_1(h1_sec7, "PHẦN VII: ĐÁNH GIÁ TOÀN DIỆN, GIỚI HẠN & HƯỚNG PHÁT TRIỂN")
    for p_text in CONCLUSION_PARAGRAPHS:
        add_body_p(doc, p_text, space_after=6)
        
    callout_future = [
        "1. Khả năng mở rộng đa luồng phân tán (Distributed Multi-stream): Mở rộng từ 1 camera lên cụm 16-32 luồng camera RTSP đồng thời thông qua kiến trúc Worker Process Pool và bộ nhớ chia sẻ POSIX Shared Memory.",
        "2. Tăng tốc phần cứng TensorRT / ONNX Runtime: Biên dịch lại YOLOv8-pose sang định dạng FP16 TensorRT Engine để đẩy tốc độ suy luận từ 80 FPS lên trên 180 FPS trên card đồ họa NVIDIA RTX thế hệ mới.",
        "3. Tích hợp Mô hình Ngôn ngữ Nhỏ Cục bộ (Edge SLM): Triển khai mô hình Gemma-2B hoặc Phi-3-mini lượng tử hóa 4-bit chạy trực tiếp trên GPU để đảm nhận vai trò chẩn đoán bối cảnh ngữ nghĩa hoàn toàn không cần Internet."
    ]
    add_callout(doc, callout_future, title="BA HƯỚNG MỞ RỘNG VÀ NÂNG CẤP TRỌNG TÂM TRONG TƯƠNG LAI", bg_color="F0FDF4", border_color="16A34A")
    
    # Save output file
    output_filename = "BAO_CAO_CONG_NGHE_VA_KIEN_TRUC_HE_THONG.docx"
    doc.save(output_filename)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(f"[SUCCESS] Da tao thanh cong tep tai lieu: {os.path.abspath(output_filename)}")
    return output_filename

if __name__ == "__main__":
    build_document()
