from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mss import mss
from PIL import Image


@dataclass
class CaptureResult:
    path: Path
    bounds: dict[str, int]


class ScreenCapture:
    def __init__(self) -> None:
        self._mss = None

    def capture_monitor(self, monitor_index: int, dest: Path) -> CaptureResult:
        with mss() as sct:
            monitors = sct.monitors
            monitor = monitors[min(monitor_index, len(monitors) - 1)]
            image = sct.grab(monitor)
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.frombytes("RGB", image.size, image.rgb).save(dest)
        bounds = {
            "left": monitor["left"],
            "top": monitor["top"],
            "width": monitor["width"],
            "height": monitor["height"],
        }
        return CaptureResult(dest, bounds)

    def capture_roi(self, roi: dict[str, int], dest: Path) -> CaptureResult:
        with mss() as sct:
            image = sct.grab(roi)
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.frombytes("RGB", image.size, image.rgb).save(dest)
        return CaptureResult(dest, roi)

    def capture_active_window(self, dest: Path) -> CaptureResult:
        with mss() as sct:
            monitor = sct.monitors[0]
            image = sct.grab(monitor)
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.frombytes("RGB", image.size, image.rgb).save(dest)
        bounds = {
            "left": monitor["left"],
            "top": monitor["top"],
            "width": monitor["width"],
            "height": monitor["height"],
        }
        return CaptureResult(dest, bounds)

    @staticmethod
    def build_capture_path(captures_dir: Path, prefix: str) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return captures_dir / f"{prefix}_{timestamp}.png"

    @staticmethod
    def diff_ratio(before: Path, after: Path) -> float:
        before_image = Image.open(before).convert("RGB")
        after_image = Image.open(after).convert("RGB")
        if before_image.size != after_image.size:
            after_image = after_image.resize(before_image.size)
        diff = 0
        pixels = 0
        for before_pixel, after_pixel in zip(before_image.getdata(), after_image.getdata()):
            pixels += 1
            diff += sum(abs(b - a) for b, a in zip(before_pixel, after_pixel))
        max_diff = pixels * 3 * 255
        return diff / max_diff if max_diff else 0.0

    def describe_available_monitors(self) -> list[dict[str, Any]]:
        monitors = []
        with mss() as sct:
            for idx, monitor in enumerate(sct.monitors):
                monitors.append(
                    {
                        "index": idx,
                        "left": monitor["left"],
                        "top": monitor["top"],
                        "width": monitor["width"],
                        "height": monitor["height"],
                    }
                )
        return monitors
