import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from core.web_server import app
from core.video_annotator import probe_web_video

class TestURLProbeAndSlice(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("core.video_annotator.yt_dlp.YoutubeDL")
    def test_probe_web_video_direct_function(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "title": "Sample 1-hour Security Surveillance Footage",
            "duration": 3600,
            "thumbnail": "https://example.com/thumb.jpg"
        }
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        res = probe_web_video("https://www.youtube.com/watch?v=sample123")
        self.assertEqual(res["title"], "Sample 1-hour Security Surveillance Footage")
        self.assertEqual(res["duration"], 3600)
        self.assertTrue(res["is_long"])
        self.assertEqual(res["duration_str"], "60:00")

    @patch("core.video_annotator.yt_dlp.YoutubeDL")
    def test_probe_url_api_endpoint(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "title": "Short 60s Clip",
            "duration": 60,
            "thumbnail": "https://example.com/short.jpg"
        }
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        response = self.client.post("/api/video/probe_url", json={"url": "https://www.youtube.com/watch?v=short"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["duration"], 60)
        self.assertFalse(data["is_long"])

    @patch("core.video_annotator.yt_dlp.YoutubeDL")
    def test_probe_url_error_handling(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = Exception("Video unavailable. Copyright strike.")
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl

        # Calling function directly raises RuntimeError with Vietnamese guidance
        with self.assertRaises(RuntimeError) as ctx:
            probe_web_video("https://www.youtube.com/watch?v=blocked")
        self.assertIn("bản quyền", str(ctx.exception))

        # API endpoint catches it and returns 400 with detail
        response = self.client.post("/api/video/probe_url", json={"url": "https://www.youtube.com/watch?v=blocked"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("bản quyền", response.json()["detail"])

if __name__ == "__main__":
    unittest.main()
