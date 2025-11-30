"""Cryptography benchmarks."""
from __future__ import annotations

import argparse
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_cryptsetup_output
from ..utils import run_command


def run_cryptsetup_benchmark() -> BenchmarkResult:
    """Run cryptsetup cipher benchmark."""
    command = ["cryptsetup", "benchmark"]
    stdout, duration, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    
    try:
        metrics_data = parse_cryptsetup_output(stdout)
        status = "ok"
        metrics = BenchmarkMetrics(metrics_data)
        message = ""
    except ValueError as e:
        # Preserve output even when parsing fails
        status = "error"
        metrics = BenchmarkMetrics({})
        message = str(e)

    return BenchmarkResult(
        name="cryptsetup-benchmark",
        status=status,
        categories=(),
        presets=(),
        metrics=metrics,
        parameters=BenchmarkParameters({}),
        duration_seconds=duration,
        command="cryptsetup benchmark",
        raw_output=stdout,
        message=message,
    )


# Benchmark definitions for registration
def get_crypto_benchmarks():
    """Get list of cryptography benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="cryptsetup-benchmark",
            categories=("crypto", "io"),
            presets=("crypto", "io", "all"),
            description="cryptsetup cipher benchmark.",
            runner=lambda args: run_cryptsetup_benchmark(),
            requires=("cryptsetup",),
        ),
    ]
