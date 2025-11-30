from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import (
    BenchmarkBase,
    DEFAULT_VKMARK_CMD,
)


class VKMarkBenchmark(BenchmarkBase):
    key = "vkmark"
    categories = ("gpu",)
    presets = ("gpu-light", "gpu", "all")
    description = "vkmark Vulkan benchmark"
    _required_commands = ("vkmark",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command_list = list(DEFAULT_VKMARK_CMD)
        stdout, duration, returncode = run_command(command_list)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command_list, stdout)
        
        try:
            scene_pattern = re.compile(
                r"(?P<scene>[\w-]+).*?(?P<frames>[\d.]+)\s+frames\s+in\s+[\d.]+\s+seconds\s*="
                r"\s*(?P<fps>[\d.]+)\s*FPS",
                flags=re.IGNORECASE,
            )
            fps_values = [float(match.group("fps")) for match in scene_pattern.finditer(stdout)]
            if not fps_values:
                fps_values = [
                    float(match)
                    for match in re.findall(r"FPS[:=]\s*([\d.]+)", stdout, flags=re.IGNORECASE)
                ]
            if not fps_values:
                raise ValueError("Unable to parse vkmark FPS results")
            
            metrics_data = {
                "fps_avg": sum(fps_values) / len(fps_values),
                "fps_min": min(fps_values),
                "fps_max": max(fps_values),
                "samples": len(fps_values),
            }
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="vkmark",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command=" ".join(command_list),
            raw_output=stdout,
            message=message,
        )
    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"
        
        fps = result.metrics.get("fps_avg") or result.metrics.get("fps_max")
        if fps is not None:
            return f"{fps:.1f} fps"
        return ""
