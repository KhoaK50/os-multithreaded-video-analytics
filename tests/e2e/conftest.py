"""
Shared Fixtures, Mocks, and Helpers for E2E Test Suite.
Academic Module: Operating Systems (Hệ Điều Hành)
"""

import os
import sys
import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
from PIL import Image

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEMPLATES_DIR = PROJECT_ROOT / "ui" / "templates"
STATIC_DIR = PROJECT_ROOT / "ui" / "static"

# Forbidden AI Slop & Sci-Fi Terms from ORIGINAL_REQUEST §R2
FORBIDDEN_SLOP_TERMS = [
    "THREAT MATRIX",
    "LOCK-ON",
    "RADAR AI",
    "CYBER HUD",
    "CYBER-SURVEILLANCE HUD",
]

# Required Academic OS Terminology from ORIGINAL_REQUEST §R2
REQUIRED_OS_TERMS = [
    "Producer",
    "Consumer",
    "Bounded Buffer",
    "Flow Control",
]


class MockGeminiResponse:
    """Mock Google GenAI response object."""
    def __init__(self, data: dict):
        self.text = json.dumps(data, ensure_ascii=False)


def make_mock_inference_payload(
    action: str = "Ngồi làm việc tập trung",
    description: str = "Đối tượng ngồi trước máy tính, tư thế chuẩn công thái học.",
    prediction_next_4s: str = "Duy trì thao tác gõ phím ổn định.",
    severity: str = "safe"
) -> dict:
    return {
        "action": action,
        "description": description,
        "prediction_next_4s": prediction_next_4s,
        "severity": severity
    }


def raise_mock_429_error(*args, **kwargs):
    """Simulates Google GenAI SDK raising HTTP 429 RESOURCE_EXHAUSTED."""
    raise Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded (15 requests per minute limit reached).")


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient instance."""
    from fastapi.testclient import TestClient
    from core.web_server import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_bgr_frame() -> np.ndarray:
    """A standard 640x480 BGR synthetic frame."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw simple gradient / shapes to emulate realistic frame
    frame[100:380, 200:440] = [60, 120, 180]
    return frame


@pytest.fixture
def sample_pil_frame() -> Image.Image:
    """A standard 640x480 RGB PIL image."""
    img = Image.new("RGB", (640, 480), color=(40, 50, 65))
    return img


@pytest.fixture
def mock_gemini_client():
    """Returns a mock genai.Client simulating fast offline generation."""
    client_mock = MagicMock()
    payload = make_mock_inference_payload()
    client_mock.models.generate_content.return_value = MockGeminiResponse(payload)
    return client_mock
