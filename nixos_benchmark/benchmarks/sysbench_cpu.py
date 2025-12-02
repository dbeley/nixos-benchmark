from __future__ import annotations

import argparse
import os
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


# Default constants
DEFAULT_SYSBENCH_CPU_MAX_PRIME = 20000
DEFAULT_SYSBENCH_RUNTIME = 5
DEFAULT_SYSBENCH_THREADS = 0


class SysbenchCPUBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.SYSBENCH_CPU
    description = "sysbench CPU benchmark"
    _required_commands = ("sysbench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        threads = DEFAULT_SYSBENCH_THREADS
        max_prime = DEFAULT_SYSBENCH_CPU_MAX_PRIME
        runtime_secs = DEFAULT_SYSBENCH_RUNTIME
        thread_count = threads if threads > 0 else (os.cpu_count() or 1)

        command = [
            "sysbench",
            "cpu",
            f"--cpu-max-prime={max_prime}",
            f"--threads={thread_count}",
            f"--time={runtime_secs}",
            "run",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data: dict[str, float | str | int] = {}
            events_per_sec = re.search(r"events per second:\s+([\d.]+)", stdout)
            total_time = re.search(r"total time:\s+([\d.]+)s", stdout)
            total_events = re.search(r"total number of events:\s+([\d.]+)", stdout)
            if events_per_sec:
                metrics_data["events_per_sec"] = float(events_per_sec.group(1))
            if total_time:
                metrics_data["total_time_secs"] = float(total_time.group(1))
            if total_events:
                metrics_data["total_events"] = float(total_events.group(1))
            if not metrics_data:
                raise ValueError("Unable to parse sysbench CPU output")

            metrics_data["threads"] = thread_count
            metrics_data["cpu_max_prime"] = max_prime
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
            parameters=BenchmarkParameters(
                {
                    "threads": thread_count,
                    "cpu_max_prime": max_prime,
                    "runtime_secs": runtime_secs,
                }
            ),
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

        events = result.metrics.get("events_per_sec")
        if events is not None:
            return f"{events:,.1f} events/s"
        return ""
