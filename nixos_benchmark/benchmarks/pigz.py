from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
import time

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command, write_temp_data_file
from .base import (
    BenchmarkBase,
    DEFAULT_COMPRESS_SIZE_MB,
    DEFAULT_PIGZ_LEVEL,
)


class PigzBenchmark(BenchmarkBase):
    key = "pigz-compress"
    categories = ("cpu", "compression")
    presets = ("cpu", "compression", "all")
    description = "pigz compress/decompress throughput"
    _required_commands = ("pigz",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        level = DEFAULT_PIGZ_LEVEL
        size_mb = DEFAULT_COMPRESS_SIZE_MB
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
            "decompress_mb_per_s": size_mb / decompress_duration if decompress_duration else 0.0,
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


    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"
        
        comp = result.metrics.get("compress_mb_per_s")
        decomp = result.metrics.get("decompress_mb_per_s")
        if comp is not None and decomp is not None:
            return f"C {comp:.0f}/D {decomp:.0f} MB/s"
        return ""
