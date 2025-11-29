"""CPU benchmarks."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
from typing import ClassVar, Dict, Tuple

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import command_exists, run_command
from .base import (
    BenchmarkBase,
    DEFAULT_OPENSSL_ALGORITHM,
    DEFAULT_OPENSSL_SECONDS,
    DEFAULT_STRESS_NG_METHOD,
    DEFAULT_STRESS_NG_SECONDS,
    DEFAULT_SYSBENCH_CPU_MAX_PRIME,
    DEFAULT_SYSBENCH_RUNTIME,
    DEFAULT_SYSBENCH_THREADS,
)


class OpenSSLBenchmark(BenchmarkBase):
    """OpenSSL speed benchmark."""

    key: ClassVar[str] = "openssl-speed"
    categories: ClassVar[Tuple[str, ...]] = ("cpu", "crypto")
    presets: ClassVar[Tuple[str, ...]] = ("balanced", "cpu", "crypto", "all")
    description: ClassVar[str] = "OpenSSL AES-256 encryption throughput."

    def __init__(
        self,
        seconds: int = DEFAULT_OPENSSL_SECONDS,
        algorithm: str = DEFAULT_OPENSSL_ALGORITHM,
    ):
        self.seconds = seconds
        self.algorithm = algorithm

    def get_required_commands(self) -> Tuple[str, ...]:
        return ("openssl",)

    def validate(self) -> Tuple[bool, str]:
        """Pre-flight check before execution."""
        for cmd in self.get_required_commands():
            if not command_exists(cmd):
                return False, f"Command {cmd!r} not found in PATH"
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Run the benchmark."""
        command = [
            "openssl",
            "speed",
            "-elapsed",
            "-seconds",
            str(self.seconds),
            self.algorithm,
        ]
        stdout, duration, returncode = run_command(command)

        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data = self._parse_output(stdout)
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name=self.key,
            status=status,
            categories=self.categories,
            presets=self.presets,
            metrics=metrics,
            parameters=BenchmarkParameters(
                {"seconds": self.seconds, "algorithm": self.algorithm}
            ),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def _parse_output(self, output: str) -> Dict[str, float]:
        """Parse openssl output."""
        pattern = rf"^{re.escape(self.algorithm)}\s+(.+)$"
        match = re.search(pattern, output, flags=re.MULTILINE)
        if not match:
            raise ValueError(f"Unable to find throughput table for {self.algorithm!r}")

        values_str = match.group(1).split()
        block_sizes = ["16B", "64B", "256B", "1KiB", "8KiB", "16KiB"]
        values = {}
        for size, token in zip(block_sizes, values_str):
            values[size] = float(token.rstrip("k"))

        values["max_kbytes_per_sec"] = max(values.values())
        return values

    def format_result(self, result: BenchmarkResult) -> str:
        """Format for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        throughput = result.metrics.get("max_kbytes_per_sec")
        if throughput is not None:
            return f"{throughput / 1024:.1f} MiB/s"
        return ""


class SevenZipBenchmark(BenchmarkBase):
    """7-Zip compression benchmark."""

    key: ClassVar[str] = "7zip-benchmark"
    categories: ClassVar[Tuple[str, ...]] = ("cpu", "compression")
    presets: ClassVar[Tuple[str, ...]] = ("balanced", "cpu", "compression", "all")
    description: ClassVar[str] = "7-Zip compression benchmark."

    def get_required_commands(self) -> Tuple[str, ...]:
        return ("7z",)

    def validate(self) -> Tuple[bool, str]:
        """Pre-flight check before execution."""
        for cmd in self.get_required_commands():
            if not command_exists(cmd):
                return False, f"Command {cmd!r} not found in PATH"
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Run the benchmark."""
        command = ["7z", "b"]
        stdout, duration, returncode = run_command(command)

        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data = self._parse_output(stdout)
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name=self.key,
            status=status,
            categories=self.categories,
            presets=self.presets,
            metrics=metrics,
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def _parse_output(self, output: str) -> Dict[str, float]:
        """Parse 7-Zip benchmark output."""
        totals_match = re.search(r"Tot:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", output)
        avg_match = re.search(
            r"Avr:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\|\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
            output,
        )
        result: Dict[str, float] = {}

        if totals_match:
            result["total_usage_pct"] = float(totals_match.group(1))
            result["total_ru"] = float(totals_match.group(2))
            result["total_rating_mips"] = float(totals_match.group(3))

        if avg_match:
            result["compress_usage_pct"] = float(avg_match.group(1))
            result["compress_ru_mips"] = float(avg_match.group(2))
            result["compress_rating_mips"] = float(avg_match.group(3))
            result["decompress_usage_pct"] = float(avg_match.group(4))
            result["decompress_ru_mips"] = float(avg_match.group(5))
            result["decompress_rating_mips"] = float(avg_match.group(6))

        if not result:
            raise ValueError("Unable to parse 7-Zip benchmark output")

        return result

    def format_result(self, result: BenchmarkResult) -> str:
        """Format for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        rating = result.metrics.get("total_rating_mips")
        if rating is not None:
            return f"{rating:.0f} MIPS"
        return ""


class StressNGBenchmark(BenchmarkBase):
    """stress-ng CPU stress test."""

    key: ClassVar[str] = "stress-ng"
    categories: ClassVar[Tuple[str, ...]] = ("cpu",)
    presets: ClassVar[Tuple[str, ...]] = ("balanced", "cpu", "all")
    description: ClassVar[str] = "stress-ng CPU stress test."

    def __init__(
        self,
        seconds: int = DEFAULT_STRESS_NG_SECONDS,
        method: str = DEFAULT_STRESS_NG_METHOD,
    ):
        self.seconds = seconds
        self.method = method

    def get_required_commands(self) -> Tuple[str, ...]:
        return ("stress-ng",)

    def validate(self) -> Tuple[bool, str]:
        """Pre-flight check before execution."""
        for cmd in self.get_required_commands():
            if not command_exists(cmd):
                return False, f"Command {cmd!r} not found in PATH"
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Run the benchmark."""
        command = [
            "stress-ng",
            "--cpu",
            "0",
            "--cpu-method",
            self.method,
            "--timeout",
            f"{self.seconds}s",
            "--metrics-brief",
        ]
        stdout, duration, returncode = run_command(command)

        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data = self._parse_output(stdout)
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name=self.key,
            status=status,
            categories=self.categories,
            presets=self.presets,
            metrics=metrics,
            parameters=BenchmarkParameters(
                {"seconds": self.seconds, "cpu_method": self.method}
            ),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def _parse_output(self, output: str) -> Dict[str, float]:
        """Parse stress-ng benchmark output."""
        pattern = re.compile(
            r"stress-ng:\s+\w+:\s+\[\d+\]\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
            r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
        )
        for line in output.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            stressor_name = match.group(1)
            if stressor_name == "stressor" or stressor_name.startswith("("):
                continue
            return {
                "stressor": stressor_name,
                "bogo_ops": float(match.group(2)),
                "real_time_secs": float(match.group(3)),
                "user_time_secs": float(match.group(4)),
                "system_time_secs": float(match.group(5)),
                "bogo_ops_per_sec_real": float(match.group(6)),
                "bogo_ops_per_sec_cpu": float(match.group(7)),
            }
        raise ValueError("Unable to parse stress-ng metrics (try increasing runtime)")

    def format_result(self, result: BenchmarkResult) -> str:
        """Format for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        ops = result.metrics.get("bogo_ops_per_sec_real")
        if ops is not None:
            return f"{ops:,.0f} bogo-ops/s"
        return ""


class SysbenchCPUBenchmark(BenchmarkBase):
    """sysbench CPU benchmark."""

    key: ClassVar[str] = "sysbench-cpu"
    categories: ClassVar[Tuple[str, ...]] = ("cpu",)
    presets: ClassVar[Tuple[str, ...]] = ("balanced", "cpu", "all")
    description: ClassVar[str] = "sysbench CPU benchmark."

    def __init__(
        self,
        threads: int = DEFAULT_SYSBENCH_THREADS,
        max_prime: int = DEFAULT_SYSBENCH_CPU_MAX_PRIME,
        runtime_secs: int = DEFAULT_SYSBENCH_RUNTIME,
    ):
        self.threads = threads
        self.max_prime = max_prime
        self.runtime_secs = runtime_secs

    def get_required_commands(self) -> Tuple[str, ...]:
        return ("sysbench",)

    def validate(self) -> Tuple[bool, str]:
        """Pre-flight check before execution."""
        for cmd in self.get_required_commands():
            if not command_exists(cmd):
                return False, f"Command {cmd!r} not found in PATH"
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Run the benchmark."""
        thread_count = self.threads if self.threads > 0 else (os.cpu_count() or 1)
        command = [
            "sysbench",
            "cpu",
            f"--cpu-max-prime={self.max_prime}",
            f"--threads={thread_count}",
            f"--time={self.runtime_secs}",
            "run",
        ]
        stdout, duration, returncode = run_command(command)

        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)

        try:
            metrics_data = self._parse_output(stdout)
            metrics_data["threads"] = thread_count
            metrics_data["cpu_max_prime"] = self.max_prime
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name=self.key,
            status=status,
            categories=self.categories,
            presets=self.presets,
            metrics=metrics,
            parameters=BenchmarkParameters(
                {
                    "threads": thread_count,
                    "cpu_max_prime": self.max_prime,
                    "runtime_secs": self.runtime_secs,
                }
            ),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )

    def _parse_output(self, output: str) -> Dict[str, float]:
        """Parse sysbench CPU benchmark output."""
        metrics: Dict[str, float] = {}
        events_per_sec = re.search(r"events per second:\s+([\d.]+)", output)
        total_time = re.search(r"total time:\s+([\d.]+)s", output)
        total_events = re.search(r"total number of events:\s+([\d.]+)", output)
        if events_per_sec:
            metrics["events_per_sec"] = float(events_per_sec.group(1))
        if total_time:
            metrics["total_time_secs"] = float(total_time.group(1))
        if total_events:
            metrics["total_events"] = float(total_events.group(1))
        if not metrics:
            raise ValueError("Unable to parse sysbench CPU output")
        return metrics

    def format_result(self, result: BenchmarkResult) -> str:
        """Format for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        events = result.metrics.get("events_per_sec")
        if events is not None:
            return f"{events:,.1f} events/s"
        return ""


# Legacy function wrappers for backward compatibility
def run_openssl(
    seconds: int = DEFAULT_OPENSSL_SECONDS,
    algorithm: str = DEFAULT_OPENSSL_ALGORITHM,
) -> BenchmarkResult:
    """Run OpenSSL speed benchmark."""
    benchmark = OpenSSLBenchmark(seconds, algorithm)
    return benchmark.execute(argparse.Namespace())


def run_7zip() -> BenchmarkResult:
    """Run 7-Zip benchmark."""
    benchmark = SevenZipBenchmark()
    return benchmark.execute(argparse.Namespace())


def run_stress_ng(
    seconds: int = DEFAULT_STRESS_NG_SECONDS,
    method: str = DEFAULT_STRESS_NG_METHOD,
) -> BenchmarkResult:
    """Run stress-ng CPU benchmark."""
    benchmark = StressNGBenchmark(seconds, method)
    return benchmark.execute(argparse.Namespace())


def run_sysbench_cpu(
    threads: int = DEFAULT_SYSBENCH_THREADS,
    max_prime: int = DEFAULT_SYSBENCH_CPU_MAX_PRIME,
    runtime_secs: int = DEFAULT_SYSBENCH_RUNTIME,
) -> BenchmarkResult:
    """Run sysbench CPU benchmark."""
    benchmark = SysbenchCPUBenchmark(threads, max_prime, runtime_secs)
    return benchmark.execute(argparse.Namespace())


# Benchmark definitions for registration
def get_cpu_benchmarks():
    """Get list of CPU benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
        BenchmarkDefinition(
            key="openssl-speed",
            categories=("cpu", "crypto"),
            presets=("balanced", "cpu", "crypto", "all"),
            description="OpenSSL AES-256 encryption throughput.",
            runner=lambda args: run_openssl(
                DEFAULT_OPENSSL_SECONDS, DEFAULT_OPENSSL_ALGORITHM
            ),
            requires=("openssl",),
        ),
        BenchmarkDefinition(
            key="7zip-benchmark",
            categories=("cpu", "compression"),
            presets=("balanced", "cpu", "compression", "all"),
            description="7-Zip compression benchmark.",
            runner=lambda args: run_7zip(),
            requires=("7z",),
        ),
        BenchmarkDefinition(
            key="stress-ng",
            categories=("cpu",),
            presets=("balanced", "cpu", "all"),
            description="stress-ng CPU stress test.",
            runner=lambda args: run_stress_ng(
                DEFAULT_STRESS_NG_SECONDS, DEFAULT_STRESS_NG_METHOD
            ),
            requires=("stress-ng",),
        ),
        BenchmarkDefinition(
            key="sysbench-cpu",
            categories=("cpu",),
            presets=("balanced", "cpu", "all"),
            description="sysbench CPU benchmark.",
            runner=lambda args: run_sysbench_cpu(
                DEFAULT_SYSBENCH_THREADS,
                DEFAULT_SYSBENCH_CPU_MAX_PRIME,
                DEFAULT_SYSBENCH_RUNTIME,
            ),
            requires=("sysbench",),
        ),
    ]


# Registry of benchmark classes
CPU_BENCHMARK_CLASSES = [
    OpenSSLBenchmark,
    SevenZipBenchmark,
    StressNGBenchmark,
    SysbenchCPUBenchmark,
]

