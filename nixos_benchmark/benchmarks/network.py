"""Network benchmarks."""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_netperf_output
from ..utils import find_free_tcp_port, run_command, wait_for_port
from .base import DEFAULT_IPERF_DURATION, DEFAULT_NETPERF_DURATION


def run_iperf3_loopback(duration: int = DEFAULT_IPERF_DURATION) -> BenchmarkResult:
    """Run iperf3 loopback throughput test."""
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
        stdout, client_duration = run_command(
            ["iperf3", "-c", "127.0.0.1", "-p", str(port), "-t", str(duration), "-J"]
        )
        data = json.loads(stdout)
    finally:
        with contextlib.suppress(Exception):
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
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"duration_s": duration}),
        duration_seconds=client_duration,
        command=f"iperf3 -c 127.0.0.1 -p {port} -t {duration} -J",
        raw_output=stdout,
    )


def run_netperf(duration: int = DEFAULT_NETPERF_DURATION) -> BenchmarkResult:
    """Run netperf TCP_STREAM loopback test."""
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
        stdout, client_duration = run_command(
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
            metrics_data = parse_netperf_output(stdout)
            metrics_data["duration_s"] = duration
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            # Preserve output even when parsing fails
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)
    finally:
        server.terminate()
        with contextlib.suppress(Exception):
            server.wait(timeout=5)

    return BenchmarkResult(
        name="netperf",
        status=status,
        categories=(),
        presets=(),
        metrics=metrics,
        parameters=BenchmarkParameters({"duration_s": duration}),
        duration_seconds=client_duration,
        command=f"netperf -H 127.0.0.1 -p {port} -l {duration} -t TCP_STREAM",
        raw_output=stdout,
        message=message,
    )


# Benchmark definitions for registration
def get_network_benchmarks():
    """Get list of network benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="iperf3-loopback",
            categories=("network",),
            presets=("network", "all"),
            description="iperf3 loopback throughput.",
            runner=lambda args: run_iperf3_loopback(DEFAULT_IPERF_DURATION),
            requires=("iperf3",),
        ),
        BenchmarkDefinition(
            key="netperf",
            categories=("network",),
            presets=("network", "all"),
            description="netperf TCP_STREAM loopback.",
            runner=lambda args: run_netperf(DEFAULT_NETPERF_DURATION),
            requires=("netperf", "netserver"),
        ),
    ]
