"""
Quick Webcam Clip Recorder (Tạo video mẫu 5-10 giây để test dán nhãn).
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn
"""

import sys
import time
import cv2

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def record_sample(output_file: str = "sample_test.mp4", duration_sec: int = 5):
    print("=" * 70)
    print(f"  QUAY THỬ MỘT CLIP {duration_sec} GIÂY TỪ WEBCAM ĐỂ TEST DÁN NHÃN VIDEO")
    print("=" * 70)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[!] Không mở được webcam.")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    fps = 30.0

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_file, fourcc, fps, (width, height))

    print(f"[+] Đang quay video trong {duration_sec} giây... (Hãy cử động tay, gõ máy hoặc vẫy tay)")
    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)

        elapsed = time.time() - start_time
        remaining = max(0.0, duration_sec - elapsed)

        # Hiển thị thời gian còn lại
        display_frame = frame.copy()
        cv2.putText(display_frame, f"REC: {remaining:.1f}s", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        cv2.imshow("Dang Quay Video Mau (Nhan 'q' de dung)", display_frame)

        out.write(frame)

        if elapsed >= duration_sec or (cv2.waitKey(1) & 0xFF) == ord('q'):
            break

    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print(f"\n[+] Đã lưu clip mẫu thành công tại: {output_file}")
    print(f"Bây giờ bạn có thể chạy: python tests/test_video_file.py --input {output_file}")


if __name__ == "__main__":
    record_sample()
