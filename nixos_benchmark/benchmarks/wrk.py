from __future__ import annotations

import argparse
import contextlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import find_free_tcp_port, run_command, wait_for_port
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_WRK_DURATION = 5
DEFAULT_WRK_THREADS = 2
DEFAULT_WRK_CONNECTIONS = 16


def _parse_number_with_suffix(token: str) -> float:
    """Parse numbers that may carry k/M/G suffixes."""
    match = re.match(r"([\d.]+)\s*([kKmMgG]?)", token)
    if not match:
        raise ValueError(f"Unable to parse numeric value from {token!r}")
    base = float(match.group(1))
    suffix = match.group(2).lower()
    multiplier = {"": 1.0, "k": 1_000.0, "m": 1_000_000.0, "g": 1_000_000_000.0}
    return base * multiplier.get(suffix, 1.0)


def _parse_transfer_value(token: str) -> float:
    """Parse wrk transfer/sec values (KB, MB, GB) into MiB/s."""
    match = re.match(r"([\d.]+)\s*([KMG])B", token)
    if not match:
        raise ValueError(f"Unable to parse transfer value from {token!r}")
    value = float(match.group(1))
    unit = match.group(2)
    scale = {"K": 1 / 1024, "M": 1.0, "G": 1024.0}
    return value * scale[unit]


class WrkHTTPBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.WRK_HTTP
    description = "wrk HTTP load against a local python server"
    _required_commands = ("wrk",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        duration = DEFAULT_WRK_DURATION
        threads = DEFAULT_WRK_THREADS
        connections = DEFAULT_WRK_CONNECTIONS
        port = find_free_tcp_port()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "index.html").write_text("benchmark\n", encoding="utf-8")

            server = subprocess.Popen(
                [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                cwd=tmp_path,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )

            if not wait_for_port("127.0.0.1", port):
                server.kill()
                raise RuntimeError("HTTP server failed to start")

            try:
                command = [
                    "wrk",
                    "-t",
                    str(threads),
                    "-c",
                    str(connections),
                    "-d",
                    f"{duration}s",
                    f"http://127.0.0.1:{port}/",
                ]
                stdout, wrk_duration, returncode = run_command(command)
                if returncode != 0:
                    raise subprocess.CalledProcessError(returncode, command, stdout)
            finally:
                with contextlib.suppress(Exception):
                    server.terminate()
                with contextlib.suppress(Exception):
                    server.wait(timeout=5)

        try:
            reqs_match = re.search(r"Requests/sec:\s+([\d.kKmMgG]+)", stdout)
            xfer_match = re.search(r"Transfer/sec:\s+([\d.]+[KMG]B)", stdout)
            latency_match = re.search(r"Latency\s+([\d.]+)ms", stdout)

            if not reqs_match or not xfer_match or not latency_match:
                raise ValueError("Unable to parse wrk output")

            requests_per_sec = _parse_number_with_suffix(reqs_match.group(1))
            transfer_mib_per_s = _parse_transfer_value(xfer_match.group(1))
            avg_latency_ms = float(latency_match.group(1))

            metrics = BenchmarkMetrics(
                {
                    "requests_per_sec": requests_per_sec,
                    "transfer_mib_per_s": transfer_mib_per_s,
                    "avg_latency_ms": avg_latency_ms,
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
            parameters=BenchmarkParameters(
                {
                    "duration_s": duration,
                    "threads": threads,
                    "connections": connections,
                }
            ),
            duration_seconds=wrk_duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        rps = result.metrics.get("requests_per_sec")
        latency = result.metrics.get("avg_latency_ms")
        if rps is not None and latency is not None:
            return f"{rps:,.0f} req/s @ {latency:.1f} ms"
        return ""
