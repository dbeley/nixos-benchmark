from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from . import BenchmarkType
from .base import BenchmarkBase


class CryptsetupBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.CRYPTSETUP
    description = "cryptsetup cipher benchmark"
    _required_commands = ("cryptsetup",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["cryptsetup", "benchmark"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data: dict[str, float | str | int] = {}
            pattern = re.compile(
                r"^\s*(?P<cipher>[a-z0-9-]+)\s+(?P<keybits>\d+)b\s+(?P<enc>[\d.]+)\s+MiB/s\s+(?P<dec>[\d.]+)\s+MiB/s",
                flags=re.IGNORECASE,
            )
            for line in stdout.splitlines():
                match = pattern.search(line)
                if not match:
                    continue
                cipher = match.group("cipher")
                keybits = int(match.group("keybits"))
                enc = float(match.group("enc"))
                dec = float(match.group("dec"))
                metrics_data[f"{cipher}_{keybits}_enc_mib_per_s"] = enc
                metrics_data[f"{cipher}_{keybits}_dec_mib_per_s"] = dec

            if not metrics_data:
                raise ValueError("Unable to parse cryptsetup benchmark results")

            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
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
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command="cryptsetup benchmark",
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        speeds = [
            value
            for key, value in result.metrics.data.items()
            if key.endswith("_enc_mib_per_s") and isinstance(value, (int, float))
        ]
        if speeds:
            peak = max(speeds)
            return f"{peak:,.0f} MiB/s"
        return ""
