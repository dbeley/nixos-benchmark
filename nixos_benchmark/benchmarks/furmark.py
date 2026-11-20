from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


FPS_PATTERNS = (
    r"Average\s+FPS\s*[:=]\s*([\d.]+)",
    r"Avg\.?\s*FPS\s*[:=]\s*([\d.]+)",
    r"FPS\s*\(avg\)\s*[:=]\s*([\d.]+)",
)
SCORE_PATTERN = re.compile(r"Score\s*[:=]\s*([\d.]+)", flags=re.IGNORECASE)
FPS_FALLBACK_PATTERN = re.compile(r"FPS[^\d]*([\d.]+)", flags=re.IGNORECASE)

# FurMark records "demo X is already running" in a SysV shared memory segment
# keyed by this value. A crashed or killed run leaves it behind, and every later
# run then aborts with "In benchmark mode, only one instance is allowed."
# Only that exact key is removed: /dev/shm holds other programs' segments too.
FURMARK_SHM_KEY = "0x0000023e"


def _cleanup_stale_shm() -> None:
    """Remove leftover FurMark shared-memory state from a crashed/killed run."""
    ipcrm = shutil.which("ipcrm")
    if ipcrm:
        subprocess.run([ipcrm, "-M", FURMARK_SHM_KEY], capture_output=True, check=False)


def _ensure_x_resources() -> bool:
    """Ensure the X root window has a RESOURCE_MANAGER property.

    FurMark 2.10.2 segfaults (SIGSEGV) in X11_GetMonitorDPI when the property
    is absent: it passes a NULL string to XrmGetStringDatabase. Creating an
    empty property sidesteps the crash.

    Returns True when this call created the property, so the caller can remove
    it again instead of leaving the change in the user's session.
    """
    if not os.environ.get("DISPLAY"):
        return False
    xprop = shutil.which("xprop")
    if not xprop:
        return False
    check = subprocess.run([xprop, "-root", "RESOURCE_MANAGER"], capture_output=True, text=True, check=False)
    if "not found" not in check.stdout:
        return False
    subprocess.run(
        [xprop, "-root", "-f", "RESOURCE_MANAGER", "8s", "-set", "RESOURCE_MANAGER", ""],
        capture_output=True,
        check=False,
    )
    return True


def _remove_x_resources() -> None:
    """Remove the RESOURCE_MANAGER placeholder so the session is left as found."""
    xprop = shutil.which("xprop")
    if xprop:
        subprocess.run([xprop, "-root", "-remove", "RESOURCE_MANAGER"], capture_output=True, check=False)


class FurmarkBenchmark(BenchmarkBase):
    _required_commands = ("furmark",)
    version_command = ("furmark", "-v")

    def __init__(self, demo: str, benchmark_type: BenchmarkType, description: str):
        self.demo = demo
        self.benchmark_type = benchmark_type
        self.description = description

    def _parse_metrics(self, output: str) -> dict[str, float | int]:
        metrics: dict[str, float | int] = {}

        for pattern in FPS_PATTERNS:
            match = re.search(pattern, output, flags=re.IGNORECASE)
            if match:
                metrics["fps_avg"] = float(match.group(1))
                break

        min_match = re.search(r"Min(?:imum)?\s+FPS\s*[:=]\s*([\d.]+)", output, flags=re.IGNORECASE)
        if min_match:
            metrics["fps_min"] = float(min_match.group(1))

        max_match = re.search(r"Max(?:imum)?\s+FPS\s*[:=]\s*([\d.]+)", output, flags=re.IGNORECASE)
        if max_match:
            metrics["fps_max"] = float(max_match.group(1))

        score_match = SCORE_PATTERN.search(output)
        if score_match:
            metrics["score"] = float(score_match.group(1))

        if "fps_avg" not in metrics:
            fps_values = [float(match) for match in FPS_FALLBACK_PATTERN.findall(output)]
            if fps_values:
                metrics["fps_avg"] = fps_values[-1]

        if not metrics:
            raise ValueError("Unable to parse furmark output for FPS/score")

        return metrics

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        _cleanup_stale_shm()
        created_property = _ensure_x_resources()

        command_list = ["furmark", "--demo", self.demo, "--benchmark", "--no-score-box", "--p1080"]

        try:
            stdout, duration, returncode = run_command(command_list, timeout=300)
        finally:
            if created_property:
                _remove_x_resources()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command_list, stdout)

        metrics_data = self._parse_metrics(stdout)
        metrics = BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data))

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status="ok",
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"demo": self.demo, "profile": "p1080"}),
            duration_seconds=duration,
            command=self.format_command(command_list),
            raw_output=stdout,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        fps = result.metrics.get("fps_avg")
        score = result.metrics.get("score")
        if fps is not None and score is not None:
            return f"{fps:.1f} fps (score {score:.0f})"
        if fps is not None:
            return f"{float(fps):.1f} fps"
        if score is not None:
            return f"score {float(score):.0f}"
        return ""
