from __future__ import annotations

import argparse
import re
import subprocess
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from . import BenchmarkType
from .base import BenchmarkBase


FPS_PATTERNS = (
    r"Average\s+FPS\s*[:=]\s*([\d.]+)",
    r"Avg\.?\s*FPS\s*[:=]\s*([\d.]+)",
    r"FPS\s*\(avg\)\s*[:=]\s*([\d.]+)",
)
SCORE_PATTERN = re.compile(r"Score\s*[:=]\s*([\d.]+)", flags=re.IGNORECASE)
FPS_FALLBACK_PATTERN = re.compile(r"FPS[^\d]*([\d.]+)", flags=re.IGNORECASE)


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
        command_list = ["furmark", "--demo", self.demo, "--benchmark", "--no-score-box", "--p1080"]

        stdout, duration, returncode = run_command(command_list)
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
