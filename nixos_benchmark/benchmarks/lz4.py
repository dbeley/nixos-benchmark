from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command, write_temp_data_file
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_LZ4_SIZE_MB = 64
DEFAULT_LZ4_LEVEL = 1
DEFAULT_LZ4_TIME = 2  # seconds per level


class LZ4Benchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.LZ4
    description = "lz4 compression/decompression throughput"
    _required_commands = ("lz4",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        size_mb = DEFAULT_LZ4_SIZE_MB
        level = DEFAULT_LZ4_LEVEL
        time_per_level = DEFAULT_LZ4_TIME

        data_path = write_temp_data_file(size_mb)
        try:
            command = [
                "lz4",
                f"-b{level}",
                f"-e{level}",
                f"-i{time_per_level}",
                str(data_path),
            ]
            stdout, duration, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)

            try:
                compress_speed, decompress_speed = self._parse_speeds(stdout)
                metrics = BenchmarkMetrics(
                    {
                        "compress_mb_per_s": compress_speed,
                        "decompress_mb_per_s": decompress_speed,
                        "level": level,
                        "size_mb": size_mb,
                    }
                )
                status = "ok"
                message = ""
            except ValueError as exc:
                metrics = BenchmarkMetrics({})
                status = "error"
                message = str(exc)
        finally:
            data_path.unlink(missing_ok=True)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"size_mb": size_mb, "level": level, "time_per_level_secs": time_per_level}),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    @staticmethod
    def _parse_speeds(text: str) -> tuple[float, float]:
        # Search for the last occurrence of ", <comp> MB/s, <decomp> MB/s"
        matches = list(re.finditer(r",\s*([\d.]+)\s+MB/s(?:,\s*([\d.]+)\s+MB/s)?", text))
        if not matches:
            raise ValueError("Unable to parse lz4 benchmark output")
        comp = float(matches[-1].group(1))
        decomp_group = matches[-1].group(2)
        decomp = float(decomp_group) if decomp_group is not None else 0.0
        return comp, decomp

    def format_result(self, result: BenchmarkResult) -> str:
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        comp = result.metrics.get("compress_mb_per_s")
        decomp = result.metrics.get("decompress_mb_per_s")
        if comp is not None and decomp is not None:
            return f"{comp:,.0f} / {decomp:,.0f} MB/s (c/d)"
        return ""
