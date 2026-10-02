"""
Unit Tests for ThreadSafeBoundedBuffer and Producer-Consumer Synchronization.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.

Mục tiêu kiểm thử:
1. Xác minh dung lượng giới hạn N (Bounded Buffer Capacity).
2. Kiểm tra cơ chế Flow Control Drop-Oldest (FIFO Eviction) khi quá tải.
3. Kiểm tra tính năng đồng bộ hóa Condition Variable (not_empty, not_full).
4. Kiểm tra độ chính xác của đo đạc Queue Latency và High-Water Mark.
5. Kiểm thử độ bền đa luồng (Concurrent Stress Test) không sinh Race Condition hoặc Deadlock.
6. Xác minh cấu trúc hợp đồng viễn trắc (Telemetry Contract).
"""

import sys
import os
import time
import threading
import unittest
import numpy as np

# Thêm thư mục gốc vào PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.capture import ThreadSafeBoundedBuffer, VideoCaptureProducer


class TestThreadSafeBoundedBuffer(unittest.TestCase):
    def test_bounded_capacity_enforcement(self):
        """Kiểm tra giới hạn dung lượng buffer không vượt quá N."""
        buf = ThreadSafeBoundedBuffer(capacity=5)
        self.assertEqual(buf.capacity, 5)
        self.assertTrue(buf.empty())
        self.assertFalse(buf.full())

        for i in range(5):
            buf.put_drop_oldest((time.time(), f"frame_{i}"))

        self.assertEqual(buf.qsize(), 5)
        self.assertTrue(buf.full())
        self.assertFalse(buf.empty())

    def test_drop_oldest_fifo_eviction(self):
        """Kiểm tra cơ chế Drop-Oldest: Đẩy N+5 phần tử, N phần tử cũ nhất bị loại bỏ."""
        buf = ThreadSafeBoundedBuffer(capacity=4)

        # Đẩy 10 frames (1 đến 10)
        for i in range(1, 11):
            buf.put_drop_oldest((time.time(), f"frame_{i}"))

        stats = buf.get_stats()
        self.assertEqual(stats["size"], 4)
        self.assertEqual(stats["total_produced"], 10)
        self.assertEqual(stats["total_dropped"], 6)
        self.assertEqual(stats["drop_rate_pct"], 60.0)
        self.assertEqual(stats["high_water_mark"], 4)

        # 4 phần tử còn lại trong buffer phải là frame_7, frame_8, frame_9, frame_10
        remaining = []
        while not buf.empty():
            item = buf.get_nowait()
            self.assertIsNotNone(item)
            remaining.append(item[1])

        self.assertEqual(remaining, ["frame_7", "frame_8", "frame_9", "frame_10"])

    def test_condition_variable_signaling(self):
        """Kiểm tra Condition Variable: Consumer chờ và được đánh thức khi Producer nạp dữ liệu."""
        buf = ThreadSafeBoundedBuffer(capacity=8)
        consumed_items = []
        consumer_started = threading.Event()

        def consumer_worker():
            consumer_started.set()
            # Chờ phần tử đầu tiên (blocking get)
            item = buf.get(block=True, timeout=2.0)
            if item is not None:
                consumed_items.append(item[1])

        t_cons = threading.Thread(target=consumer_worker, daemon=True)
        t_cons.start()

        # Đợi consumer bắt đầu chờ
        consumer_started.wait(timeout=1.0)
        time.sleep(0.05)
        self.assertEqual(len(consumed_items), 0)

        # Producer nạp phần tử -> Đánh thức consumer qua not_empty.notify()
        buf.put_drop_oldest((time.time(), "frame_awakened"))
        t_cons.join(timeout=2.0)

        self.assertEqual(consumed_items, ["frame_awakened"])
        self.assertEqual(buf.total_consumed, 1)

    def test_queue_latency_measurement(self):
        """Kiểm tra tính toán độ trễ hàng đợi Queue Latency chính xác."""
        buf = ThreadSafeBoundedBuffer(capacity=10)
        t_put = time.time() - 0.050  # Giả lập frame đã nằm trong buffer 50ms
        buf.put_drop_oldest((t_put, "latency_frame"))

        item = buf.get(block=False)
        self.assertIsNotNone(item)

        stats = buf.get_stats()
        # Latency phải xấp xỉ >= 45ms
        self.assertGreaterEqual(stats["latency_ms"], 40.0)

    def test_concurrent_producer_consumer_stress(self):
        """Stress test: 2 Producer và 2 Consumer chạy đồng thời 1000 items không deadlock/race condition."""
        buf = ThreadSafeBoundedBuffer(capacity=16)
        total_items = 600
        stop_consumers = threading.Event()
        consumed_count = 0
        cons_lock = threading.Lock()

        def producer_worker(start_id, count):
            for i in range(count):
                buf.put_drop_oldest((time.time(), f"item_{start_id}_{i}"))
                time.sleep(0.001)

        def consumer_worker():
            nonlocal consumed_count
            while not stop_consumers.is_set():
                item = buf.get(block=True, timeout=0.05)
                if item is not None:
                    with cons_lock:
                        consumed_count += 1

        t_p1 = threading.Thread(target=producer_worker, args=(1, total_items // 2))
        t_p2 = threading.Thread(target=producer_worker, args=(2, total_items // 2))
        t_c1 = threading.Thread(target=consumer_worker)
        t_c2 = threading.Thread(target=consumer_worker)

        t_c1.start()
        t_c2.start()
        t_p1.start()
        t_p2.start()

        t_p1.join(timeout=5.0)
        t_p2.join(timeout=5.0)
        time.sleep(0.2)
        stop_consumers.set()
        t_c1.join(timeout=2.0)
        t_c2.join(timeout=2.0)

        stats = buf.get_stats()
        self.assertEqual(stats["total_produced"], total_items)
        # Tổng số consumed + số còn trong buffer + số bị dropped phải đúng bằng total_produced
        self.assertEqual(stats["total_consumed"] + stats["size"] + stats["total_dropped"], total_items)
        self.assertGreater(stats["high_water_mark"], 0)
        self.assertLessEqual(stats["high_water_mark"], 16)

    def test_telemetry_stats_contract(self):
        """Xác minh đầy đủ các trường của hợp đồng viễn trắc HĐH."""
        buf = ThreadSafeBoundedBuffer(capacity=16)
        stats = buf.get_stats()

        required_keys = [
            "size", "capacity", "total_produced", "total_consumed",
            "total_dropped", "drop_rate_pct", "latency_ms", "high_water_mark", "utilization_pct"
        ]
        for key in required_keys:
            self.assertIn(key, stats)
            self.assertIsInstance(stats[key], (int, float))


if __name__ == "__main__":
    unittest.main()
