from __future__ import annotations

import argparse
import re
import subprocess
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_IOPING_COUNT = 20  # Increased from 5 for better statistics, not too slow


class IOPingBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.IOPING
    description = "ioping latency probe"
    _required_commands = ("ioping",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        count = DEFAULT_IOPING_COUNT
        command = ["ioping", "-c", str(count), "."]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            pattern = (
                r"min/avg/max/mdev = ([\d.]+)\s*(\w+)\s*/\s*([\d.]+)\s*(\w+)\s*/"
                r"\s*([\d.]+)\s*(\w+)\s*/\s*([\d.]+)\s*(\w+)"
            )
            match = re.search(pattern, stdout)
            if not match:
                raise ValueError("Unable to parse ioping summary")

            def to_ms(value: str, unit: str) -> float:
                unit_lower = unit.lower()
                if unit_lower.startswith("us"):
                    return float(value) / 1000.0
                if unit_lower.startswith("ms"):
                    return float(value)
                if unit_lower.startswith("s"):
                    return float(value) * 1000.0
                raise ValueError(f"Unknown latency unit: {unit}")

            metrics_data = {
                "latency_min_ms": to_ms(match.group(1), match.group(2)),
                "latency_avg_ms": to_ms(match.group(3), match.group(4)),
                "latency_max_ms": to_ms(match.group(5), match.group(6)),
                "latency_mdev_ms": to_ms(match.group(7), match.group(8)),
                "requests": count,
            }
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
            parameters=BenchmarkParameters({"count": count}),
            duration_seconds=duration,
            command=f"ioping -c {count} .",
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        latency = result.metrics.get("latency_avg_ms")
        if latency is not None:
            return f"{latency:.2f} ms avg"
        return ""
