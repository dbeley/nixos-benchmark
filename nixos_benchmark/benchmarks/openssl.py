from __future__ import annotations

import argparse
import re
import subprocess
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


# Default constants
DEFAULT_OPENSSL_SECONDS = 3
DEFAULT_OPENSSL_ALGORITHM = "aes-256-cbc"


class OpenSSLBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.OPENSSL_SPEED
    description = "OpenSSL AES-256 encryption throughput"
    _required_commands = ("openssl",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        seconds = DEFAULT_OPENSSL_SECONDS
        algorithm = DEFAULT_OPENSSL_ALGORITHM
        command = ["openssl", "speed", "-elapsed", "-seconds", str(seconds), algorithm]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            pattern = rf"^{re.escape(algorithm)}\s+(.+)$"
            match = re.search(pattern, stdout, flags=re.MULTILINE)
            if not match:
                raise ValueError(f"Unable to find throughput table for {algorithm!r}")

            values_str = match.group(1).split()
            block_sizes = ["16B", "64B", "256B", "1KiB", "8KiB", "16KiB"]
            metrics_data = {}
            for size, token in zip(block_sizes, values_str, strict=False):
                metrics_data[size] = float(token.rstrip("k"))
            metrics_data["max_kbytes_per_sec"] = max(metrics_data.values())

            status = "ok"
            metrics = BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data))
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"seconds": seconds, "algorithm": algorithm}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        throughput = result.metrics.get("max_kbytes_per_sec")
        if throughput is not None:
            return f"{throughput / 1024:.1f} MiB/s"
        return ""
