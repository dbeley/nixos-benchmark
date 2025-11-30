"""All benchmark classes and registry - pragmatic OOP implementation.

This module consolidates all benchmarks into a single file using a pragmatic approach:
- BenchmarkBase provides the OOP interface
- Individual benchmark classes wrap existing implementations
- Minimal code duplication while achieving architectural simplification
"""
from __future__ import annotations

import argparse
from abc import ABC
from typing import ClassVar, Tuple

from .benchmarks import cpu, memory, io, gpu, compression, crypto, database, media, network
from .benchmarks.base import BenchmarkDefinition
from .models import BenchmarkResult
from .output import describe_benchmark
from .utils import check_requirements


class BenchmarkBase(ABC):
    """Base class for all benchmarks - pragmatic OOP wrapper."""

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
        """Execute the benchmark - delegates to implementation function."""
        # Subclasses override this to call their specific implementation
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display - delegates to output module."""
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
        return cpu.run_openssl()


class SevenZipBenchmark(BenchmarkBase):
    key = "7zip-benchmark"
    categories = ("cpu", "compression")
    presets = ("balanced", "cpu", "compression", "all")
    description = "7-Zip compression benchmark"
    _required_commands = ("7z",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return cpu.run_7zip()


class StressNGBenchmark(BenchmarkBase):
    key = "stress-ng"
    categories = ("cpu",)
    presets = ("balanced", "cpu", "all")
    description = "stress-ng CPU stress test"
    _required_commands = ("stress-ng",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return cpu.run_stress_ng()


class SysbenchCPUBenchmark(BenchmarkBase):
    key = "sysbench-cpu"
    categories = ("cpu",)
    presets = ("balanced", "cpu", "all")
    description = "sysbench CPU benchmark"
    _required_commands = ("sysbench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return cpu.run_sysbench_cpu()


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
        return memory.run_sysbench_memory()


class TinyMemBenchBenchmark(BenchmarkBase):
    key = "tinymembench"
    categories = ("memory",)
    presets = ("memory", "all")
    description = "TinyMemBench memory throughput"
    _required_commands = ("tinymembench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return memory.run_tinymembench()


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
        return io.run_fio()


class IOPingBenchmark(BenchmarkBase):
    key = "ioping"
    categories = ("io",)
    presets = ("io", "all")
    description = "ioping latency probe"
    _required_commands = ("ioping",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return io.run_ioping()


class FSMarkBenchmark(BenchmarkBase):
    key = "fsmark"
    categories = ("io",)
    presets = ("io", "all")
    description = "fs_mark small file benchmark"
    _required_commands = ("fs_mark",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return io.run_fsmark()


class FileBenchBenchmark(BenchmarkBase):
    key = "filebench"
    categories = ("io",)
    presets = ("io", "all")
    description = "filebench micro workload"
    _required_commands = ("filebench",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return io.run_filebench()


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
        offscreen = args.glmark2_mode == "offscreen"
        return gpu.run_glmark2(offscreen=offscreen)


class VKMarkBenchmark(BenchmarkBase):
    key = "vkmark"
    categories = ("gpu",)
    presets = ("gpu-light", "gpu", "all")
    description = "vkmark Vulkan benchmark"
    _required_commands = ("vkmark",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return gpu.run_vkmark()


class CLPeakBenchmark(BenchmarkBase):
    key = "clpeak"
    categories = ("gpu", "compute")
    presets = ("gpu", "all")
    description = "OpenCL peak bandwidth/compute"
    _required_commands = ("clpeak",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return gpu.run_clpeak()


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
        return compression.run_zstd_benchmark()


class PigzBenchmark(BenchmarkBase):
    key = "pigz-compress"
    categories = ("cpu", "compression")
    presets = ("cpu", "compression", "all")
    description = "pigz compress/decompress throughput"
    _required_commands = ("pigz",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return compression.run_pigz_benchmark()


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
        return crypto.run_cryptsetup_benchmark()


# ==================
# Database Benchmarks
# ==================


class SQLiteMixedBenchmark(BenchmarkBase):
    key = "sqlite-mixed"
    categories = ("io", "database")
    presets = ("balanced", "io", "all")
    description = "SQLite insert/select mix"

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return database.run_sqlite_benchmark()


class SQLiteSpeedtestBenchmark(BenchmarkBase):
    key = "sqlite-speedtest"
    categories = ("io", "database")
    presets = ("database", "io", "all")
    description = "SQLite speedtest-style insert/select"

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return database.run_sqlite_speedtest()


class PGBenchBenchmark(BenchmarkBase):
    key = "pgbench"
    categories = ("database", "io")
    presets = ("database", "all")
    description = "PostgreSQL pgbench on local socket"
    _required_commands = ("initdb", "pgbench", "pg_ctl", "createdb")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return database.run_pgbench()


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
        return media.run_ffmpeg_benchmark()


class X264Benchmark(BenchmarkBase):
    key = "x264-encode"
    categories = ("media",)
    presets = ("all",)
    description = "x264 encoder benchmark"
    _required_commands = ("x264", "ffmpeg")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return media.run_x264_benchmark()


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
        return network.run_iperf3_loopback()


class NetperfBenchmark(BenchmarkBase):
    key = "netperf"
    categories = ("network",)
    presets = ("network", "all")
    description = "netperf TCP_STREAM loopback"
    _required_commands = ("netperf", "netserver")

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return network.run_netperf()


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
    FSMarkBenchmark(),
    FileBenchBenchmark(),
    GLMark2Benchmark(),
    VKMarkBenchmark(),
    CLPeakBenchmark(),
    ZstdBenchmark(),
    PigzBenchmark(),
    CryptsetupBenchmark(),
    SQLiteMixedBenchmark(),
    SQLiteSpeedtestBenchmark(),
    PGBenchBenchmark(),
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
        "description": "Database engines (SQLite and PostgreSQL)",
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
