"""hashcat GPU hash throughput benchmark."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkParameters, BenchmarkResult
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
        stdout, _, returncode = run_command(["hashcat", "-I"])
        if returncode != 0 or ("Device #" not in stdout and "Backend Device ID" not in stdout):
            return False, "hashcat: no usable backend devices detected"
        return True, ""

    @staticmethod
    def _parse_hashcat(stdout: str) -> dict[str, float | str | int]:
        match = re.search(r"Speed.#\d+\.*:\s+([\d.]+)\s+([KMG])H/s", stdout)
        if not match:
            raise ValueError("Unable to parse hashcat speed output")
        value = float(match.group(1))
        unit = match.group(2)
        scale = {"K": 1_000.0, "M": 1_000_000.0, "G": 1_000_000_000.0}
        hashes_per_sec = value * scale[unit]
        return {"hashes_per_sec": hashes_per_sec}

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

        status, metrics, message = self.parse_metrics(lambda: self._parse_hashcat(stdout))

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"runtime_secs": runtime, "hash_mode": hash_mode}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        hps = result.metrics.get("hashes_per_sec")
        if hps is not None:
            return f"{hps / 1_000_000:.1f} MH/s"
        return ""
