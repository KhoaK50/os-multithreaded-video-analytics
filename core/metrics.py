"""
System Resource Monitor for OS Video Analytics Project.
Học phần: Hệ điều hành — Kiến trúc Phân tích Video Đa luồng.

Chức năng:
- Đo đạc phần trăm CPU (% CPU) toàn hệ thống và tiến trình hiện tại qua psutil
- Đo dung lượng và phần trăm bộ nhớ RAM (% RAM, Used/Total GB)
- Đo bộ nhớ card đồ họa rời NVIDIA RTX (VRAM Allocated/Reserved MB qua PyTorch CUDA)
- Tính toán độ trễ xử lý (Latency ms) và FPS thời gian thực
"""

import os
import threading
import time
from typing import Dict, Any
import psutil
import torch



def get_hardware_gpu_name() -> str:
    """
    Nhận diện chính xác thiết bị tính toán phần cứng:
    - NVIDIA CUDA: Tesla T4, RTX 5060, RTX 4090, v.v.
    - Apple Silicon: Apple Silicon (MPS)
    - CPU: CPU
    """
    if torch.cuda.is_available():
        try:
            raw_name = torch.cuda.get_device_name(0)
            upper = raw_name.upper()
            if "T4" in upper:
                return "Tesla T4"
            if "5060" in upper:
                return "RTX 5060"
            if "4090" in upper:
                return "RTX 4090"
            if "3060" in upper:
                return "RTX 3060"
            if "A100" in upper:
                return "Tesla A100"
            if "V100" in upper:
                return "Tesla V100"
            cleaned = raw_name.replace("NVIDIA GeForce ", "").replace("NVIDIA ", "").replace(" Laptop GPU", "").strip()
            return cleaned if len(cleaned) <= 18 else cleaned[:18]
        except Exception:
            return "CUDA GPU"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "Apple Silicon (MPS)"
    return "CPU"


class SystemResourceMonitor:
    """Theo dõi và đo đạc tài nguyên phần cứng theo thời gian thực."""

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.process = psutil.Process(os.getpid())
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._monitor_thread = None

        initial_gpu = get_hardware_gpu_name()
        cuda_avail = torch.cuda.is_available()
        mps_avail = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()

        self.latest_metrics: Dict[str, Any] = {
            "timestamp": time.time(),
            "cpu_total_pct": 0.0,
            "cpu_process_pct": 0.0,
            "cpu_percent": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "ram_percent": 0.0,
            "vram_allocated_mb": 0.0,
            "vram_reserved_mb": 0.0,
            "vram_total_mb": 0.0,
            "gpu_vram_used": 0.0,
            "gpu_vram_total": 0.0,
            "gpu_name": initial_gpu,
            "cuda_available": cuda_avail,
            "mps_available": mps_avail,
        }

    def sample_now(self) -> Dict[str, Any]:
        """Lấy mẫu thông số tài nguyên ngay lập tức."""
        cpu_total = psutil.cpu_percent(interval=None)
        cpu_process = self.process.cpu_percent(interval=None)

        vmem = psutil.virtual_memory()
        ram_used_gb = vmem.used / (1024 ** 3)
        ram_total_gb = vmem.total / (1024 ** 3)
        ram_pct = vmem.percent

        cuda_avail = torch.cuda.is_available()
        mps_avail = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        gpu_name = get_hardware_gpu_name()

        if cuda_avail:
            try:
                vram_allocated = torch.cuda.memory_allocated(0) / (1024 ** 2)
                vram_reserved = torch.cuda.memory_reserved(0) / (1024 ** 2)
                vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
            except Exception:
                vram_allocated, vram_reserved, vram_total = 0.0, 0.0, 0.0
        else:
            vram_allocated, vram_reserved, vram_total = 0.0, 0.0, 0.0

        vram_used_gb = vram_reserved / 1024.0 if vram_reserved > 0 else vram_allocated / 1024.0
        vram_total_gb = vram_total / 1024.0

        metrics = {
            "timestamp": time.time(),
            "cpu_total_pct": round(cpu_total, 1),
            "cpu_process_pct": round(cpu_process, 1),
            "cpu_percent": round(cpu_total, 1),
            "ram_used_gb": round(ram_used_gb, 2),
            "ram_total_gb": round(ram_total_gb, 2),
            "ram_percent": round(ram_pct, 1),
            "vram_allocated_mb": round(vram_allocated, 1),
            "vram_reserved_mb": round(vram_reserved, 1),
            "vram_total_mb": round(vram_total, 1),
            "gpu_vram_used": round(vram_used_gb, 2),
            "gpu_vram_total": round(vram_total_gb, 2),
            "gpu_name": gpu_name,
            "cuda_available": cuda_avail,
            "mps_available": mps_avail,
        }

        with self._lock:
            self.latest_metrics = metrics

        return metrics

    def start_background_monitoring(self):
        """Khởi động luồng chạy nền lấy mẫu định kỳ."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._run_loop,
            name="ResourceMonitorThread",
            daemon=True
        )
        self._monitor_thread.start()

    def _run_loop(self):
        while not self._stop_event.is_set():
            self.sample_now()
            time.sleep(self.interval)

    def stop_monitoring(self):
        """Dừng luồng lấy mẫu tài nguyên."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)

    def get_latest(self) -> Dict[str, Any]:
        """Truy xuất thông số mới nhất mà không gây nghẽn luồng gọi."""
        with self._lock:
            return dict(self.latest_metrics)

    def get_telemetry(self) -> Dict[str, Any]:
        """Truy xuất thông số viễn trắc HĐH chuẩn Interface Contract."""
        return self.get_latest()

