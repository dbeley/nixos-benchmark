from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import parse_float, run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_STRESSAPPTEST_SECONDS = 5
DEFAULT_STRESSAPPTEST_MEMORY_MB = 128
DEFAULT_STRESSAPPTEST_THREADS = 1


class StressAppTestBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.STRESSAPPTEST
    description = "stressapptest memory bandwidth"
    _required_commands = ("stressapptest",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        seconds = DEFAULT_STRESSAPPTEST_SECONDS
        memory_mb = DEFAULT_STRESSAPPTEST_MEMORY_MB
        threads = DEFAULT_STRESSAPPTEST_THREADS

        command = [
            "stressapptest",
            "-s",
            str(seconds),
            "-M",
            str(memory_mb),
            "-m",
            str(threads),
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            completed = re.search(
                r"Stats: Completed:\s+([\d.]+)M in ([\d.]+)s ([\d.]+)MB/s, with (\d+) hardware incidents, (\d+) errors",
                stdout,
            )
            if not completed:
                raise ValueError("Unable to parse stressapptest throughput")

            total_mb = parse_float(completed.group(1))
            runtime_secs = parse_float(completed.group(2))
            throughput_mb_s = parse_float(completed.group(3))
            incidents = int(completed.group(4))
            errors = int(completed.group(5))

            metrics = BenchmarkMetrics(
                {
                    "total_megabytes": total_mb,
                    "runtime_secs": runtime_secs,
                    "throughput_mb_per_s": throughput_mb_s,
                    "hardware_incidents": incidents,
                    "errors": errors,
                }
            )
            status = "ok"
            message = ""
        except ValueError as exc:
            metrics = BenchmarkMetrics({})
            status = "error"
            message = str(exc)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"seconds": seconds, "memory_mb": memory_mb, "threads": threads}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        throughput = result.metrics.get("throughput_mb_per_s")
        if throughput is not None:
            return f"{throughput:,.1f} MB/s"
        return ""
