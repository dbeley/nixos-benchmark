"""CPU benchmarks."""
from __future__ import annotations

import argparse
import os
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import (
    parse_7zip_output,
    parse_openssl_output,
    parse_stress_ng_output,
    parse_sysbench_cpu_output,
)
from ..utils import run_command
from .base import (
    DEFAULT_OPENSSL_ALGORITHM,
    DEFAULT_OPENSSL_SECONDS,
    DEFAULT_STRESS_NG_METHOD,
    DEFAULT_STRESS_NG_SECONDS,
    DEFAULT_SYSBENCH_CPU_MAX_PRIME,
    DEFAULT_SYSBENCH_RUNTIME,
    DEFAULT_SYSBENCH_THREADS,
)


def run_openssl(
    seconds: int = DEFAULT_OPENSSL_SECONDS,
    algorithm: str = DEFAULT_OPENSSL_ALGORITHM,
) -> BenchmarkResult:
    """Run OpenSSL speed benchmark."""
    command = ["openssl", "speed", "-elapsed", "-seconds", str(seconds), algorithm]
    stdout, duration, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    metrics_data = parse_openssl_output(stdout, algorithm)

    return BenchmarkResult(
        name="openssl-speed",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"seconds": seconds, "algorithm": algorithm}),
        duration_seconds=duration,
        command=" ".join(command),
        raw_output=stdout,
    )


def run_7zip() -> BenchmarkResult:
    """Run 7-Zip benchmark."""
    command = ["7z", "b"]
    stdout, duration, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    metrics_data = parse_7zip_output(stdout)

    return BenchmarkResult(
        name="7zip-benchmark",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({}),
        duration_seconds=duration,
        command=" ".join(command),
        raw_output=stdout,
    )


def run_stress_ng(
    seconds: int = DEFAULT_STRESS_NG_SECONDS,
    method: str = DEFAULT_STRESS_NG_METHOD,
) -> BenchmarkResult:
    """Run stress-ng CPU benchmark."""
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
    metrics_data = parse_stress_ng_output(stdout)

    return BenchmarkResult(
        name="stress-ng",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"seconds": seconds, "cpu_method": method}),
        duration_seconds=duration,
        command=" ".join(command),
        raw_output=stdout,
    )


def run_sysbench_cpu(
    threads: int = DEFAULT_SYSBENCH_THREADS,
    max_prime: int = DEFAULT_SYSBENCH_CPU_MAX_PRIME,
    runtime_secs: int = DEFAULT_SYSBENCH_RUNTIME,
) -> BenchmarkResult:
    """Run sysbench CPU benchmark."""
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
    metrics_data = parse_sysbench_cpu_output(stdout)
    metrics_data["threads"] = thread_count
    metrics_data["cpu_max_prime"] = max_prime

    return BenchmarkResult(
        name="sysbench-cpu",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
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
    )


# Benchmark definitions for registration
def get_cpu_benchmarks():
    """Get list of CPU benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="openssl-speed",
            categories=("cpu", "crypto"),
            presets=("balanced", "cpu", "crypto", "all"),
            description="OpenSSL AES-256 encryption throughput.",
            runner=lambda args: run_openssl(
                DEFAULT_OPENSSL_SECONDS, DEFAULT_OPENSSL_ALGORITHM
            ),
            requires=("openssl",),
        ),
        BenchmarkDefinition(
            key="7zip-benchmark",
            categories=("cpu", "compression"),
            presets=("balanced", "cpu", "compression", "all"),
            description="7-Zip compression benchmark.",
            runner=lambda args: run_7zip(),
            requires=("7z",),
        ),
        BenchmarkDefinition(
            key="stress-ng",
            categories=("cpu",),
            presets=("balanced", "cpu", "all"),
            description="stress-ng CPU stress test.",
            runner=lambda args: run_stress_ng(
                DEFAULT_STRESS_NG_SECONDS, DEFAULT_STRESS_NG_METHOD
            ),
            requires=("stress-ng",),
        ),
        BenchmarkDefinition(
            key="sysbench-cpu",
            categories=("cpu",),
            presets=("balanced", "cpu", "all"),
            description="sysbench CPU benchmark.",
            runner=lambda args: run_sysbench_cpu(
                DEFAULT_SYSBENCH_THREADS,
                DEFAULT_SYSBENCH_CPU_MAX_PRIME,
                DEFAULT_SYSBENCH_RUNTIME,
            ),
            requires=("sysbench",),
        ),
    ]
