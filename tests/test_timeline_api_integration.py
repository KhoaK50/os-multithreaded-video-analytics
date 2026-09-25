import os
import time
import unittest
from fastapi.testclient import TestClient
from core.web_server import app

class TestVideoAnalyticsAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.sample_video = "demo_synthetic.mp4"

    def test_video_process_pipeline_e2e(self):
        if not os.path.exists(self.sample_video):
            self.skipTest(f"{self.sample_video} not found")

        # 1. Start processing job
        res = self.client.post("/api/video/process", json={
            "video_path": os.path.abspath(self.sample_video),
            "start_time": 0.0,
            "end_time": 4.0,
            "call_gemini": False
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("job_id", data)
        job_id = data["job_id"]

        # 2. Poll until completed (max 20 seconds)
        completed = False
        result = None
        for _ in range(40):
            time.sleep(0.5)
            poll_res = self.client.get(f"/api/video/job/{job_id}")
            self.assertEqual(poll_res.status_code, 200)
            job = poll_res.json()
            if job["status"] == "completed":
                completed = True
                result = job["result"]
                break
            elif job["status"] == "error":
                self.fail(f"Job failed with error: {job.get('error')}")

        self.assertTrue(completed, "Job did not complete within timeout")
        self.assertIsNotNone(result)

        # 3. Check result schema
        self.assertIn("timeline_segments", result)
        self.assertIn("heatmap_data", result)
        self.assertIn("entities_detected", result)
        self.assertIn("annotated_stream_url", result)
        self.assertIn("download_url", result)

        print("\n[E2E SUCCESS] Timeline Segments Count:", len(result["timeline_segments"]))
        print("[E2E SUCCESS] Heatmap Slots Count:", len(result["heatmap_data"]))
        print("[E2E SUCCESS] Detected Entities:", result["entities_detected"])

if __name__ == "__main__":
    unittest.main()
