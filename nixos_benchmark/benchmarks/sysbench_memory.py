from __future__ import annotations

import argparse
import os
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import (
    DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
    DEFAULT_SYSBENCH_MEMORY_OPERATION,
    DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
    DEFAULT_SYSBENCH_THREADS,
    BenchmarkBase,
)


class SysbenchMemoryBenchmark(BenchmarkBase):
    key = "sysbench-memory"
    categories = ("memory",)
    presets = ("balanced", "memory", "all")
    description = "sysbench memory throughput"
    _required_commands = ("sysbench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        threads = DEFAULT_SYSBENCH_THREADS
        block_kb = DEFAULT_SYSBENCH_MEMORY_BLOCK_KB
        total_mb = DEFAULT_SYSBENCH_MEMORY_TOTAL_MB
        operation = DEFAULT_SYSBENCH_MEMORY_OPERATION
        thread_count = threads if threads > 0 else (os.cpu_count() or 1)

        command = [
            "sysbench",
            "memory",
            f"--memory-block-size={block_kb}K",
            f"--memory-total-size={total_mb}M",
            f"--memory-oper={operation}",
            f"--threads={thread_count}",
            "run",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data: dict[str, float | str | int] = {}
            operations = re.search(r"Total operations:\s+([\d.]+)\s+\(([\d.]+)\s+per second\)", stdout)
            throughput = re.search(r"([\d.]+)\s+MiB transferred\s+\(([\d.]+)\s+MiB/sec\)", stdout)
            total_time = re.search(r"total time:\s+([\d.]+)s", stdout)
            if operations:
                metrics_data["operations"] = float(operations.group(1))
                metrics_data["operations_per_sec"] = float(operations.group(2))
            if throughput:
                metrics_data["transferred_mib"] = float(throughput.group(1))
                metrics_data["throughput_mib_per_s"] = float(throughput.group(2))
            if total_time:
                metrics_data["total_time_secs"] = float(total_time.group(1))
            if not metrics_data:
                raise ValueError("Unable to parse sysbench memory output")

            metrics_data["threads"] = thread_count
            metrics_data["block_kb"] = block_kb
            metrics_data["total_mb"] = total_mb
            metrics_data["operation"] = operation
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="sysbench-memory",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters(
                {
                    "threads": thread_count,
                    "block_kb": block_kb,
                    "total_mb": total_mb,
                    "operation": operation,
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

        throughput = result.metrics.get("throughput_mib_per_s")
        if throughput is not None:
            return f"{throughput:,.0f} MiB/s"
        return ""
