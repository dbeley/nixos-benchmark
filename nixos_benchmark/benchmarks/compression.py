"""Compression benchmarks."""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command, write_temp_data_file
from .base import (
    DEFAULT_COMPRESS_SIZE_MB,
    DEFAULT_PIGZ_LEVEL,
    DEFAULT_ZSTD_LEVEL,
)


def run_zstd_benchmark(
    level: int = DEFAULT_ZSTD_LEVEL, size_mb: int = DEFAULT_COMPRESS_SIZE_MB
) -> BenchmarkResult:
    """Run zstd compression benchmark."""
    data_path = write_temp_data_file(size_mb)
    compressed_path = data_path.with_suffix(data_path.suffix + ".zst")
    decompressed_path = data_path.with_suffix(".out")
    try:
        start = time.perf_counter()
        command = [
            "zstd",
            "-q",
            "-f",
            f"-{level}",
            str(data_path),
            "-o",
            str(compressed_path),
        ]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        compress_duration = time.perf_counter() - start

        data_path.unlink(missing_ok=True)
        start = time.perf_counter()
        command = [
            "zstd",
            "-d",
            "-q",
            "-f",
            str(compressed_path),
            "-o",
            str(decompressed_path),
        ]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        decompress_duration = time.perf_counter() - start
    finally:
        data_path.unlink(missing_ok=True)
        compressed_path.unlink(missing_ok=True)
        decompressed_path.unlink(missing_ok=True)

    metrics_data = {
        "compress_mb_per_s": size_mb / compress_duration if compress_duration else 0.0,
        "decompress_mb_per_s": size_mb / decompress_duration
        if decompress_duration
        else 0.0,
        "level": level,
        "size_mb": size_mb,
    }

    return BenchmarkResult(
        name="zstd-compress",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"level": level, "size_mb": size_mb}),
        duration_seconds=compress_duration + decompress_duration,
        command=f"zstd -q -f -{level} {data_path} -o {compressed_path}",
        raw_output="",
    )


def run_pigz_benchmark(
    level: int = DEFAULT_PIGZ_LEVEL, size_mb: int = DEFAULT_COMPRESS_SIZE_MB
) -> BenchmarkResult:
    """Run pigz compression benchmark."""
    data_path = write_temp_data_file(size_mb)
    compressed_path = Path(f"{data_path}.gz")
    decompressed_path = compressed_path.with_suffix("")
    try:
        start = time.perf_counter()
        command = ["pigz", "-f", "-k", "-p", "0", f"-{level}", str(data_path)]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        compress_duration = time.perf_counter() - start

        data_path.unlink(missing_ok=True)
        start = time.perf_counter()
        command = ["pigz", "-d", "-f", "-k", str(compressed_path)]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        decompress_duration = time.perf_counter() - start
    finally:
        data_path.unlink(missing_ok=True)
        compressed_path.unlink(missing_ok=True)
        decompressed_path.unlink(missing_ok=True)

    metrics_data = {
        "compress_mb_per_s": size_mb / compress_duration if compress_duration else 0.0,
        "decompress_mb_per_s": size_mb / decompress_duration
        if decompress_duration
        else 0.0,
        "level": level,
        "size_mb": size_mb,
    }

    return BenchmarkResult(
        name="pigz-compress",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"level": level, "size_mb": size_mb}),
        duration_seconds=compress_duration + decompress_duration,
        command=f"pigz -f -k -p 0 -{level} {data_path}",
        raw_output="",
    )


# Benchmark definitions for registration
def get_compression_benchmarks():
    """Get list of compression benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="zstd-compress",
            categories=("cpu", "compression"),
            presets=("cpu", "compression", "all"),
            description="zstd compress/decompress throughput.",
            runner=lambda args: run_zstd_benchmark(
                DEFAULT_ZSTD_LEVEL, DEFAULT_COMPRESS_SIZE_MB
            ),
            requires=("zstd",),
        ),
        BenchmarkDefinition(
            key="pigz-compress",
            categories=("cpu", "compression"),
            presets=("cpu", "compression", "all"),
            description="pigz compress/decompress throughput.",
            runner=lambda args: run_pigz_benchmark(
                DEFAULT_PIGZ_LEVEL, DEFAULT_COMPRESS_SIZE_MB
            ),
            requires=("pigz",),
        ),
    ]
