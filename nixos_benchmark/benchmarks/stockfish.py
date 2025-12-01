from __future__ import annotations

import argparse
import re
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase


DEFAULT_STOCKFISH_THREADS = 0  # 0 = auto-detect
DEFAULT_STOCKFISH_LIMIT = 10  # seconds


class StockfishBenchmark(BenchmarkBase):
    name = "stockfish-bench"
    description = "Stockfish built-in bench (nodes/sec)"
    _required_commands = ("stockfish",)

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
            name=self.name,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"threads": threads, "limit_secs": limit_seconds, "hash_mb": 128}),
            duration_seconds=duration,
            command=" ".join(command),
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
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        nps = result.metrics.get("nodes_per_sec")
        if nps is not None:
            return f"{nps/1_000_000:.2f} Mnps"
        return ""
