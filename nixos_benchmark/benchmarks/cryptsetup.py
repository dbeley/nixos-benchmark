from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase


class CryptsetupBenchmark(BenchmarkBase):
    name = "cryptsetup-benchmark"
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
            name="cryptsetup-benchmark",
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
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        speeds = [
            value
            for key, value in result.metrics.data.items()
            if key.endswith("_enc_mib_per_s") and isinstance(value, (int, float))
        ]
        if speeds:
            peak = max(speeds)
            return f"{peak:,.0f} MiB/s"
        return ""
