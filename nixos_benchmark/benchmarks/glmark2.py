from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import (
    BenchmarkBase,
    DEFAULT_GLMARK2_SIZE,
)


class GLMark2Benchmark(BenchmarkBase):
    key = "glmark2"
    categories = ("gpu",)
    presets = ("gpu-light", "gpu", "all")
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
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="glmark2",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({
                "size": size,
                "mode": "offscreen" if offscreen else "onscreen"
            }),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )
    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"
        
        score = result.metrics.get("score")
        if score is not None:
            return f"{score:.0f} pts"
        return ""
