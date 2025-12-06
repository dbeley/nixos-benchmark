from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_STOCKFISH_THREADS = 0  # 0 = auto-detect
DEFAULT_STOCKFISH_LIMIT = 10  # seconds


class StockfishBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.STOCKFISH
    description = "Stockfish built-in bench (nodes/sec)"
    _required_commands = ("stockfish",)

    def get_version(self) -> str:
        try:
            completed = subprocess.run(
                ["stockfish"],
                check=False,
                input="uci\nquit\n",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=3,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return super().get_version()

        for line in (completed.stdout or "").splitlines():
            lower = line.lower()
            if lower.startswith("id name"):
                return line.split(" ", 2)[2].strip()
        return super().get_version()

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        threads = DEFAULT_STOCKFISH_THREADS
        limit_seconds = DEFAULT_STOCKFISH_LIMIT

        command = [
            "stockfish",
            "bench",
            "128",  # default hash MB
            str(threads),
            str(limit_seconds),
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            total_time_ms = self._parse_value(stdout, r"Total time \(ms\)\s*:\s*([\d.]+)")
            nodes_searched = self._parse_value(stdout, r"Nodes searched\s*:\s*([\d.]+)")
            nodes_per_second = self._parse_value(stdout, r"Nodes/second\s*:\s*([\d.]+)")

            metrics = BenchmarkMetrics(
                {
                    "total_time_ms": total_time_ms,
                    "nodes_searched": nodes_searched,
                    "nodes_per_sec": nodes_per_second,
                    "threads": threads,
                }
            )
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
            parameters=BenchmarkParameters({"threads": threads, "limit_secs": limit_seconds, "hash_mb": 128}),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    @staticmethod
    def _parse_value(text: str, pattern: str) -> float:
        match = re.search(pattern, text)
        if not match:
            raise ValueError("Unable to parse stockfish bench output")
        return float(match.group(1))

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        nps = result.metrics.get("nodes_per_sec")
        if nps is not None:
            return f"{nps / 1_000_000:.2f} Mnps"
        return ""
