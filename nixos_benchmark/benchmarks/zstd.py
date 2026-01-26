from __future__ import annotations

import argparse
import subprocess
import time
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command, write_temp_data_file
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_ZSTD_LEVEL = 5
DEFAULT_COMPRESS_SIZE_MB = 32


class ZstdBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.ZSTD
    description = "zstd compress/decompress throughput"
    _required_commands = ("zstd",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        level = DEFAULT_ZSTD_LEVEL
        size_mb = DEFAULT_COMPRESS_SIZE_MB
        data_path = write_temp_data_file(size_mb)
        compressed_path = data_path.with_suffix(data_path.suffix + ".zst")
        decompressed_path = data_path.with_suffix(".out")

        try:
            start = time.perf_counter()
            compress_command = [
                "zstd",
                "-q",
                "-f",
                f"-{level}",
                str(data_path),
                "-o",
                str(compressed_path),
            ]
            stdout, _, returncode = run_command(compress_command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, compress_command, stdout)
            compress_duration = time.perf_counter() - start

            data_path.unlink(missing_ok=True)
            start = time.perf_counter()
            decompress_command = [
                "zstd",
                "-d",
                "-q",
                "-f",
                str(compressed_path),
                "-o",
                str(decompressed_path),
            ]
            stdout, _, returncode = run_command(decompress_command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, decompress_command, stdout)
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
            benchmark_type=self.benchmark_type,
            status="ok",
            presets=(),
            metrics=BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data)),
            parameters=BenchmarkParameters({"level": level, "size_mb": size_mb}),
            duration_seconds=compress_duration + decompress_duration,
            command=self.format_command(compress_command),
            raw_output=stdout,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        comp = result.metrics.get("compress_mb_per_s")
        decomp = result.metrics.get("decompress_mb_per_s")
        if comp is not None and decomp is not None:
            return f"C {comp:.0f}/D {decomp:.0f} MB/s"
        return ""
