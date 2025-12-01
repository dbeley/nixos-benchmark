from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import find_free_tcp_port, run_command, wait_for_port
from .base import BenchmarkBase


# Default constants
DEFAULT_IPERF_DURATION = 3


class IPerf3Benchmark(BenchmarkBase):
    name = "iperf3-loopback"
    description = "iperf3 loopback throughput"
    _required_commands = ("iperf3",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        duration = DEFAULT_IPERF_DURATION
        port = find_free_tcp_port()
        server = subprocess.Popen(
            ["iperf3", "-s", "-1", "-p", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if not wait_for_port("127.0.0.1", port):
            server.kill()
            raise RuntimeError("iperf3 server failed to start")
        try:
            command = [
                "iperf3",
                "-c",
                "127.0.0.1",
                "-p",
                str(port),
                "-t",
                str(duration),
                "-J",
            ]
            stdout, client_duration, returncode = run_command(command)
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                raise subprocess.CalledProcessError(returncode, command, stdout)

            error_msg = data.get("error")
            if returncode != 0 or error_msg:
                message = error_msg or f"iperf3 returned exit code {returncode}"
                return BenchmarkResult(
                    name="iperf3-loopback",
                    status="error",
                    presets=(),
                    metrics=BenchmarkMetrics({}),
                    parameters=BenchmarkParameters({"duration_s": duration}),
                    duration_seconds=client_duration,
                    command=" ".join(command),
                    raw_output=stdout,
                    message=message,
                )
        finally:
            with contextlib.suppress(Exception):
                server.terminate()
                server.wait(timeout=5)

        end = data.get("end", {})
        sum_received = end.get("sum_received", {})
        bits_per_second = float(sum_received.get("bits_per_second", 0.0))
        metrics_data = {
            "throughput_mib_per_s": bits_per_second / (8 * 1024 * 1024),
            "retransmits": float(sum_received.get("retransmits", 0)),
            "duration_s": duration,
        }

        return BenchmarkResult(
            name="iperf3-loopback",
            status="ok",
            presets=(),
            metrics=BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data)),
            parameters=BenchmarkParameters({"duration_s": duration}),
            duration_seconds=client_duration,
            command=f"iperf3 -c 127.0.0.1 -p {port} -t {duration} -J",
            raw_output=stdout,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        bw = result.metrics.get("throughput_mib_per_s")
        if bw is not None:
            return f"{bw:.1f} MiB/s"
        return ""
