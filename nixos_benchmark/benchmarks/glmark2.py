from __future__ import annotations

import argparse
import re
import subprocess
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from . import BenchmarkType
from .base import BenchmarkBase


# Default constants
DEFAULT_GLMARK2_SIZE = "1920x1080"


class GLMark2Benchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.GLMARK2
    description = "glmark2 OpenGL benchmark"
    _required_commands = ("glmark2",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        size = DEFAULT_GLMARK2_SIZE
        offscreen = args.glmark2_mode == "offscreen"
        command = ["glmark2", "-s", size]
        if offscreen:
            command.append("--off-screen")

        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            score_match = re.search(r"glmark2 Score:\s*(\d+)", stdout)
            if not score_match:
                raise ValueError("Unable to parse glmark2 score")

            metrics_data = {"score": float(score_match.group(1))}
            status = "ok"
            metrics = BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data))
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"size": size, "mode": "offscreen" if offscreen else "onscreen"}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        score = result.metrics.get("score")
        if score is not None:
            return f"{score:.0f} pts"
        return ""
