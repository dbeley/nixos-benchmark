"""Cryptography benchmarks."""
from __future__ import annotations

import argparse

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_cryptsetup_output
from ..utils import run_command


def run_cryptsetup_benchmark() -> BenchmarkResult:
    """Run cryptsetup cipher benchmark."""
    stdout, duration = run_command(["cryptsetup", "benchmark"])
    metrics_data = parse_cryptsetup_output(stdout)

    return BenchmarkResult(
        name="cryptsetup-benchmark",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({}),
        duration_seconds=duration,
        command="cryptsetup benchmark",
        raw_output=stdout,
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
