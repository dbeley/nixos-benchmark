from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from . import BenchmarkType
from .base import BenchmarkBase


class CLPeakBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.CLPEAK
    description = "OpenCL peak bandwidth/compute"
    _required_commands = ("clpeak",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["clpeak"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            if "no platforms found" in stdout.lower() or "clgetplatformids" in stdout.lower():
                raise ValueError("No OpenCL platforms found")

            metrics_data: dict[str, float | str | int] = {}
            bandwidth_pattern = re.compile(r"Global memory bandwidth.*?:\s*([\d.]+)\s*GB/s", flags=re.IGNORECASE)
            compute_patterns = [
                (r"Single-precision.*?:\s*([\d.]+)\s*GFLOPS", "compute_sp_gflops"),
                (r"Double-precision.*?:\s*([\d.]+)\s*GFLOPS", "compute_dp_gflops"),
                (r"Integer.*?:\s*([\d.]+)\s*GIOPS", "compute_int_giops"),
            ]
            for line in stdout.splitlines():
                bw_match = bandwidth_pattern.search(line)
                if bw_match:
                    metrics_data["global_memory_bandwidth_gb_per_s"] = float(bw_match.group(1))
                for pattern, key in compute_patterns:
                    match = re.search(pattern, line, flags=re.IGNORECASE)
                    if match:
                        metrics_data[key] = float(match.group(1))

            if not metrics_data:
                raise ValueError("Unable to parse clpeak metrics")

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
            command="clpeak",
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        bandwidth = result.metrics.get("global_memory_bandwidth_gb_per_s")
        if bandwidth is None and result.metrics.data:
            numeric_values = [v for v in result.metrics.data.values() if isinstance(v, (int, float))]
            if numeric_values:
                bandwidth = max(numeric_values)
        if bandwidth is not None:
            return f"{bandwidth:.1f} GB/s"
        return ""
