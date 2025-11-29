"""Memory benchmarks."""
from __future__ import annotations

import argparse
import os
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_sysbench_memory_output, parse_tinymembench_output
from ..utils import run_command
from .base import (
    DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
    DEFAULT_SYSBENCH_MEMORY_OPERATION,
    DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
    DEFAULT_SYSBENCH_THREADS,
)


def run_sysbench_memory(
    threads: int = DEFAULT_SYSBENCH_THREADS,
    block_kb: int = DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
    total_mb: int = DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
    operation: str = DEFAULT_SYSBENCH_MEMORY_OPERATION,
) -> BenchmarkResult:
    """Run sysbench memory benchmark."""
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
        metrics_data = parse_sysbench_memory_output(stdout)
        metrics_data["threads"] = thread_count
        metrics_data["block_kb"] = block_kb
        metrics_data["total_mb"] = total_mb
        metrics_data["operation"] = operation
        status = "ok"
        metrics = BenchmarkMetrics(metrics_data)
        message = ""
    except ValueError as e:
        # Preserve output even when parsing fails
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


def run_tinymembench() -> BenchmarkResult:
    """Run tinymembench memory throughput test."""
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
