"""
System Resource Monitor for OS Video Analytics Project.
Học phần: Hệ điều hành - GVHD: Thầy Nguyễn Tấn Duẩn

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


class SystemResourceMonitor:
    """Theo dõi và đo đạc tài nguyên phần cứng theo thời gian thực."""

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.process = psutil.Process(os.getpid())
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._monitor_thread = None

        self.latest_metrics: Dict[str, Any] = {
            "timestamp": time.time(),
            "cpu_total_pct": 0.0,
            "cpu_process_pct": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "ram_percent": 0.0,
            "vram_allocated_mb": 0.0,
            "vram_reserved_mb": 0.0,
            "vram_total_mb": 0.0,
            "gpu_name": "None",
            "cuda_available": False,
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
        gpu_name = torch.cuda.get_device_name(0) if cuda_avail else "CPU Only"
        vram_allocated = (torch.cuda.memory_allocated(0) / (1024 ** 2)) if cuda_avail else 0.0
        vram_reserved = (torch.cuda.memory_reserved(0) / (1024 ** 2)) if cuda_avail else 0.0
        vram_total = (torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)) if cuda_avail else 0.0

        metrics = {
            "timestamp": time.time(),
            "cpu_total_pct": round(cpu_total, 1),
            "cpu_process_pct": round(cpu_process, 1),
            "ram_used_gb": round(ram_used_gb, 2),
            "ram_total_gb": round(ram_total_gb, 2),
            "ram_percent": round(ram_pct, 1),
            "vram_allocated_mb": round(vram_allocated, 1),
            "vram_reserved_mb": round(vram_reserved, 1),
            "vram_total_mb": round(vram_total, 1),
            "gpu_name": gpu_name,
            "cuda_available": cuda_avail,
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
