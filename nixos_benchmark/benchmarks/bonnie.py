from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_SIZE_MB = 4096
DEFAULT_RAM_MB = 512


def _bonnie_scratch_dir() -> Path:
    """Return a directory on a real disk, not tmpfs (/tmp)."""
    base = Path("results")
    base.mkdir(parents=True, exist_ok=True)
    return base


class BonnieBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.BONNIE
    description = "Bonnie++ filesystem benchmark"
    _required_commands = ("bonnie++",)

    def get_version(self) -> str:
        stdout, _, _ = run_command(["bonnie++", "-V"])
        match = re.search(r"([0-9]+(?:\.[0-9]+)+)", stdout)
        if match:
            return match.group(1)
        return super().get_version()

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        uid = os.getuid()
        with tempfile.TemporaryDirectory(dir=_bonnie_scratch_dir()) as tmpdir:
            command = [
                "bonnie++",
                "-d",
                tmpdir,
                "-s",
                str(DEFAULT_SIZE_MB),
                "-r",
                str(DEFAULT_RAM_MB),
                "-n",
                "0",
                "-u",
                str(uid),
                "-q",
            ]

            stdout, duration, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)

        for leftover in Path("results").glob("Bonnie.*"):
            if leftover.is_file():
                leftover.unlink(missing_ok=True)

        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        csv_lines = [line for line in stdout.splitlines() if line.count(",") > 10]
        if csv_lines:
            fields = csv_lines[-1].split(",")

            def parse_float(idx: int, key: str) -> None:
                if idx >= len(fields):
                    return
                value = fields[idx]
                if not value or value.startswith("+"):
                    return
                try:
                    metrics_data[key] = float(value) / 1024.0
                except ValueError:
                    return

            def parse_latency(idx: int, key: str) -> None:
                if idx >= len(fields):
                    return
                value = fields[idx].strip()
                match = re.match(r"(\d+(?:\.\d+)?)\s*us", value)
                if match:
                    metrics_data[key] = float(match.group(1)) / 1000.0

            parse_float(9, "char_write_mb_s")
            parse_float(11, "block_write_mb_s")
            parse_float(13, "rewrite_mb_s")
            parse_float(15, "char_read_mb_s")
            parse_float(17, "block_read_mb_s")
            parse_float(19, "seeks_per_s")

            parse_latency(38, "char_write_latency_ms")
            parse_latency(39, "block_write_latency_ms")
            parse_latency(40, "rewrite_latency_ms")
            parse_latency(41, "char_read_latency_ms")
            parse_latency(42, "block_read_latency_ms")
            parse_latency(43, "seeks_latency_ms")
            if not metrics_data:
                status = "error"
                message = (
                    "bonnie++ could not measure throughput (all values too fast to time). "
                    "Increase the test file size or use a slower filesystem."
                )
        else:
            status = "error"
            message = "Unable to parse bonnie++ output"

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters(
                {"size_mb": DEFAULT_SIZE_MB, "ram_mb": DEFAULT_RAM_MB, "iterations": 1, "uid": uid}
            ),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        write = result.metrics.get("block_write_mb_s") or result.metrics.get("char_write_mb_s")
        read = result.metrics.get("block_read_mb_s") or result.metrics.get("char_read_mb_s")
        if write is not None and read is not None:
            return f"write {write:.1f} MiB/s, read {read:.1f} MiB/s"
        if write is not None:
            return f"write {write:.1f} MiB/s"
        if read is not None:
            return f"read {read:.1f} MiB/s"
        return ""
