from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_JOHN_RUNTIME = 5


class JohnBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.JOHN
    description = "John the Ripper CPU hash benchmark (sha512crypt)"
    _required_commands = ("john",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        runtime = DEFAULT_JOHN_RUNTIME
        # Use a temporary HOME to avoid polluting the user's ~/.john directory
        with tempfile.TemporaryDirectory() as temp_home:
            env = {"HOME": str(Path(temp_home))}
            command = ["john", f"--test={runtime}", "--format=sha512crypt"]
            stdout, duration, returncode = run_command(command, env=env)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            match = re.search(r"Raw:\s+([\d.]+)\s+c/s\s+real", stdout)
            if not match:
                raise ValueError("Unable to parse john benchmark output")
            cps = float(match.group(1))
            metrics = BenchmarkMetrics({"c_per_sec": cps})
            status = "ok"
            message = ""
        except ValueError as exc:
            metrics = BenchmarkMetrics({})
            status = "error"
            message = str(exc)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"runtime_secs": runtime, "hash_format": "sha512crypt"}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message
        cps = result.metrics.get("c_per_sec")
        if cps is not None:
            return f"{cps:,.0f} c/s"
        return ""
