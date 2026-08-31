"""Stockfish chess engine benchmark."""

from __future__ import annotations

import argparse
import os
import re
import subprocess

from ..models import BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_STOCKFISH_LIMIT = 20  # fixed depth for the built-in bench


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

    @staticmethod
    def _parse_stockfish(stdout: str) -> dict[str, float | str | int]:
        total_time_ms = StockfishBenchmark._parse_value(stdout, r"Total time \(ms\)\s*:\s*([\d.]+)")
        nodes_searched = StockfishBenchmark._parse_value(stdout, r"Nodes searched\s*:\s*([\d.]+)")
        nodes_per_second = StockfishBenchmark._parse_value(stdout, r"Nodes/second\s*:\s*([\d.]+)")
        return {
            "total_time_ms": total_time_ms,
            "nodes_searched": nodes_searched,
            "nodes_per_sec": nodes_per_second,
        }

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        threads = os.cpu_count() or 1
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

        status, metrics, message = self.parse_metrics(lambda: self._parse_stockfish(stdout))
        if status == "ok":
            metrics.data["threads"] = threads

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
