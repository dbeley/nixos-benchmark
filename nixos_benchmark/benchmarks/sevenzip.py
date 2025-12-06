from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from . import BenchmarkType
from .base import BenchmarkBase


class SevenZipBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.SEVENZIP
    description = "7-Zip compression benchmark"
    _required_commands = ("7z",)
    version_command = ("7z",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["7z", "b"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            totals_match = re.search(r"Tot:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", stdout)
            avg_match = re.search(
                r"Avr:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\|\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
                stdout,
            )
            metrics_data: dict[str, float | str | int] = {}

            if totals_match:
                metrics_data["total_usage_pct"] = float(totals_match.group(1))
                metrics_data["total_ru"] = float(totals_match.group(2))
                metrics_data["total_rating_mips"] = float(totals_match.group(3))

            if avg_match:
                metrics_data["compress_usage_pct"] = float(avg_match.group(1))
                metrics_data["compress_ru_mips"] = float(avg_match.group(2))
                metrics_data["compress_rating_mips"] = float(avg_match.group(3))
                metrics_data["decompress_usage_pct"] = float(avg_match.group(4))
                metrics_data["decompress_ru_mips"] = float(avg_match.group(5))
                metrics_data["decompress_rating_mips"] = float(avg_match.group(6))

            if not metrics_data:
                raise ValueError("Unable to parse 7-Zip benchmark output")

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
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        rating = result.metrics.get("total_rating_mips")
        if rating is not None:
            return f"{rating:.0f} MIPS"
        return ""
