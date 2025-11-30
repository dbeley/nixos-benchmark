from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import (
    DEFAULT_STRESS_NG_METHOD,
    DEFAULT_STRESS_NG_SECONDS,
    BenchmarkBase,
)


class StressNGBenchmark(BenchmarkBase):
    key = "stress-ng"
    categories = ("cpu",)
    presets = ("balanced", "cpu", "all")
    description = "stress-ng CPU stress test"
    _required_commands = ("stress-ng",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        seconds = DEFAULT_STRESS_NG_SECONDS
        method = DEFAULT_STRESS_NG_METHOD
        command = [
            "stress-ng",
            "--cpu",
            "0",
            "--cpu-method",
            method,
            "--timeout",
            f"{seconds}s",
            "--metrics-brief",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            pattern = re.compile(
                r"stress-ng:\s+\w+:\s+\[\d+\]\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
                r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
            )
            metrics_data = {}
            for line in stdout.splitlines():
                match = pattern.search(line)
                if not match:
                    continue
                stressor_name = match.group(1)
                if stressor_name == "stressor" or stressor_name.startswith("("):
                    continue
                metrics_data = {
                    "stressor": stressor_name,
                    "bogo_ops": float(match.group(2)),
                    "real_time_secs": float(match.group(3)),
                    "user_time_secs": float(match.group(4)),
                    "system_time_secs": float(match.group(5)),
                    "bogo_ops_per_sec_real": float(match.group(6)),
                    "bogo_ops_per_sec_cpu": float(match.group(7)),
                }
                break

            if not metrics_data:
                raise ValueError("Unable to parse stress-ng metrics (try increasing runtime)")

            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="stress-ng",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"seconds": seconds, "cpu_method": method}),
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

        ops = result.metrics.get("bogo_ops_per_sec_real")
        if ops is not None:
            return f"{ops:,.0f} bogo-ops/s"
        return ""
