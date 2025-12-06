from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import parse_float, run_command
from . import BenchmarkType
from .base import BenchmarkBase


class TinyMemBenchBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.TINYMEMBENCH
    description = "TinyMemBench memory throughput"
    _required_commands = ("tinymembench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["tinymembench"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data: dict[str, float | str | int] = {}
            for line in stdout.splitlines():
                match = re.match(r"\s*([A-Za-z0-9 +/_-]+?)\s*:?\s+([\d.,]+)\s+M(?:i)?B/s", line)
                if not match:
                    continue
                label = re.sub(r"\s+", "_", match.group(1).strip().lower())
                metrics_data[f"{label}_mb_per_s"] = parse_float(match.group(2))

            if not metrics_data:
                raise ValueError("Unable to parse tinymembench throughput")

            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
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
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command="tinymembench",
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        memcpy = result.metrics.get("memcpy_mb_per_s")
        if memcpy is None:
            memcpy = result.metrics.get("memcpy_-_aligned_mb_per_s")
        if memcpy is None and result.metrics.data:
            numeric_values = [v for v in result.metrics.data.values() if isinstance(v, (int, float))]
            if numeric_values:
                memcpy = max(numeric_values)
        if memcpy is not None:
            return f"{memcpy:,.0f} MB/s"
        return ""
