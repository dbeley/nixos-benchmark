from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


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
            metrics = self.parse_metrics(stdout)
            status = "ok"
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

    def parse_metrics(self, stdout: str) -> BenchmarkMetrics:
        """Extract structured metrics from clpeak output."""
        if "no platforms found" in stdout.lower() or "clgetplatformids" in stdout.lower():
            raise ValueError("No OpenCL platforms found")

        metrics_data: dict[str, float | str | int] = {}
        section_values: dict[str, list[float]] = {
            "bandwidth": [],
            "compute_sp": [],
            "compute_dp": [],
            "compute_int": [],
        }

        current_section: str | None = None
        for line in stdout.splitlines():
            section = self._detect_section(line)
            if section == "reset":
                current_section = None
                continue
            if section:
                current_section = section
            if current_section:
                section_values[current_section].extend(self._extract_numbers(line))

        if section_values["bandwidth"]:
            metrics_data["global_memory_bandwidth_gb_per_s"] = max(section_values["bandwidth"])
        if section_values["compute_sp"]:
            metrics_data["compute_sp_gflops"] = max(section_values["compute_sp"])
        if section_values["compute_dp"]:
            metrics_data["compute_dp_gflops"] = max(section_values["compute_dp"])
        if section_values["compute_int"]:
            metrics_data["compute_int_giops"] = max(section_values["compute_int"])

        if not metrics_data:
            raise ValueError("Unable to parse clpeak metrics")

        return BenchmarkMetrics(metrics_data)

    @staticmethod
    def _extract_numbers(text: str) -> list[float]:
        return [float(match) for match in re.findall(r"[-+]?\d+(?:\.\d+)?", text)]

    @staticmethod
    def _detect_section(line: str) -> str | None:
        lower_line = line.lower()
        if not lower_line.strip():
            return "reset"
        if "global memory bandwidth" in lower_line:
            return "bandwidth"
        if "single-precision compute" in lower_line:
            return "compute_sp"
        if "double-precision compute" in lower_line:
            return "compute_dp"
        if "integer compute" in lower_line:
            return "compute_int"
        return None

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
