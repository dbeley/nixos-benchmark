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


DEFAULT_HASHCAT_RUNTIME = 5
DEFAULT_HASH_MODE = 0  # MD5


class HashcatBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.HASHCAT_GPU
    description = "hashcat GPU hash throughput (MD5)"
    _required_commands = ("hashcat",)

    def _availability_check(self, args: argparse.Namespace) -> tuple[bool, str]:
        # Quick device probe; if no backends are found, skip gracefully
        stdout, _, returncode = run_command(["hashcat", "-I"])
        if returncode != 0 or "Device #" not in stdout:
            return False, "hashcat: no usable backend devices detected"
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        runtime = DEFAULT_HASHCAT_RUNTIME
        hash_mode = DEFAULT_HASH_MODE

        with tempfile.TemporaryDirectory() as temp_home:
            env = {"HOME": str(Path(temp_home))}
            command = [
                "hashcat",
                "--benchmark",
                "--hash-type",
                str(hash_mode),
                "--runtime",
                str(runtime),
                "--quiet",
            ]
            stdout, duration, returncode = run_command(command, env=env)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            match = re.search(r"Speed.#\d+\.*:\s+([\d.]+)\s+([KMG])H/s", stdout)
            if not match:
                raise ValueError("Unable to parse hashcat speed output")
            value = float(match.group(1))
            unit = match.group(2)
            scale = {"K": 1_000.0, "M": 1_000_000.0, "G": 1_000_000_000.0}
            hashes_per_sec = value * scale[unit]

            metrics = BenchmarkMetrics({"hashes_per_sec": hashes_per_sec})
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
            parameters=BenchmarkParameters({"runtime_secs": runtime, "hash_mode": hash_mode}),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        hps = result.metrics.get("hashes_per_sec")
        if hps is not None:
            return f"{hps / 1_000_000:.1f} MH/s"
        return ""
