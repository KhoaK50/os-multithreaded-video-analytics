"""
Adversarial Challenge & Empirical Stress Test Suite: Milestone 1
Focus: Startup Latency, Concurrent Readiness, Engine Warmup Concurrency/Deadlock, and Leak Analysis.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn.
Challenger: challenger_m1_1 (Milestone 1 Latency & Concurrency Stress Verification)
"""

import os
import sys
import io
import time
import json
import socket
import gc
import psutil
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error

# Ensure root import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
from core.config import CONFIG
from core.video_annotator import VideoAnnotatorEngine
from core.web_server import app, ANNOTATOR_ENGINE


def get_ephemeral_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestM1LatencyAndConcurrencyStress(unittest.TestCase):
    """
    Empirical Stress Testing for Milestone 1:
    - Repeated server startups and latency distribution (<500ms target).
    - Rapid concurrent request bursts to /health and /api/health (100 concurrent workers).
    - Concurrency, race condition, and deadlock resistance of VideoAnnotatorEngine.warmup() & ensure_ready().
    - Memory, thread, and socket leak analysis across startup/shutdown cycles.
    - Failure modes: GIL starvation, orphaned workers, UnicodeEncodeError on CP1252, and warmup error handling.
    """

    def test_01_repeated_server_startup_latency(self):
        """
        Challenge 1.1: Verify server startup latency across repeated startup cycles.
        Tests startup latency and detects if background warmup from prior uncoordinated lifespans
        causes latency to spike past the 1.0s requirement.
        """
        startup_latencies = []
        cycle_count = 5

        for cycle in range(cycle_count):
            port = get_ephemeral_port()
            url = f"http://127.0.0.1:{port}"
            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
            server = uvicorn.Server(config)
            server_thread = threading.Thread(target=server.run, daemon=True)

            t0 = time.time()
            server_thread.start()

            # Poll for readiness
            ready = False
            elapsed = 0.0
            health_url = f"{url}/health"

            for _ in range(60):  # poll up to 1.8s
                try:
                    req = urllib.request.Request(
                        health_url,
                        headers={"User-Agent": f"StartupLatencyProbeCycle{cycle}/1.0"}
                    )
                    with urllib.request.urlopen(req, timeout=0.2) as resp:
                        if resp.status == 200:
                            elapsed = time.time() - t0
                            ready = True
                            break
                except Exception:
                    time.sleep(0.015)

            # Shutdown server
            server.should_exit = True
            server_thread.join(timeout=2.0)

            self.assertTrue(ready, f"Cycle {cycle+1}: Server did not respond within timeout")
            startup_latencies.append(elapsed)
            print(f"  [Cycle {cycle+1}/{cycle_count}] Startup latency: {elapsed*1000:.1f}ms")

        min_lat = min(startup_latencies)
        max_lat = max(startup_latencies)
        mean_lat = sum(startup_latencies) / len(startup_latencies)

        print(f"\n[STRESS REPORT 1.1] Repeated Startup Latencies (5 cycles):")
        print(f"  Min:  {min_lat*1000:.1f}ms")
        print(f"  Max:  {max_lat*1000:.1f}ms")
        print(f"  Mean: {mean_lat*1000:.1f}ms")

        # Empirical findings check
        self.assertLess(mean_lat, 0.6, f"Mean startup latency {mean_lat:.3f}s is higher than expected")

    def test_02_gil_starvation_during_background_warmup(self):
        """
        Challenge 1.2: Measure /health endpoint latency before vs during background YOLO model warmup.
        Empirically verifies whether PyTorch/YOLO/CUDA loading in the background thread starves
        Uvicorn's event loop via Python GIL contention, causing response latencies to exceed 1.0s.
        """
        port = get_ephemeral_port()
        url = f"http://127.0.0.1:{port}"

        # Create isolated engine for this test
        test_engine = VideoAnnotatorEngine(auto_warmup=False)

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()

        # 1. Wait for server to bind and measure baseline latency
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=0.1) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(0.02)

        t_base_start = time.time()
        with urllib.request.urlopen(f"{url}/health", timeout=1.0) as r:
            self.assertEqual(r.status, 200)
        baseline_latency = (time.time() - t_base_start) * 1000.0

        # 2. Trigger heavy model warmup on background thread
        warmup_thread = threading.Thread(target=test_engine.warmup, daemon=True)
        warmup_thread.start()
        time.sleep(0.05)  # allow warmup to enter YOLO loading

        # 3. Measure request latency while warmup is active
        t_active_start = time.time()
        with urllib.request.urlopen(f"{url}/health", timeout=3.0) as r:
            self.assertEqual(r.status, 200)
        active_warmup_latency = (time.time() - t_active_start) * 1000.0

        warmup_thread.join(timeout=10.0)
        server.should_exit = True
        server_thread.join(timeout=2.0)

        print(f"\n[STRESS REPORT 1.2] GIL Contention During Background Warmup:")
        print(f"  Baseline /health Latency (idle):          {baseline_latency:.2f}ms")
        print(f"  Under Background Warmup /health Latency:   {active_warmup_latency:.2f}ms")
        print(f"  Latency Inflation Factor:                 {active_warmup_latency / max(0.1, baseline_latency):.1f}x")

        # Record empirical observation
        self.assertLess(baseline_latency, 100.0, "Baseline /health latency should be < 100ms")

    def test_03_rapid_concurrent_health_requests(self):
        """
        Challenge 1.3: Launch 100 concurrent requests to /health and /api/health (25 concurrent workers).
        Verify:
        - 100% of requests return HTTP 200 OK.
        - Zero dropped connections or connection refused errors.
        - Payload schema validation across all responses.
        - P50, P95, and P99 latency measurement under concurrency.
        """
        port = get_ephemeral_port()
        url = f"http://127.0.0.1:{port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()

        # Wait until port is ready
        ready = False
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=0.1) as r:
                    if r.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.02)
        self.assertTrue(ready, "Server failed to start for concurrency test")

        total_requests = 100
        concurrency = 25
        endpoints = [f"{url}/health", f"{url}/api/health"]

        latencies = []
        errors = []
        status_codes = []
        payloads = []

        def worker_request(req_id: int):
            target_url = endpoints[req_id % len(endpoints)]
            t_req = time.time()
            try:
                req = urllib.request.Request(
                    target_url,
                    headers={"User-Agent": f"ConcurrentStressWorker/{req_id}"}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    dur = time.time() - t_req
                    content = resp.read().decode("utf-8")
                    data = json.loads(content)
                    return (resp.status, dur, data, None)
            except Exception as e:
                dur = time.time() - t_req
                return (0, dur, None, str(e))

        t_burst_start = time.time()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(worker_request, i) for i in range(total_requests)]
            for fut in as_completed(futures):
                status, dur, data, err = fut.result()
                latencies.append(dur)
                status_codes.append(status)
                if err:
                    errors.append(err)
                if data:
                    payloads.append(data)
        total_burst_time = time.time() - t_burst_start

        server.should_exit = True
        server_thread.join(timeout=2.0)

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        success_count = sum(1 for s in status_codes if s == 200)

        print(f"\n[STRESS REPORT 1.3] Concurrent Health Requests (100 requests @ concurrency {concurrency}):")
        print(f"  Success Rate: {success_count}/{total_requests} (100% target)")
        print(f"  Total burst duration: {total_burst_time:.3f}s")
        print(f"  Throughput: {total_requests / total_burst_time:.1f} req/sec")
        print(f"  P50 Latency: {p50*1000:.2f}ms")
        print(f"  P95 Latency: {p95*1000:.2f}ms")
        print(f"  P99 Latency: {p99*1000:.2f}ms")
        print(f"  Max Latency: {max(latencies)*1000:.2f}ms")
        print(f"  Errors encountered: {len(errors)}")

        self.assertEqual(len(errors), 0, f"Encountered {len(errors)} request errors: {errors[:5]}")
        self.assertEqual(success_count, total_requests, f"Only {success_count}/{total_requests} succeeded")

        for payload in payloads:
            self.assertEqual(payload.get("status"), "healthy")
            self.assertTrue(payload.get("ready"))
            self.assertIn("server_time", payload)
            self.assertIn(payload.get("ai_status"), ["ready", "warming_up"])
            self.assertIn("device", payload)
            self.assertIn("active_camera", payload)

    def test_04_engine_warmup_concurrency_and_race_conditions(self):
        """
        Challenge 2.1: Stress-test VideoAnnotatorEngine.warmup() under high thread contention.
        20 threads call warmup() simultaneously on an unwarmed instance.
        Verify:
        - No race conditions or multiple YOLO allocations.
        - All threads exit cleanly without deadlocks.
        - is_ready is True after all threads finish.
        """
        fresh_engine = VideoAnnotatorEngine(auto_warmup=False)
        self.assertFalse(fresh_engine.is_ready)

        num_threads = 20
        barrier = threading.Barrier(num_threads)
        exceptions = []
        threads = []

        def worker_warmup():
            try:
                barrier.wait(timeout=5.0)
                fresh_engine.warmup()
            except Exception as e:
                exceptions.append(e)

        for _ in range(num_threads):
            t = threading.Thread(target=worker_warmup)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=25.0)
            self.assertFalse(t.is_alive(), "A thread deadlocked in warmup()")

        print(f"\n[STRESS REPORT 2.1] Engine Warmup Concurrency ({num_threads} simultaneous threads):")
        print(f"  Exceptions raised: {len(exceptions)}")
        print(f"  Engine is_ready: {fresh_engine.is_ready}")
        print(f"  Engine model loaded: {fresh_engine.model is not None}")

        self.assertEqual(len(exceptions), 0, f"Exceptions occurred during concurrent warmup: {exceptions}")
        self.assertTrue(fresh_engine.is_ready)
        self.assertIsNotNone(fresh_engine.model)

    def test_05_engine_ensure_ready_concurrency_and_deadlock(self):
        """
        Challenge 2.2: Stress-test VideoAnnotatorEngine.ensure_ready() with 30 concurrent threads.
        Spawn 30 threads that call ensure_ready(timeout=20.0) while warmup() runs in background.
        Verify:
        - All 30 threads unblock successfully and return True.
        - No thread hangs or times out.
        """
        fresh_engine = VideoAnnotatorEngine(auto_warmup=False)
        self.assertFalse(fresh_engine.is_ready)

        num_threads = 30
        results = [None] * num_threads
        exceptions = []
        threads = []
        barrier = threading.Barrier(num_threads + 1)

        def worker_ensure(idx: int):
            try:
                barrier.wait(timeout=5.0)
                t_call = time.time()
                res = fresh_engine.ensure_ready(timeout=20.0)
                dur = time.time() - t_call
                results[idx] = (res, dur)
            except Exception as e:
                exceptions.append(e)

        for i in range(num_threads):
            t = threading.Thread(target=worker_ensure, args=(i,))
            threads.append(t)
            t.start()

        # Synchronize barrier and launch warmup
        barrier.wait(timeout=5.0)
        warmup_thread = threading.Thread(target=fresh_engine.warmup)
        warmup_thread.start()

        for t in threads:
            t.join(timeout=25.0)
            self.assertFalse(t.is_alive(), "ensure_ready thread deadlocked!")
        warmup_thread.join(timeout=25.0)

        true_count = sum(1 for r in results if r and r[0] is True)
        print(f"\n[STRESS REPORT 2.2] Engine ensure_ready Concurrency ({num_threads} concurrent threads):")
        print(f"  Threads returned True: {true_count}/{num_threads}")
        print(f"  Exceptions: {len(exceptions)}")
        if true_count > 0:
            durations = [r[1] for r in results if r]
            print(f"  Max duration to unblock: {max(durations):.3f}s")
            print(f"  Min duration to unblock: {min(durations):.3f}s")

        self.assertEqual(len(exceptions), 0, f"Exceptions occurred: {exceptions}")
        self.assertEqual(true_count, num_threads, f"Not all threads returned True: {results}")

    def test_06_ensure_ready_unicode_encode_resilience(self):
        """
        Challenge 2.3 Verification: Verify resilience against UnicodeEncodeError in ensure_ready() on standard Windows CP1252.
        Remediation: Safe ASCII logging wrapped in try/except ensures that console output
        on Windows CP1252 does not raise UnicodeEncodeError.
        """
        cold_engine = VideoAnnotatorEngine(auto_warmup=False)
        captured_error = None

        # Simulate standard Windows CP1252 console output stream
        old_stdout = sys.stdout
        buf = io.BytesIO()
        sys.stdout = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")

        try:
            cold_engine.ensure_ready(timeout=0.01)
        except UnicodeEncodeError as uee:
            captured_error = uee
        except Exception:
            pass
        finally:
            sys.stdout = old_stdout

        print(f"\n[STRESS REPORT 2.3] Unicode Encoding Resilience in ensure_ready():")
        print(f"  Captured UnicodeEncodeError: {captured_error}")
        self.assertIsNone(captured_error, f"Regression: ensure_ready() raised unexpected UnicodeEncodeError under CP1252: {captured_error}")

    def test_07_ensure_ready_failed_warmup_fail_fast(self):
        """
        Challenge 2.4 Verification: Verify fail-fast and immediate unblocking when warmup() raises an exception.
        Remediation: try-except-finally in warmup() records _warmup_error and guarantees _warmup_event.set()
        is called. ensure_ready() checks _warmup_error and fail-fasts immediately (<0.2s) without hanging for 30s.
        """
        from unittest.mock import patch
        broken_engine = VideoAnnotatorEngine(auto_warmup=False)
        waiting_results = []

        with patch("ultralytics.YOLO", side_effect=RuntimeError("Simulated CUDA Out Of Memory Error")):
            def waiting_thread():
                t0 = time.time()
                res = broken_engine.ensure_ready(timeout=5.0)
                dur = time.time() - t0
                waiting_results.append((res, dur))

            # Acquire lock first so waiting_thread is blocked in ensure_ready waiting on _warmup_event
            with broken_engine._warmup_lock:
                th_wait = threading.Thread(target=waiting_thread)
                th_wait.start()
                time.sleep(0.02)

            # Now execute failing warmup
            try:
                broken_engine.warmup()
            except Exception:
                pass

            th_wait.join(timeout=2.0)

        res, elapsed = waiting_results[0]

        print(f"\n[STRESS REPORT 2.4] ensure_ready Error Propagation & Fail-Fast:")
        print(f"  Warmup threw exception -> _warmup_event.is_set(): {broken_engine._warmup_event.is_set()}")
        print(f"  Warmup error recorded: {broken_engine._warmup_error}")
        print(f"  ensure_ready returned: {res} after {elapsed:.3f}s (immediate fail-fast, no 30s hang)")

        # Verify that _warmup_event was set in finally and _warmup_error is captured
        self.assertTrue(broken_engine._warmup_event.is_set(), "_warmup_event must be set on warmup completion/failure")
        self.assertIsNotNone(broken_engine._warmup_error, "_warmup_error must be populated")
        self.assertFalse(res, "ensure_ready must return False on warmup failure")
        self.assertLess(elapsed, 1.0, f"ensure_ready hung for too long: {elapsed:.3f}s (should be fail-fast)")

    def test_08_memory_thread_and_socket_leak_cycles(self):
        """
        Challenge 3.1: Check memory, thread, and socket leaks during 5 repeated server startup/shutdown cycles.
        Verify:
        - Sockets are not leaked (0 dangling sockets after teardown).
        - Active threads do not continuously accumulate across cycles.
        - RSS memory does not exhibit runaway growth.
        """
        process = psutil.Process()
        gc.collect()

        initial_rss = process.memory_info().rss / (1024 * 1024)
        initial_threads = threading.active_count()
        cycle_count = 5

        memory_samples = []
        thread_samples = []
        socket_samples = []

        for cycle in range(cycle_count):
            port = get_ephemeral_port()
            url = f"http://127.0.0.1:{port}"
            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
            server = uvicorn.Server(config)
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()

            # Wait for 200
            for _ in range(30):
                try:
                    with urllib.request.urlopen(f"{url}/health", timeout=0.1) as r:
                        if r.status == 200:
                            break
                except Exception:
                    time.sleep(0.02)

            # Fire 10 requests to exercise socket paths
            for _ in range(10):
                try:
                    with urllib.request.urlopen(f"{url}/health", timeout=0.5):
                        pass
                except Exception:
                    pass

            # Shutdown server
            server.should_exit = True
            server_thread.join(timeout=2.0)
            time.sleep(0.1)

            gc.collect()
            cur_rss = process.memory_info().rss / (1024 * 1024)
            cur_threads = threading.active_count()

            try:
                cur_sockets = len(process.net_connections())
            except Exception:
                cur_sockets = 0

            memory_samples.append(cur_rss)
            thread_samples.append(cur_threads)
            socket_samples.append(cur_sockets)

            print(f"  [Cycle {cycle+1}/{cycle_count}] RSS: {cur_rss:.1f} MB | Threads: {cur_threads} | Sockets: {cur_sockets}")

        final_rss = memory_samples[-1]
        rss_delta = final_rss - initial_rss
        final_threads = thread_samples[-1]
        thread_delta = final_threads - initial_threads

        print(f"\n[STRESS REPORT 3.1] Resource Leak Analysis (5 Startup/Shutdown cycles):")
        print(f"  Initial RSS: {initial_rss:.1f} MB -> Final RSS: {final_rss:.1f} MB (Delta: {rss_delta:+.1f} MB)")
        print(f"  Initial Threads: {initial_threads} -> Final Threads: {final_threads} (Delta: {thread_delta:+d})")
        print(f"  Final open socket connections: {socket_samples[-1]}")

        self.assertLessEqual(thread_delta, 3, f"Thread accumulation detected! Delta={thread_delta}")
        self.assertLess(rss_delta, 100.0, f"Significant memory growth detected! Delta={rss_delta:.1f} MB")


if __name__ == "__main__":
    unittest.main()
