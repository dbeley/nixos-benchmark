from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import (
    BenchmarkBase,
    DEFAULT_IOPING_COUNT,
)


class IOPingBenchmark(BenchmarkBase):
    key = "ioping"
    categories = ("io",)
    presets = ("io", "all")
    description = "ioping latency probe"
    _required_commands = ("ioping",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        count = DEFAULT_IOPING_COUNT
        command = ["ioping", "-c", str(count), "."]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            match = re.search(
                r"min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", stdout
            )
            if not match:
                raise ValueError("Unable to parse ioping summary")
            
            metrics_data = {
                "latency_min_ms": float(match.group(1)),
                "latency_avg_ms": float(match.group(2)),
                "latency_max_ms": float(match.group(3)),
                "latency_mdev_ms": float(match.group(4)),
                "requests": count,
            }
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="ioping",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"count": count}),
            duration_seconds=duration,
            command=f"ioping -c {count} .",
            raw_output=stdout,
            message=message,
        )


    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"
        
        latency = result.metrics.get("latency_avg_ms")
        if latency is not None:
            return f"{latency:.2f} ms avg"
        return ""
