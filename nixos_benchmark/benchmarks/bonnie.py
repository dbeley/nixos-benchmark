from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_SIZE_MB = 512
DEFAULT_RAM_MB = 256


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
        with tempfile.TemporaryDirectory() as tmpdir:
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

        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        csv_lines = [line for line in stdout.splitlines() if line.count(",") > 10]
        if csv_lines:
            fields = csv_lines[-1].split(",")

            def parse_float(idx: int, key: str) -> None:
                if idx >= len(fields):
                    return
                try:
                    metrics_data[key] = float(fields[idx]) / 1024.0
                except ValueError:
                    return

            parse_float(9, "char_write_mb_s")
            parse_float(11, "block_write_mb_s")
            parse_float(13, "rewrite_mb_s")
            parse_float(15, "char_read_mb_s")
            parse_float(17, "block_read_mb_s")
            parse_float(19, "seeks_per_s")
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

        block_write = result.metrics.get("block_write_mb_s")
        block_read = result.metrics.get("block_read_mb_s")
        if block_write is not None and block_read is not None:
            return f"write {block_write:.1f} MiB/s, read {block_read:.1f} MiB/s"
        if block_write is not None:
            return f"write {block_write:.1f} MiB/s"
        if block_read is not None:
            return f"read {block_read:.1f} MiB/s"
        return ""
