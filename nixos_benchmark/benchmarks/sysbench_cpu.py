from __future__ import annotations

import argparse
import os
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import (
    DEFAULT_SYSBENCH_CPU_MAX_PRIME,
    DEFAULT_SYSBENCH_RUNTIME,
    DEFAULT_SYSBENCH_THREADS,
    BenchmarkBase,
)


class SysbenchCPUBenchmark(BenchmarkBase):
    key = "sysbench-cpu"
    categories = ("cpu",)
    presets = ("balanced", "cpu", "all")
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
            name="sysbench-cpu",
            status=status,
            categories=(),
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
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        events = result.metrics.get("events_per_sec")
        if events is not None:
            return f"{events:,.1f} events/s"
        return ""
