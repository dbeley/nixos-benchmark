"""All benchmark classes and registry - complete OOP implementation.

This module consolidates all benchmarks using OOP principles with all logic encapsulated.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
from abc import ABC
from pathlib import Path
from typing import ClassVar, Dict, Sequence, Tuple

from .benchmarks.base import (
    DEFAULT_COMPRESS_SIZE_MB,
    DEFAULT_FFMPEG_CODEC,
    DEFAULT_FFMPEG_DURATION,
    DEFAULT_FFMPEG_RESOLUTION,
    DEFAULT_FIO_BLOCK_KB,
    DEFAULT_FIO_RUNTIME,
    DEFAULT_FIO_SIZE_MB,
    DEFAULT_GLMARK2_SIZE,
    DEFAULT_IOPING_COUNT,
    DEFAULT_IPERF_DURATION,
    DEFAULT_NETPERF_DURATION,
    DEFAULT_OPENSSL_ALGORITHM,
    DEFAULT_OPENSSL_SECONDS,
    DEFAULT_PIGZ_LEVEL,
    DEFAULT_SQLITE_ROWS,
    DEFAULT_SQLITE_SELECTS,
    DEFAULT_STRESS_NG_METHOD,
    DEFAULT_STRESS_NG_SECONDS,
    DEFAULT_SYSBENCH_CPU_MAX_PRIME,
    DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
    DEFAULT_SYSBENCH_MEMORY_OPERATION,
    DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
    DEFAULT_SYSBENCH_RUNTIME,
    DEFAULT_SYSBENCH_THREADS,
    DEFAULT_VKMARK_CMD,
    DEFAULT_X264_CRF,
    DEFAULT_X264_FRAMES,
    DEFAULT_X264_PRESET,
    DEFAULT_X264_RESOLUTION,
    DEFAULT_ZSTD_LEVEL,
)
from .models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from .output import describe_benchmark
from .utils import (
    check_requirements,
    find_free_tcp_port,
    parse_float,
    run_command,
    wait_for_port,
    write_temp_data_file,
)


class BenchmarkBase(ABC):
    """Base class for all benchmarks."""

    key: ClassVar[str]
    categories: ClassVar[Tuple[str, ...]]
    presets: ClassVar[Tuple[str, ...]]
    description: ClassVar[str]

    def validate(self, args: argparse.Namespace = None) -> Tuple[bool, str]:
        """Check if benchmark can run."""
        if hasattr(self, '_required_commands'):
            ok, reason = check_requirements(self._required_commands)
            if not ok:
                return ok, reason
        if hasattr(self, '_availability_check') and args is not None:
            return self._availability_check(args)
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Execute the benchmark."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        return describe_benchmark(result)


# ==================
# CPU Benchmarks
# ==================


class OpenSSLBenchmark(BenchmarkBase):
    key = "openssl-speed"
    categories = ("cpu", "crypto")
    presets = ("balanced", "cpu", "crypto", "all")
    description = "OpenSSL AES-256 encryption throughput"
    _required_commands = ("openssl",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        seconds = DEFAULT_OPENSSL_SECONDS
        algorithm = DEFAULT_OPENSSL_ALGORITHM
        command = ["openssl", "speed", "-elapsed", "-seconds", str(seconds), algorithm]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            pattern = rf"^{re.escape(algorithm)}\s+(.+)$"
            match = re.search(pattern, stdout, flags=re.MULTILINE)
            if not match:
                raise ValueError(f"Unable to find throughput table for {algorithm!r}")

            values_str = match.group(1).split()
            block_sizes = ["16B", "64B", "256B", "1KiB", "8KiB", "16KiB"]
            metrics_data = {}
            for size, token in zip(block_sizes, values_str):
                metrics_data[size] = float(token.rstrip("k"))
            metrics_data["max_kbytes_per_sec"] = max(metrics_data.values())
            
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="openssl-speed",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"seconds": seconds, "algorithm": algorithm}),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


class SevenZipBenchmark(BenchmarkBase):
    key = "7zip-benchmark"
    categories = ("cpu", "compression")
    presets = ("balanced", "cpu", "compression", "all")
    description = "7-Zip compression benchmark"
    _required_commands = ("7z",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["7z", "b"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            totals_match = re.search(r"Tot:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", stdout)
            avg_match = re.search(
                r"Avr:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\|\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
                stdout,
            )
            metrics_data: Dict[str, float] = {}

            if totals_match:
                metrics_data["total_usage_pct"] = float(totals_match.group(1))
                metrics_data["total_ru"] = float(totals_match.group(2))
                metrics_data["total_rating_mips"] = float(totals_match.group(3))

            if avg_match:
                metrics_data["compress_usage_pct"] = float(avg_match.group(1))
                metrics_data["compress_ru_mips"] = float(avg_match.group(2))
                metrics_data["compress_rating_mips"] = float(avg_match.group(3))
                metrics_data["decompress_usage_pct"] = float(avg_match.group(4))
                metrics_data["decompress_ru_mips"] = float(avg_match.group(5))
                metrics_data["decompress_rating_mips"] = float(avg_match.group(6))

            if not metrics_data:
                raise ValueError("Unable to parse 7-Zip benchmark output")
            
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="7zip-benchmark",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


class StressNGBenchmark(BenchmarkBase):
    key = "stress-ng"
    categories = ("cpu",)
    presets = ("balanced", "cpu", "all")
    description = "stress-ng CPU stress test"
    _required_commands = ("stress-ng",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        seconds = DEFAULT_STRESS_NG_SECONDS
        method = DEFAULT_STRESS_NG_METHOD
        command = [
            "stress-ng",
            "--cpu",
            "0",
            "--cpu-method",
            method,
            "--timeout",
            f"{seconds}s",
            "--metrics-brief",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            pattern = re.compile(
                r"stress-ng:\s+\w+:\s+\[\d+\]\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
                r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
            )
            metrics_data = {}
            for line in stdout.splitlines():
                match = pattern.search(line)
                if not match:
                    continue
                stressor_name = match.group(1)
                if stressor_name == "stressor" or stressor_name.startswith("("):
                    continue
                metrics_data = {
                    "stressor": stressor_name,
                    "bogo_ops": float(match.group(2)),
                    "real_time_secs": float(match.group(3)),
                    "user_time_secs": float(match.group(4)),
                    "system_time_secs": float(match.group(5)),
                    "bogo_ops_per_sec_real": float(match.group(6)),
                    "bogo_ops_per_sec_cpu": float(match.group(7)),
                }
                break
            
            if not metrics_data:
                raise ValueError("Unable to parse stress-ng metrics (try increasing runtime)")
            
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="stress-ng",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"seconds": seconds, "cpu_method": method}),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


class SysbenchCPUBenchmark(BenchmarkBase):
    key = "sysbench-cpu"
    categories = ("cpu",)
    presets = ("balanced", "cpu", "all")
    description = "sysbench CPU benchmark"
    _required_commands = ("sysbench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        threads = DEFAULT_SYSBENCH_THREADS
        max_prime = DEFAULT_SYSBENCH_CPU_MAX_PRIME
        runtime_secs = DEFAULT_SYSBENCH_RUNTIME
        thread_count = threads if threads > 0 else (os.cpu_count() or 1)
        
        command = [
            "sysbench",
            "cpu",
            f"--cpu-max-prime={max_prime}",
            f"--threads={thread_count}",
            f"--time={runtime_secs}",
            "run",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            metrics_data: Dict[str, float] = {}
            events_per_sec = re.search(r"events per second:\s+([\d.]+)", stdout)
            total_time = re.search(r"total time:\s+([\d.]+)s", stdout)
            total_events = re.search(r"total number of events:\s+([\d.]+)", stdout)
            if events_per_sec:
                metrics_data["events_per_sec"] = float(events_per_sec.group(1))
            if total_time:
                metrics_data["total_time_secs"] = float(total_time.group(1))
            if total_events:
                metrics_data["total_events"] = float(total_events.group(1))
            if not metrics_data:
                raise ValueError("Unable to parse sysbench CPU output")
            
            metrics_data["threads"] = thread_count
            metrics_data["cpu_max_prime"] = max_prime
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="sysbench-cpu",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({
                "threads": thread_count,
                "cpu_max_prime": max_prime,
                "runtime_secs": runtime_secs,
            }),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


# ==================
# Memory Benchmarks
# ==================


class SysbenchMemoryBenchmark(BenchmarkBase):
    key = "sysbench-memory"
    categories = ("memory",)
    presets = ("balanced", "memory", "all")
    description = "sysbench memory throughput"
    _required_commands = ("sysbench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        threads = DEFAULT_SYSBENCH_THREADS
        block_kb = DEFAULT_SYSBENCH_MEMORY_BLOCK_KB
        total_mb = DEFAULT_SYSBENCH_MEMORY_TOTAL_MB
        operation = DEFAULT_SYSBENCH_MEMORY_OPERATION
        thread_count = threads if threads > 0 else (os.cpu_count() or 1)
        
        command = [
            "sysbench",
            "memory",
            f"--memory-block-size={block_kb}K",
            f"--memory-total-size={total_mb}M",
            f"--memory-oper={operation}",
            f"--threads={thread_count}",
            "run",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            metrics_data: Dict[str, float] = {}
            operations = re.search(
                r"Total operations:\s+([\d.]+)\s+\(([\d.]+)\s+per second\)", stdout
            )
            throughput = re.search(
                r"([\d.]+)\s+MiB transferred\s+\(([\d.]+)\s+MiB/sec\)", stdout
            )
            total_time = re.search(r"total time:\s+([\d.]+)s", stdout)
            if operations:
                metrics_data["operations"] = float(operations.group(1))
                metrics_data["operations_per_sec"] = float(operations.group(2))
            if throughput:
                metrics_data["transferred_mib"] = float(throughput.group(1))
                metrics_data["throughput_mib_per_s"] = float(throughput.group(2))
            if total_time:
                metrics_data["total_time_secs"] = float(total_time.group(1))
            if not metrics_data:
                raise ValueError("Unable to parse sysbench memory output")
            
            metrics_data["threads"] = thread_count
            metrics_data["block_kb"] = block_kb
            metrics_data["total_mb"] = total_mb
            metrics_data["operation"] = operation
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="sysbench-memory",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({
                "threads": thread_count,
                "block_kb": block_kb,
                "total_mb": total_mb,
                "operation": operation,
            }),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


class TinyMemBenchBenchmark(BenchmarkBase):
    key = "tinymembench"
    categories = ("memory",)
    presets = ("memory", "all")
    description = "TinyMemBench memory throughput"
    _required_commands = ("tinymembench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["tinymembench"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            metrics_data: Dict[str, float] = {}
            for line in stdout.splitlines():
                match = re.match(r"\s*([A-Za-z0-9 +/_-]+?)\s*:?\s+([\d.,]+)\s+M(?:i)?B/s", line)
                if not match:
                    continue
                label = re.sub(r"\s+", "_", match.group(1).strip().lower())
                metrics_data[f"{label}_mb_per_s"] = parse_float(match.group(2))
            
            if not metrics_data:
                raise ValueError("Unable to parse tinymembench throughput")
            
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="tinymembench",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command="tinymembench",
            raw_output=stdout,
            message=message,
        )


# ==================
# I/O Benchmarks
# ==================


class FIOBenchmark(BenchmarkBase):
    key = "fio-seq"
    categories = ("io",)
    presets = ("balanced", "io", "all")
    description = "fio sequential read/write"
    _required_commands = ("fio",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        size_mb = DEFAULT_FIO_SIZE_MB
        runtime = DEFAULT_FIO_RUNTIME
        block_kb = DEFAULT_FIO_BLOCK_KB
        
        results_dir = Path("results")
        results_dir.mkdir(parents=True, exist_ok=True)
        data_file = results_dir / "fio-testfile.bin"

        job_text = (
            "[global]\n"
            "ioengine=sync\n"
            "direct=0\n"
            f"size={size_mb}m\n"
            f"runtime={runtime}\n"
            "time_based=1\n"
            "group_reporting=1\n"
            f"bs={block_kb}k\n"
            f"filename={data_file}\n"
            "\n"
            "[seqwrite]\n"
            "rw=write\n"
            "\n"
            "[seqread]\n"
            "rw=read\n"
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".fio") as tmp:
            job_path = Path(tmp.name)
            tmp.write(job_text.encode("utf-8"))

        try:
            stdout, duration, returncode = run_command(["fio", "--output-format=json", str(job_path)])
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, ["fio", "--output-format=json", str(job_path)], stdout)
            data = json.loads(stdout)
        finally:
            job_path.unlink(missing_ok=True)
            if data_file.exists():
                data_file.unlink()

        jobs = data.get("jobs", [])
        if not jobs:
            raise ValueError("fio output missing job data")

        aggregate = jobs[0]
        read_stats = aggregate.get("read", {})
        write_stats = aggregate.get("write", {})

        metrics_data = {
            "seqwrite_mib_per_s": float(write_stats.get("bw", 0.0)) / 1024,
            "seqwrite_iops": float(write_stats.get("iops", 0.0)),
            "seqread_mib_per_s": float(read_stats.get("bw", 0.0)) / 1024,
            "seqread_iops": float(read_stats.get("iops", 0.0)),
        }

        return BenchmarkResult(
            name="fio-seq",
            status="ok",
            categories=(),
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters({
                "size_mb": size_mb,
                "runtime_s": runtime,
                "block_kb": block_kb
            }),
            duration_seconds=duration,
            command=f"fio --output-format=json {job_path}",
            raw_output=stdout,
        )


class IOPingBenchmark(BenchmarkBase):
    key = "ioping"
    categories = ("io",)
    presets = ("io", "all")
    description = "ioping latency probe"
    _required_commands = ("ioping",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        count = DEFAULT_IOPING_COUNT
        command = ["ioping", "-c", str(count), "."]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            match = re.search(
                r"min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", stdout
            )
            if not match:
                raise ValueError("Unable to parse ioping summary")
            
            metrics_data = {
                "latency_min_ms": float(match.group(1)),
                "latency_avg_ms": float(match.group(2)),
                "latency_max_ms": float(match.group(3)),
                "latency_mdev_ms": float(match.group(4)),
                "requests": count,
            }
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="ioping",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({"count": count}),
            duration_seconds=duration,
            command=f"ioping -c {count} .",
            raw_output=stdout,
            message=message,
        )


# ==================
# GPU Benchmarks
# ==================


class GLMark2Benchmark(BenchmarkBase):
    key = "glmark2"
    categories = ("gpu",)
    presets = ("gpu-light", "gpu", "all")
    description = "glmark2 OpenGL benchmark"
    _required_commands = ("glmark2",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        size = DEFAULT_GLMARK2_SIZE
        offscreen = args.glmark2_mode == "offscreen"
        command = ["glmark2", "-s", size]
        if offscreen:
            command.append("--off-screen")
        
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            score_match = re.search(r"glmark2 Score:\s*(\d+)", stdout)
            if not score_match:
                raise ValueError("Unable to parse glmark2 score")
            
            metrics_data = {"score": float(score_match.group(1))}
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="glmark2",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({
                "size": size,
                "mode": "offscreen" if offscreen else "onscreen"
            }),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


class VKMarkBenchmark(BenchmarkBase):
    key = "vkmark"
    categories = ("gpu",)
    presets = ("gpu-light", "gpu", "all")
    description = "vkmark Vulkan benchmark"
    _required_commands = ("vkmark",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command_list = list(DEFAULT_VKMARK_CMD)
        stdout, duration, returncode = run_command(command_list)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command_list, stdout)
        
        try:
            scene_pattern = re.compile(
                r"(?P<scene>[\w-]+).*?(?P<frames>[\d.]+)\s+frames\s+in\s+[\d.]+\s+seconds\s*="
                r"\s*(?P<fps>[\d.]+)\s*FPS",
                flags=re.IGNORECASE,
            )
            fps_values = [float(match.group("fps")) for match in scene_pattern.finditer(stdout)]
            if not fps_values:
                fps_values = [
                    float(match)
                    for match in re.findall(r"FPS[:=]\s*([\d.]+)", stdout, flags=re.IGNORECASE)
                ]
            if not fps_values:
                raise ValueError("Unable to parse vkmark FPS results")
            
            metrics_data = {
                "fps_avg": sum(fps_values) / len(fps_values),
                "fps_min": min(fps_values),
                "fps_max": max(fps_values),
                "samples": len(fps_values),
            }
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="vkmark",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command=" ".join(command_list),
            raw_output=stdout,
            message=message,
        )


class CLPeakBenchmark(BenchmarkBase):
    key = "clpeak"
    categories = ("gpu", "compute")
    presets = ("gpu", "all")
    description = "OpenCL peak bandwidth/compute"
    _required_commands = ("clpeak",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["clpeak"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            if "no platforms found" in stdout.lower() or "clgetplatformids" in stdout.lower():
                raise ValueError("No OpenCL platforms found")
            
            metrics_data: Dict[str, float] = {}
            bandwidth_pattern = re.compile(
                r"Global memory bandwidth.*?:\s*([\d.]+)\s*GB/s", flags=re.IGNORECASE
            )
            compute_patterns = [
                (r"Single-precision.*?:\s*([\d.]+)\s*GFLOPS", "compute_sp_gflops"),
                (r"Double-precision.*?:\s*([\d.]+)\s*GFLOPS", "compute_dp_gflops"),
                (r"Integer.*?:\s*([\d.]+)\s*GIOPS", "compute_int_giops"),
            ]
            for line in stdout.splitlines():
                bw_match = bandwidth_pattern.search(line)
                if bw_match:
                    metrics_data["global_memory_bandwidth_gb_per_s"] = float(bw_match.group(1))
                for pattern, key in compute_patterns:
                    match = re.search(pattern, line, flags=re.IGNORECASE)
                    if match:
                        metrics_data[key] = float(match.group(1))
            
            if not metrics_data:
                raise ValueError("Unable to parse clpeak metrics")
            
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="clpeak",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command="clpeak",
            raw_output=stdout,
            message=message,
        )


# ==================
# Compression Benchmarks
# ==================


class ZstdBenchmark(BenchmarkBase):
    key = "zstd-compress"
    categories = ("cpu", "compression")
    presets = ("cpu", "compression", "all")
    description = "zstd compress/decompress throughput"
    _required_commands = ("zstd",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        level = DEFAULT_ZSTD_LEVEL
        size_mb = DEFAULT_COMPRESS_SIZE_MB
        data_path = write_temp_data_file(size_mb)
        compressed_path = data_path.with_suffix(data_path.suffix + ".zst")
        decompressed_path = data_path.with_suffix(".out")
        
        try:
            start = time.perf_counter()
            command = [
                "zstd",
                "-q",
                "-f",
                f"-{level}",
                str(data_path),
                "-o",
                str(compressed_path),
            ]
            stdout, _, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)
            compress_duration = time.perf_counter() - start

            data_path.unlink(missing_ok=True)
            start = time.perf_counter()
            command = [
                "zstd",
                "-d",
                "-q",
                "-f",
                str(compressed_path),
                "-o",
                str(decompressed_path),
            ]
            stdout, _, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)
            decompress_duration = time.perf_counter() - start
        finally:
            data_path.unlink(missing_ok=True)
            compressed_path.unlink(missing_ok=True)
            decompressed_path.unlink(missing_ok=True)

        metrics_data = {
            "compress_mb_per_s": size_mb / compress_duration if compress_duration else 0.0,
            "decompress_mb_per_s": size_mb / decompress_duration if decompress_duration else 0.0,
            "level": level,
            "size_mb": size_mb,
        }

        return BenchmarkResult(
            name="zstd-compress",
            status="ok",
            categories=(),
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters({"level": level, "size_mb": size_mb}),
            duration_seconds=compress_duration + decompress_duration,
            command=f"zstd -q -f -{level} {data_path} -o {compressed_path}",
            raw_output="",
        )


class PigzBenchmark(BenchmarkBase):
    key = "pigz-compress"
    categories = ("cpu", "compression")
    presets = ("cpu", "compression", "all")
    description = "pigz compress/decompress throughput"
    _required_commands = ("pigz",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        level = DEFAULT_PIGZ_LEVEL
        size_mb = DEFAULT_COMPRESS_SIZE_MB
        data_path = write_temp_data_file(size_mb)
        compressed_path = Path(f"{data_path}.gz")
        decompressed_path = compressed_path.with_suffix("")
        
        try:
            start = time.perf_counter()
            command = ["pigz", "-f", "-k", "-p", "0", f"-{level}", str(data_path)]
            stdout, _, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)
            compress_duration = time.perf_counter() - start

            data_path.unlink(missing_ok=True)
            start = time.perf_counter()
            command = ["pigz", "-d", "-f", "-k", str(compressed_path)]
            stdout, _, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)
            decompress_duration = time.perf_counter() - start
        finally:
            data_path.unlink(missing_ok=True)
            compressed_path.unlink(missing_ok=True)
            decompressed_path.unlink(missing_ok=True)

        metrics_data = {
            "compress_mb_per_s": size_mb / compress_duration if compress_duration else 0.0,
            "decompress_mb_per_s": size_mb / decompress_duration if decompress_duration else 0.0,
            "level": level,
            "size_mb": size_mb,
        }

        return BenchmarkResult(
            name="pigz-compress",
            status="ok",
            categories=(),
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters({"level": level, "size_mb": size_mb}),
            duration_seconds=compress_duration + decompress_duration,
            command=f"pigz -f -k -p 0 -{level} {data_path}",
            raw_output="",
        )


# ==================
# Crypto Benchmarks
# ==================


class CryptsetupBenchmark(BenchmarkBase):
    key = "cryptsetup-benchmark"
    categories = ("crypto", "io")
    presets = ("crypto", "io", "all")
    description = "cryptsetup cipher benchmark"
    _required_commands = ("cryptsetup",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = ["cryptsetup", "benchmark"]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            metrics_data: Dict[str, float] = {}
            pattern = re.compile(
                r"^(?P<cipher>[a-z0-9-]+)\s+(?P<keybits>\d+)b\s+(?P<enc>[\d.]+)\s+MiB/s\s+(?P<dec>[\d.]+)\s+MiB/s",
                flags=re.IGNORECASE,
            )
            for line in stdout.splitlines():
                match = pattern.search(line)
                if not match:
                    continue
                cipher = match.group("cipher")
                keybits = int(match.group("keybits"))
                enc = float(match.group("enc"))
                dec = float(match.group("dec"))
                metrics_data[f"{cipher}_{keybits}_enc_mib_per_s"] = enc
                metrics_data[f"{cipher}_{keybits}_dec_mib_per_s"] = dec
            
            if not metrics_data:
                raise ValueError("Unable to parse cryptsetup benchmark results")
            
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="cryptsetup-benchmark",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({}),
            duration_seconds=duration,
            command="cryptsetup benchmark",
            raw_output=stdout,
            message=message,
        )


# ==================
# Database Benchmarks
# ==================


class SQLiteMixedBenchmark(BenchmarkBase):
    key = "sqlite-mixed"
    categories = ("io", "database")
    presets = ("balanced", "io", "all")
    description = "SQLite insert/select mix"

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        row_count = DEFAULT_SQLITE_ROWS
        select_queries = DEFAULT_SQLITE_SELECTS
        
        tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp_db.close()
        db_path = Path(tmp_db.name)
        insert_start = time.perf_counter()
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA synchronous = OFF;")
            conn.execute("CREATE TABLE bench (id INTEGER PRIMARY KEY, value INTEGER);")
            with conn:
                conn.executemany(
                    "INSERT INTO bench(value) VALUES (?)",
                    ((i % 1000,) for i in range(row_count)),
                )
            insert_duration = time.perf_counter() - insert_start
            query_start = time.perf_counter()
            cursor = conn.cursor()
            for i in range(select_queries):
                cursor.execute("SELECT AVG(value) FROM bench WHERE value >= ?", (i % 1000,))
                cursor.fetchone()
            query_duration = time.perf_counter() - query_start
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

        metrics_data = {
            "insert_rows_per_s": row_count / insert_duration if insert_duration else 0.0,
            "selects_per_s": select_queries / query_duration if query_duration else 0.0,
            "row_count": row_count,
            "select_queries": select_queries,
        }
        total_duration = insert_duration + query_duration

        return BenchmarkResult(
            name="sqlite-mixed",
            status="ok",
            categories=(),
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters({
                "row_count": row_count,
                "select_queries": select_queries,
            }),
            duration_seconds=total_duration,
            command="python-sqlite3-inline",
            raw_output="",
        )


class SQLiteSpeedtestBenchmark(BenchmarkBase):
    key = "sqlite-speedtest"
    categories = ("io", "database")
    presets = ("database", "io", "all")
    description = "SQLite speedtest-style insert/select"

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        row_count = DEFAULT_SQLITE_ROWS
        select_queries = DEFAULT_SQLITE_SELECTS
        
        tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp_db.close()
        db_path = Path(tmp_db.name)
        conn = sqlite3.connect(db_path)
        insert_start = time.perf_counter()
        try:
            conn.execute("PRAGMA synchronous = OFF;")
            conn.execute("PRAGMA journal_mode = MEMORY;")
            conn.execute("CREATE TABLE bench (id INTEGER PRIMARY KEY, value INTEGER);")
            with conn:
                conn.executemany(
                    "INSERT INTO bench(value) VALUES (?)",
                    ((i % 1000,) for i in range(row_count)),
                )
            insert_duration = time.perf_counter() - insert_start
            conn.execute("CREATE INDEX idx_value ON bench(value);")
            query_start = time.perf_counter()
            cursor = conn.cursor()
            for i in range(select_queries):
                cursor.execute("SELECT COUNT(*) FROM bench WHERE value = ?", (i % 1000,))
                cursor.fetchone()
            query_duration = time.perf_counter() - query_start
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

        metrics_data = {
            "insert_rows_per_s": row_count / insert_duration if insert_duration else 0.0,
            "indexed_selects_per_s": select_queries / query_duration if query_duration else 0.0,
            "row_count": row_count,
            "select_queries": select_queries,
        }
        total_duration = insert_duration + query_duration

        return BenchmarkResult(
            name="sqlite-speedtest",
            status="ok",
            categories=(),
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=BenchmarkParameters({
                "row_count": row_count,
                "select_queries": select_queries
            }),
            duration_seconds=total_duration,
            command="python-sqlite3-speedtest",
            raw_output="",
        )


# ==================
# Media Benchmarks
# ==================


class FFmpegBenchmark(BenchmarkBase):
    key = "ffmpeg-transcode"
    categories = ("media",)
    presets = ("all",)
    description = "FFmpeg synthetic video transcode"
    _required_commands = ("ffmpeg",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        resolution = DEFAULT_FFMPEG_RESOLUTION
        duration_secs = DEFAULT_FFMPEG_DURATION
        codec = DEFAULT_FFMPEG_CODEC
        
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-stats",
            "-benchmark",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={resolution}:rate=30:duration={duration_secs}",
            "-c:v",
            codec,
            "-preset",
            "medium",
            "-f",
            "null",
            "-",
        ]
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            metrics_data: Dict[str, float] = {}
            fps_matches = re.findall(r"fps=\s*([\d.]+)", stdout)
            speed_matches = re.findall(r"speed=\s*([\d.]+)x", stdout)
            if fps_matches:
                metrics_data["reported_fps"] = float(fps_matches[-1])
            if speed_matches:
                metrics_data["speed_factor"] = float(speed_matches[-1])
            
            if metrics_data:
                total_frames = duration_secs * 30
                metrics_data["frames"] = total_frames
                metrics_data["codec"] = codec
            
            if not metrics_data:
                raise ValueError("Unable to parse FFmpeg output")
            
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)

        return BenchmarkResult(
            name="ffmpeg-transcode",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({
                "resolution": resolution,
                "duration": duration_secs,
                "codec": codec,
            }),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


class X264Benchmark(BenchmarkBase):
    key = "x264-encode"
    categories = ("media",)
    presets = ("all",)
    description = "x264 encoder benchmark"
    _required_commands = ("x264", "ffmpeg")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        resolution = DEFAULT_X264_RESOLUTION
        frames = DEFAULT_X264_FRAMES
        preset = DEFAULT_X264_PRESET
        crf = DEFAULT_X264_CRF
        
        # Generate test pattern
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".y4m")
        tmp.close()
        pattern_path = Path(tmp.name)
        
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={resolution}:rate=30",
            "-frames:v",
            str(frames),
            "-pix_fmt",
            "yuv420p",
            str(pattern_path),
        ]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            pattern_path.unlink(missing_ok=True)
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            command = [
                "x264",
                "--preset",
                preset,
                "--crf",
                str(crf),
                "--frames",
                str(frames),
                str(pattern_path),
                "-o",
                "/dev/null",
            ]
            stdout, duration, returncode = run_command(command)
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)
            
            try:
                # Parse encoded fps
                metrics_data: Dict[str, float] = {}
                fps_match = re.search(r"encoded .* frames, ([\d.]+) fps", stdout)
                if fps_match:
                    metrics_data["fps"] = float(fps_match.group(1))
                    metrics_data["preset"] = preset
                    metrics_data["crf"] = crf
                    metrics_data["resolution"] = resolution
                
                if not metrics_data:
                    raise ValueError("Unable to parse x264 output")
                
                status = "ok"
                metrics = BenchmarkMetrics(metrics_data)
                message = ""
            except ValueError as e:
                status = "error"
                metrics = BenchmarkMetrics({})
                message = str(e)
        finally:
            pattern_path.unlink(missing_ok=True)

        return BenchmarkResult(
            name="x264-encode",
            status=status,
            categories=(),
            presets=(),
            metrics=metrics,
            parameters=BenchmarkParameters({
                "resolution": resolution,
                "frames": frames,
                "preset": preset,
                "crf": crf,
            }),
            duration_seconds=duration,
            command=" ".join(command),
            raw_output=stdout,
            message=message,
        )


# ==================
# Network Benchmarks
# ==================


class IPerf3Benchmark(BenchmarkBase):
    key = "iperf3-loopback"
    categories = ("network",)
    presets = ("network", "all")
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


class NetperfBenchmark(BenchmarkBase):
    key = "netperf"
    categories = ("network",)
    presets = ("network", "all")
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
            stdout, client_duration = run_command([
                "netperf",
                "-H",
                "127.0.0.1",
                "-p",
                str(port),
                "-l",
                str(duration),
                "-t",
                "TCP_STREAM",
            ])
            
            try:
                values = [
                    float(token)
                    for token in re.findall(r"([\d.]+)\s*$", stdout, flags=re.MULTILINE)
                    if token
                ]
                if not values:
                    raise ValueError("Unable to parse netperf throughput")
                throughput_mbps = values[-1]
                metrics_data = {
                    "throughput_mbps": throughput_mbps,
                    "duration_s": duration,
                }
                
                status = "ok"
                metrics = BenchmarkMetrics(metrics_data)
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


# ==================
# Registry
# ==================

ALL_BENCHMARKS = [
    OpenSSLBenchmark(),
    SevenZipBenchmark(),
    StressNGBenchmark(),
    SysbenchCPUBenchmark(),
    SysbenchMemoryBenchmark(),
    TinyMemBenchBenchmark(),
    FIOBenchmark(),
    IOPingBenchmark(),
    GLMark2Benchmark(),
    VKMarkBenchmark(),
    CLPeakBenchmark(),
    ZstdBenchmark(),
    PigzBenchmark(),
    CryptsetupBenchmark(),
    SQLiteMixedBenchmark(),
    SQLiteSpeedtestBenchmark(),
    FFmpegBenchmark(),
    X264Benchmark(),
    IPerf3Benchmark(),
    NetperfBenchmark(),
]

# Preset definitions
PRESETS = {
    "balanced": {
        "description": "Quick mix of CPU and IO tests",
        "benchmarks": (
            "openssl-speed",
            "7zip-benchmark",
            "stress-ng",
            "sysbench-cpu",
            "sysbench-memory",
            "fio-seq",
            "sqlite-mixed",
        ),
    },
    "cpu": {"description": "CPU heavy synthetic workloads", "categories": ("cpu",)},
    "io": {"description": "Disk and filesystem focused tests", "categories": ("io",)},
    "memory": {
        "description": "Memory bandwidth and latency tests",
        "categories": ("memory",),
    },
    "compression": {
        "description": "Compression and decompression throughput",
        "categories": ("compression",),
    },
    "crypto": {
        "description": "Cryptography focused benchmarks",
        "categories": ("crypto",),
    },
    "database": {
        "description": "Database engines (SQLite)",
        "categories": ("database",),
    },
    "gpu-light": {
        "description": "Lightweight GPU render sanity checks",
        "benchmarks": ("glmark2", "vkmark"),
    },
    "gpu": {
        "description": "GPU render benchmarks (glmark2 and vkmark)",
        "categories": ("gpu",),
    },
    "network": {
        "description": "Loopback network throughput tests",
        "categories": ("network",),
    },
    "all": {"description": "Run every available benchmark", "all": True},
}


def get_all_benchmarks():
    """Get all benchmark instances."""
    return ALL_BENCHMARKS


__all__ = [
    "BenchmarkBase",
    "ALL_BENCHMARKS",
    "PRESETS",
    "get_all_benchmarks",
]
