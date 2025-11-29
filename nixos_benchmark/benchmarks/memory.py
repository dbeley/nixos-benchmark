"""Memory benchmarks."""
from __future__ import annotations

import argparse
import os
import subprocess
from typing import ClassVar, Tuple

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_sysbench_memory_output, parse_tinymembench_output
from ..utils import command_exists, run_command
from .base import (
    BenchmarkBase,
    DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
    DEFAULT_SYSBENCH_MEMORY_OPERATION,
    DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
    DEFAULT_SYSBENCH_THREADS,
)


class SysbenchMemoryBenchmark(BenchmarkBase):
    """sysbench memory benchmark."""

    key: ClassVar[str] = "sysbench-memory"
    categories: ClassVar[Tuple[str, ...]] = ("memory",)
    presets: ClassVar[Tuple[str, ...]] = ("balanced", "memory", "all")
    description: ClassVar[str] = "sysbench memory throughput."

    def __init__(
        self,
        threads: int = DEFAULT_SYSBENCH_THREADS,
        block_kb: int = DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
        total_mb: int = DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
        operation: str = DEFAULT_SYSBENCH_MEMORY_OPERATION,
    ):
        self.threads = threads
        self.block_kb = block_kb
        self.total_mb = total_mb
        self.operation = operation

    def get_required_commands(self) -> Tuple[str, ...]:
        return ("sysbench",)

    def validate(self) -> Tuple[bool, str]:
        """Pre-flight check before execution."""
        for cmd in self.get_required_commands():
            if not command_exists(cmd):
                return False, f"Command {cmd!r} not found in PATH"
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Run the benchmark."""
        thread_count = self.threads if self.threads > 0 else (os.cpu_count() or 1)
        command = [
            "sysbench",
            "memory",
            f"--memory-block-size={self.block_kb}K",
            f"--memory-total-size={self.total_mb}M",
            f"--memory-oper={self.operation}",
            f"--threads={thread_count}",
            "run",
        ]
        stdout, duration, returncode = run_command(command)

        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data = parse_sysbench_memory_output(stdout)
            metrics_data["threads"] = thread_count
            metrics_data["block_kb"] = self.block_kb
            metrics_data["total_mb"] = self.total_mb
            metrics_data["operation"] = self.operation
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name=self.key,
            status=status,
            categories=self.categories,
            presets=self.presets,
            metrics=metrics,
            parameters=BenchmarkParameters(
                {
                    "threads": thread_count,
                    "block_kb": self.block_kb,
                    "total_mb": self.total_mb,
                    "operation": self.operation,
                }
            ),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        throughput = result.metrics.get("throughput_mib_per_s")
        if throughput is not None:
            return f"{throughput:,.0f} MiB/s"
        return ""


# Legacy function wrapper for backward compatibility
def run_sysbench_memory(
    threads: int = DEFAULT_SYSBENCH_THREADS,
    block_kb: int = DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
    total_mb: int = DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
    operation: str = DEFAULT_SYSBENCH_MEMORY_OPERATION,
) -> BenchmarkResult:
    """Run sysbench memory benchmark."""
    benchmark = SysbenchMemoryBenchmark(threads, block_kb, total_mb, operation)
    return benchmark.execute(argparse.Namespace())


def run_tinymembench() -> BenchmarkResult:
    """Run tinymembench memory throughput test."""
    from ..parsers import parse_tinymembench_output
    
    command = ["tinymembench"]
    stdout, duration, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    
    try:
        metrics_data = parse_tinymembench_output(stdout)
        status = "ok"
        metrics = BenchmarkMetrics(metrics_data)
        message = ""
    except ValueError as e:
        # Preserve output even when parsing fails
        status = "error"
        metrics = BenchmarkMetrics({})
        message = str(e)

    return BenchmarkResult(
        name="tinymembench",
        status=status,
        categories=(),
        presets=(),
        metrics=metrics,
        parameters=BenchmarkParameters({}),
        duration_seconds=duration,
        command="tinymembench",
        raw_output=stdout,
        message=message,
    )


# Benchmark definitions for registration
def get_memory_benchmarks():
    """Get list of memory benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="sysbench-memory",
            categories=("memory",),
            presets=("balanced", "memory", "all"),
            description="sysbench memory throughput.",
            runner=lambda args: run_sysbench_memory(
                DEFAULT_SYSBENCH_THREADS,
                DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
                DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
                DEFAULT_SYSBENCH_MEMORY_OPERATION,
            ),
            requires=("sysbench",),
        ),
        BenchmarkDefinition(
            key="tinymembench",
            categories=("memory",),
            presets=("memory", "all"),
            description="TinyMemBench memory throughput.",
            runner=lambda args: run_tinymembench(),
            requires=("tinymembench",),
        ),
    ]


# Registry of benchmark classes
MEMORY_BENCHMARK_CLASSES = [
    SysbenchMemoryBenchmark,
]

