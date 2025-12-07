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


DEFAULT_FILE_SIZE = "64M"
DEFAULT_RECORD_SIZE = "1M"


class IozoneBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.IOZONE
    description = "Iozone sequential and random IO benchmark"
    _required_commands = ("iozone",)

    def get_version(self) -> str:
        stdout, _, _ = run_command(["iozone", "-h"])
        version_match = re.search(r"Version\s+([0-9.]+)", stdout)
        if not version_match:
            version_match = re.search(r"Revision[:\s]+([0-9.]+)", stdout)
        if version_match:
            return version_match.group(1)
        return super().get_version()

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = Path(tmpdir) / "iozone.tmp"
            command = [
                "iozone",
                "-I",
                "-s",
                DEFAULT_FILE_SIZE,
                "-r",
                DEFAULT_RECORD_SIZE,
                "-i",
                "0",
                "-i",
                "1",
                "-i",
                "2",
                "-f",
                str(data_path),
            ]

            stdout, duration, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)

        metrics_data: dict[str, float | str | int] = {}
        message = ""
        status = "ok"

        data_line = next((line for line in stdout.splitlines() if re.match(r"\s*\d+\s+\d+\s+\d", line)), None)
        file_kb = 0
        record_kb = 0
        if data_line:
            tokens = data_line.split()
            try:
                file_kb = int(tokens[0])
                record_kb = int(tokens[1])
            except ValueError:
                pass

            def set_metric(idx: int, key: str) -> None:
                if idx >= len(tokens):
                    return
                try:
                    metrics_data[key] = float(tokens[idx]) / 1024.0
                except ValueError:
                    return

            set_metric(2, "write_mb_s")
            set_metric(3, "rewrite_mb_s")
            set_metric(4, "read_mb_s")
            set_metric(5, "reread_mb_s")
            set_metric(6, "random_read_mb_s")
            set_metric(7, "random_write_mb_s")
            set_metric(8, "bkwd_read_mb_s")
            set_metric(9, "record_rewrite_mb_s")
            set_metric(10, "stride_read_mb_s")
            set_metric(11, "fwrite_mb_s")
            set_metric(12, "frewrite_mb_s")
            set_metric(13, "fread_mb_s")
            set_metric(14, "freread_mb_s")
        else:
            status = "error"
            message = "Unable to parse iozone output"

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters(
                {
                    "file_size": DEFAULT_FILE_SIZE,
                    "record_size": DEFAULT_RECORD_SIZE,
                    "file_size_kb": file_kb,
                    "record_size_kb": record_kb,
                }
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

        write = result.metrics.get("write_mb_s")
        read = result.metrics.get("read_mb_s")
        if write is not None and read is not None:
            return f"write {write:.1f} MiB/s, read {read:.1f} MiB/s"
        if write is not None:
            return f"write {write:.1f} MiB/s"
        if read is not None:
            return f"read {read:.1f} MiB/s"
        return ""
