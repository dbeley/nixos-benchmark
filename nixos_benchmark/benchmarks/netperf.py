from __future__ import annotations

import argparse
import contextlib
import re
import subprocess
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import find_free_tcp_port, run_command, wait_for_port
from .base import BenchmarkBase
from .types import BenchmarkType


# Default constants
DEFAULT_NETPERF_DURATION = 3


class NetperfBenchmark(BenchmarkBase):
    benchmark_type = BenchmarkType.NETPERF
    description = "netperf TCP_STREAM loopback"
    _required_commands = ("netperf", "netserver")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        duration = DEFAULT_NETPERF_DURATION
        port = find_free_tcp_port()
        server = subprocess.Popen(
            ["netserver", "-p", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if not wait_for_port("127.0.0.1", port):
            server.kill()
            raise RuntimeError("netserver failed to start")
        try:
            stdout, client_duration, _ = run_command(
                [
                    "netperf",
                    "-H",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-l",
                    str(duration),
                    "-t",
                    "TCP_STREAM",
                ]
            )

            try:
                values = [float(token) for token in re.findall(r"([\d.]+)\s*$", stdout, flags=re.MULTILINE) if token]
                if not values:
                    raise ValueError("Unable to parse netperf throughput")
                throughput_mbps = values[-1]
                metrics_data = {
                    "throughput_mbps": throughput_mbps,
                    "duration_s": duration,
                }

                status = "ok"
                metrics = BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data))
                message = ""
            except ValueError as e:
                status = "error"
                metrics = BenchmarkMetrics({})
                message = str(e)
        finally:
            server.terminate()
            with contextlib.suppress(Exception):
                server.wait(timeout=5)

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"duration_s": duration}),
            duration_seconds=client_duration,
            command=f"netperf -H 127.0.0.1 -p {port} -l {duration} -t TCP_STREAM",
            raw_output=stdout,
            message=message,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        mbps = result.metrics.get("throughput_mbps")
        if mbps is not None:
            return f"{mbps:.1f} Mb/s"
        return ""
