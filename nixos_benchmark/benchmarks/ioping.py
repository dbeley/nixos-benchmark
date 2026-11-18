"""ioping latency probe benchmark."""

from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_IOPING_COUNT = 20  # Increased from 5 for better statistics, not too slow


class IOPingBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.IOPING
    description = "ioping latency probe"
    _required_commands = ("ioping",)

    @staticmethod
    def _to_ms(value: str, unit: str) -> float:
        unit_lower = unit.lower()
        if unit_lower.startswith("us"):
            return float(value) / 1000.0
        if unit_lower.startswith("ms"):
            return float(value)
        if unit_lower.startswith("s"):
            return float(value) * 1000.0
        raise ValueError(f"Unknown latency unit: {unit}")

    @staticmethod
    def _parse_ioping(stdout: str) -> dict[str, float | str | int]:
        pattern = (
            r"min/avg/max/mdev = ([\d.]+)\s*(\w+)\s*/\s*([\d.]+)\s*(\w+)\s*/"
            r"\s*([\d.]+)\s*(\w+)\s*/\s*([\d.]+)\s*(\w+)"
        )
        match = re.search(pattern, stdout)
        if not match:
            raise ValueError("Unable to parse ioping summary")

        return {
            "latency_min_ms": IOPingBenchmark._to_ms(match.group(1), match.group(2)),
            "latency_avg_ms": IOPingBenchmark._to_ms(match.group(3), match.group(4)),
            "latency_max_ms": IOPingBenchmark._to_ms(match.group(5), match.group(6)),
            "latency_mdev_ms": IOPingBenchmark._to_ms(match.group(7), match.group(8)),
        }

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        count = DEFAULT_IOPING_COUNT
        command = ["ioping", "-c", str(count), "."]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        status, metrics, message = self.parse_metrics(lambda: self._parse_ioping(stdout))
        if status == "ok":
            metrics.data["requests"] = count

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
