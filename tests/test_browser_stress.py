"""
Empirical Stress Test Suite: Network & Failure Modes for open_browser_when_ready
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.
Challenger: challenger_m1_2 (Milestone 1 Network & Failure Modes Stress Verification)

Tests:
1. test_01_server_never_responds_timeout
2. test_02_server_returns_500_internal_error
3. test_03_server_returns_503_service_unavailable
4. test_04_server_returns_404_not_found
5. test_05_delayed_startup_connection_refused_recovery
6. test_06_delayed_readiness_503_to_200_recovery
7. test_07_hanging_socket_black_hole_resilience
8. test_08_per_request_timeout_boundary_analysis
9. test_09_concurrency_stress_and_no_connection_refused
10. test_10_simulated_connection_delay_prevents_err_connection_refused
11. test_11_fastapi_trailing_slash_edge_case_investigation
"""

import sys
import os
import time
import socket
import threading
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

# Đảm bảo import từ thư mục gốc
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from core.web_server import app
from main import open_browser_when_ready


def get_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestBrowserReadinessStress(unittest.TestCase):
    """Bộ kiểm thử áp lực và chế độ lỗi (Failure Modes) cho open_browser_when_ready."""

    def test_01_server_never_responds_timeout(self):
        """
        Challenge 1.1: Server hoàn toàn không chạy (cổng đóng).
        Kỳ vọng: open_browser_when_ready không crash, thăm dò lặp lại,
        hết timeout thì thoát êm và KHÔNG gọi webbrowser.open, trả về False.
        """
        closed_port = get_ephemeral_port()
        url = f"http://127.0.0.1:{closed_port}"

        with patch("webbrowser.open") as mock_open:
            t0 = time.time()
            result = open_browser_when_ready(url, timeout=0.5, check_interval=0.05)
            elapsed = time.time() - t0

            self.assertFalse(result, "open_browser_when_ready phải trả về False khi server không chạy")
            mock_open.assert_not_called()
            self.assertGreaterEqual(elapsed, 0.45, "Hàm phải đợi đủ thời gian timeout")
            print(f"\n[TEST PASS] Server không phản hồi -> Timeout sau {elapsed:.3f}s, browser KHÔNG bị mở.")

    def test_02_server_returns_500_internal_error(self):
        """
        Challenge 1.2: Server phản hồi HTTP 500 Internal Server Error.
        Kỳ vọng: HTTP 500 không được coi là sẵn sàng. Hàm tiếp tục thăm dò
        cho đến timeout, trả về False, và KHÔNG gọi webbrowser.open.
        """
        port = get_ephemeral_port()
        requests_received = []

        class Error500Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests_received.append(self.path)
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "error", "message": "Internal Error"}')

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", port), Error500Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://127.0.0.1:{port}"
            with patch("webbrowser.open") as mock_open:
                t0 = time.time()
                result = open_browser_when_ready(url, timeout=0.6, check_interval=0.05)
                elapsed = time.time() - t0

                self.assertFalse(result, "open_browser_when_ready không được trả về True khi server trả về 500")
                mock_open.assert_not_called()
                self.assertGreater(len(requests_received), 0, "Server phải nhận được ít nhất 1 probe")
                print(f"[TEST PASS] Server trả về 500 ({len(requests_received)} probes) -> Rejected, browser KHÔNG bị mở.")
        finally:
            server.shutdown()
            server.server_close()

    def test_03_server_returns_503_service_unavailable(self):
        """
        Challenge 1.3: Server phản hồi HTTP 503 Service Unavailable (máy chủ đang khởi động).
        Kỳ vọng: Bị từ chối, không mở trình duyệt, trả về False khi hết timeout.
        """
        port = get_ephemeral_port()
        probes = []

        class Error503Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                probes.append(time.time())
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Service Unavailable")

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", port), Error503Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://127.0.0.1:{port}"
            with patch("webbrowser.open") as mock_open:
                result = open_browser_when_ready(url, timeout=0.5, check_interval=0.05)
                self.assertFalse(result)
                mock_open.assert_not_called()
                self.assertGreater(len(probes), 2)
                print(f"[TEST PASS] Server trả về 503 ({len(probes)} probes) -> Rejected, browser KHÔNG bị mở.")
        finally:
            server.shutdown()
            server.server_close()

    def test_04_server_returns_404_not_found(self):
        """
        Challenge 1.4: Server phản hồi HTTP 404 Not Found (sai route /health).
        Kỳ vọng: Không mở trình duyệt, trả về False.
        """
        port = get_ephemeral_port()

        class Error404Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", port), Error404Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://127.0.0.1:{port}"
            with patch("webbrowser.open") as mock_open:
                result = open_browser_when_ready(url, timeout=0.4, check_interval=0.05)
                self.assertFalse(result)
                mock_open.assert_not_called()
                print(f"[TEST PASS] Server trả về 404 -> Rejected, browser KHÔNG bị mở.")
        finally:
            server.shutdown()
            server.server_close()

    def test_05_delayed_startup_connection_refused_recovery(self):
        """
        Challenge 2.1: Mô phỏng khởi động chậm - Cổng bị từ chối kết nối (Connection Refused)
        trong 0.4 giây đầu, sau đó server mới khởi chạy và trả về HTTP 200.
        Kỳ vọng: open_browser_when_ready vượt qua các lỗi kết nối ban đầu,
        phục hồi sạch sẽ và CHỈ mở trình duyệt sau khi HTTP 200 được xác nhận.
        """
        port = get_ephemeral_port()
        url = f"http://127.0.0.1:{port}"
        server_box = [None]

        def delayed_server_starter():
            time.sleep(0.35)  # Trì hoãn mở socket 350ms
            class DelayedHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "healthy", "ready": true}')

                def log_message(self, format, *args):
                    pass

            srv = HTTPServer(("127.0.0.1", port), DelayedHandler)
            server_box[0] = srv
            srv.serve_forever()

        t_starter = threading.Thread(target=delayed_server_starter, daemon=True)
        t_starter.start()

        try:
            with patch("webbrowser.open") as mock_open:
                t0 = time.time()
                result = open_browser_when_ready(url, timeout=3.0, check_interval=0.05)
                elapsed = time.time() - t0

                self.assertTrue(result, "Phải kết nối thành công sau độ trễ khởi động")
                self.assertGreaterEqual(elapsed, 0.35, "Không thể hoàn thành trước khi server start")
                mock_open.assert_called_once_with(url)
                print(f"[TEST PASS] Phục hồi sau Connection Refused ({elapsed:.3f}s) -> HTTP 200 xác nhận -> Mở trình duyệt đúng 1 lần.")
        finally:
            if server_box[0]:
                server_box[0].shutdown()
                server_box[0].server_close()

    def test_06_delayed_readiness_503_to_200_recovery(self):
        """
        Challenge 2.2: Server phản hồi HTTP 503 trong 4 lượt probe đầu (đang nạp tài nguyên),
        sau đó mới chuyển sang HTTP 200 OK.
        Kỳ vọng: Tuyệt đối không mở trình duyệt trong giai đoạn 503;
        mở trình duyệt đúng 1 lần khi chuyển sang 200.
        """
        port = get_ephemeral_port()
        probe_count = [0]
        opened_timestamps = []

        class WarmupHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                probe_count[0] += 1
                if probe_count[0] <= 4:
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ready": false, "status": "warming_up"}')
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ready": true, "status": "healthy"}')

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", port), WarmupHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://127.0.0.1:{port}"
            with patch("webbrowser.open", side_effect=lambda u: opened_timestamps.append(time.time())) as mock_open:
                result = open_browser_when_ready(url, timeout=3.0, check_interval=0.03)

                self.assertTrue(result)
                self.assertGreaterEqual(probe_count[0], 5, f"Cần ít nhất 5 probe (thực tế: {probe_count[0]})")
                mock_open.assert_called_once_with(url)
                print(f"[TEST PASS] 503 x 4 lượt -> Probe thứ {probe_count[0]} trả về 200 -> Trình duyệt mở sau xác nhận 200.")
        finally:
            server.shutdown()
            server.server_close()

    def test_07_hanging_socket_black_hole_resilience(self):
        """
        Challenge 1.5: Server chấp nhận kết nối TCP nhưng bị treo (Hanging Socket / Black Hole).
        Kỳ vọng: Timeout per-request (0.1s trong urlopen) ngắt kết nối đúng hạn,
        không làm treo vĩnh viễn vòng lặp; tổng hàm kết thúc sau tổng timeout.
        """
        port = get_ephemeral_port()
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.bind(("127.0.0.1", port))
        raw_sock.listen(5)

        hanging_running = [True]

        def black_hole_listener():
            while hanging_running[0]:
                try:
                    conn, _ = raw_sock.accept()
                    time.sleep(1.0)
                    conn.close()
                except Exception:
                    break

        t_blackhole = threading.Thread(target=black_hole_listener, daemon=True)
        t_blackhole.start()

        try:
            url = f"http://127.0.0.1:{port}"
            with patch("webbrowser.open") as mock_open:
                t0 = time.time()
                result = open_browser_when_ready(url, timeout=0.6, check_interval=0.05)
                elapsed = time.time() - t0

                self.assertFalse(result, "Hanging socket không thể trả về True")
                mock_open.assert_not_called()
                self.assertLess(elapsed, 1.5, f"Vòng lặp bị nghẽn quá lâu: {elapsed:.2f}s")
                print(f"[TEST PASS] Hanging socket (Black Hole) -> urllib timeout=0.1 ngắt an toàn sau {elapsed:.3f}s.")
        finally:
            hanging_running[0] = False
            raw_sock.close()

    def test_08_per_request_timeout_boundary_analysis(self):
        """
        Phân tích biên độ nhạy của urllib.request.urlopen(req, timeout=0.1):
        Kiểm tra độ trễ 40ms (<100ms) phản hồi thành công.
        """
        port = get_ephemeral_port()

        class LatencyHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                time.sleep(0.04)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", port), LatencyHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://127.0.0.1:{port}"
            with patch("webbrowser.open") as mock_open:
                result = open_browser_when_ready(url, timeout=2.0, check_interval=0.05)
                self.assertTrue(result)
                mock_open.assert_called_once_with(url)
                print("[TEST PASS] Server phản hồi với latency 40ms (<100ms timeout) -> Nhận diện 200 thành công.")
        finally:
            server.shutdown()
            server.server_close()

    def test_09_concurrency_stress_and_no_connection_refused(self):
        """
        Challenge 2.3: Stress test tính đồng thời.
        15 luồng probe gọi đồng thời vào server thực tế.
        """
        port = get_ephemeral_port()

        class FastHealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "healthy", "ready": true}')

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", port), FastHealthHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://127.0.0.1:{port}"
            results = []
            threads = []

            def probe_worker():
                with patch("webbrowser.open"):
                    res = open_browser_when_ready(url, timeout=2.0, check_interval=0.02)
                    results.append(res)

            for _ in range(15):
                t = threading.Thread(target=probe_worker)
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            self.assertEqual(len(results), 15)
            self.assertTrue(all(results), "Tất cả 15 luồng đồng thời đều phải nhận diện HTTP 200 thành công")
            print(f"[TEST PASS] 15 luồng probe đồng thời đều thành công (100% PASS), không có race condition.")
        finally:
            server.shutdown()
            server.server_close()

    def test_10_simulated_connection_delay_prevents_err_connection_refused(self):
        """
        Challenge 2.4: Định lượng thời điểm mở browser so với thời điểm socket sẵn sàng.
        Xác minh trình duyệt CHỈ mở sau khi socket đã được xác nhận (delta > 0).
        """
        port = get_ephemeral_port()
        server_ready_timestamp = [0.0]
        browser_opened_timestamp = [0.0]
        server_box = [None]

        def delayed_server():
            time.sleep(0.5)
            class ReadyHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                def log_message(self, *args): pass
            srv = HTTPServer(("127.0.0.1", port), ReadyHandler)
            server_box[0] = srv
            server_ready_timestamp[0] = time.time()
            srv.serve_forever()

        t_srv = threading.Thread(target=delayed_server, daemon=True)
        t_srv.start()

        try:
            url = f"http://127.0.0.1:{port}"
            with patch("webbrowser.open", side_effect=lambda u: browser_opened_timestamp.append(time.time())):
                res = open_browser_when_ready(url, timeout=3.0, check_interval=0.03)
                self.assertTrue(res)
                self.assertGreater(len(browser_opened_timestamp), 0)
                delta = browser_opened_timestamp[-1] - server_ready_timestamp[0]
                self.assertGreater(delta, 0.0, "Trình duyệt phải mở SAU khi server socket đã xác nhận 200")
                print(f"[TEST PASS] Trình duyệt mở sau khi socket sẵn sàng {delta*1000:.2f}ms -> Loại trừ 100% ERR_CONNECTION_REFUSED.")
        finally:
            if server_box[0]:
                server_box[0].shutdown()
                server_box[0].server_close()

    def test_11_fastapi_trailing_slash_normalization_remediation(self):
        """
        Verification of Remediation: Kiểm tra xử lý url có dấu gạch chéo cuối 'http://127.0.0.1:port/'.
        Hàm open_browser_when_ready đã được chuẩn hóa với url = url.rstrip('/') để không tạo ra '//health'.
        Xác minh: Probe thành công với HTTP 200, trả về True và mở trình duyệt với URL chuẩn hóa.
        """
        port = get_ephemeral_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        time.sleep(0.4)

        try:
            url_with_slash = f"http://127.0.0.1:{port}/"
            with patch("webbrowser.open") as mock_open:
                res = open_browser_when_ready(url_with_slash, timeout=1.0, check_interval=0.05)
                self.assertTrue(res, "open_browser_when_ready phải xử lý thành công URL có trailing slash")
                mock_open.assert_called_once_with(f"http://127.0.0.1:{port}")
                print("[TEST PASS] Xác minh Remediation: Trailing slash được chuẩn hóa thành công, probe đạt 200 OK.")
        finally:
            server.should_exit = True
            server_thread.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
