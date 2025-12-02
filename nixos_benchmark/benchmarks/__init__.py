"""Benchmark modules - all benchmark implementations and registry."""

from __future__ import annotations

from .base import BenchmarkBase
from .clpeak import CLPeakBenchmark
from .cryptsetup import CryptsetupBenchmark
from .ffmpeg import FFmpegBenchmark
from .fio import FIOBenchmark
from .glmark2 import GLMark2Benchmark
from .hashcat import HashcatBenchmark
from .ioping import IOPingBenchmark
from .john import JohnBenchmark
from .lz4 import LZ4Benchmark
from .netperf import NetperfBenchmark
from .openssl import OpenSSLBenchmark
from .pigz import PigzBenchmark
from .sevenzip import SevenZipBenchmark
from .sqlite_mixed import SQLiteMixedBenchmark
from .sqlite_speedtest import SQLiteSpeedtestBenchmark
from .stockfish import StockfishBenchmark
from .stress_ng import StressNGBenchmark
from .stressapptest import StressAppTestBenchmark
from .sysbench_cpu import SysbenchCPUBenchmark
from .sysbench_memory import SysbenchMemoryBenchmark
from .tinymembench import TinyMemBenchBenchmark
from .vkmark import VKMarkBenchmark
from .wrk import WrkHTTPBenchmark
from .x264 import X264Benchmark
from .x265 import X265Benchmark
from .zstd import ZstdBenchmark
from .types import BenchmarkType


# Registry of all benchmarks
ALL_BENCHMARKS = [
    OpenSSLBenchmark(),
    SevenZipBenchmark(),
    JohnBenchmark(),
    StockfishBenchmark(),
    StressNGBenchmark(),
    SysbenchCPUBenchmark(),
    SysbenchMemoryBenchmark(),
    StressAppTestBenchmark(),
    TinyMemBenchBenchmark(),
    FIOBenchmark(),
    IOPingBenchmark(),
    GLMark2Benchmark(),
    VKMarkBenchmark(),
    CLPeakBenchmark(),
    HashcatBenchmark(),
    LZ4Benchmark(),
    ZstdBenchmark(),
    PigzBenchmark(),
    CryptsetupBenchmark(),
    SQLiteMixedBenchmark(),
    SQLiteSpeedtestBenchmark(),
    FFmpegBenchmark(),
    X264Benchmark(),
    X265Benchmark(),
    NetperfBenchmark(),
    WrkHTTPBenchmark(),
]

# Create a map from benchmark type to benchmark instance for easy lookup
BENCHMARK_MAP: dict[BenchmarkType, BenchmarkBase] = {bench.benchmark_type: bench for bench in ALL_BENCHMARKS}

# Preset definitions - directly list benchmark classes
PRESETS: dict[str, dict[str, object]] = {
    "balanced": {
        "description": "Quick mix of CPU and IO tests.",
        "benchmarks": (
            BenchmarkType.OPENSSL_SPEED,
            BenchmarkType.SEVENZIP,
            BenchmarkType.JOHN,
            BenchmarkType.STRESS_NG,
            BenchmarkType.SYSBENCH_CPU,
            BenchmarkType.SYSBENCH_MEMORY,
            BenchmarkType.FIO_SEQ,
            BenchmarkType.SQLITE_MIXED,
        ),
    },
    "cpu": {
        "description": "CPU heavy synthetic workloads.",
        "benchmarks": (
            BenchmarkType.OPENSSL_SPEED,
            BenchmarkType.SEVENZIP,
            BenchmarkType.JOHN,
            BenchmarkType.STOCKFISH,
            BenchmarkType.STRESS_NG,
            BenchmarkType.SYSBENCH_CPU,
            BenchmarkType.ZSTD,
            BenchmarkType.PIGZ,
            BenchmarkType.X265,
            BenchmarkType.LZ4,
        ),
    },
    "io": {
        "description": "Disk and filesystem focused tests.",
        "benchmarks": (
            BenchmarkType.FIO_SEQ,
            BenchmarkType.IOPING,
            BenchmarkType.SQLITE_MIXED,
            BenchmarkType.SQLITE_SPEEDTEST,
            BenchmarkType.CRYPTSETUP,
        ),
    },
    "memory": {
        "description": "Memory bandwidth and latency tests.",
        "benchmarks": (
            BenchmarkType.SYSBENCH_MEMORY,
            BenchmarkType.TINYMEMBENCH,
            BenchmarkType.STRESSAPPTEST,
        ),
    },
    "compression": {
        "description": "Compression and decompression throughput.",
        "benchmarks": (
            BenchmarkType.SEVENZIP,
            BenchmarkType.ZSTD,
            BenchmarkType.PIGZ,
            BenchmarkType.LZ4,
        ),
    },
    "crypto": {
        "description": "Cryptography focused benchmarks.",
        "benchmarks": (
            BenchmarkType.OPENSSL_SPEED,
            BenchmarkType.CRYPTSETUP,
        ),
    },
    "database": {
        "description": "Database engines (SQLite only).",
        "benchmarks": (
            BenchmarkType.SQLITE_MIXED,
            BenchmarkType.SQLITE_SPEEDTEST,
        ),
    },
    "gpu-light": {
        "description": "Lightweight GPU render sanity checks.",
        "benchmarks": (
            BenchmarkType.GLMARK2,
            BenchmarkType.VKMARK,
        ),
    },
    "gpu": {
        "description": "GPU render benchmarks (glmark2 and vkmark).",
        "benchmarks": (
            BenchmarkType.GLMARK2,
            BenchmarkType.VKMARK,
            BenchmarkType.CLPEAK,
            BenchmarkType.HASHCAT_GPU,
        ),
    },
    "network": {
        "description": "Loopback network throughput (netperf TCP_STREAM).",
        "benchmarks": (
            BenchmarkType.NETPERF,
            BenchmarkType.WRK_HTTP,
        ),
    },
    "all": {
        "description": "Run every available benchmark.",
        "benchmarks": tuple(BENCHMARK_MAP),
    },
}


def get_presets_for_benchmark(benchmark: BenchmarkBase) -> tuple[str, ...]:
    """Compute which presets include a given benchmark."""
    presets_list: list[str] = []
    for preset_name, preset_config in PRESETS.items():
        # Skip "all" preset in loop since we always add it at the end
        if preset_name == "all":
            continue
        benchmarks = preset_config.get("benchmarks", [])
        if isinstance(benchmarks, (list, tuple)) and benchmark.benchmark_type in benchmarks:
            presets_list.append(preset_name)
    # "all" preset includes all benchmarks, so always add it
    presets_list.append("all")
    return tuple(sorted(presets_list))


def get_all_benchmarks():
    """Get all benchmark instances."""
    return ALL_BENCHMARKS


__all__ = [
    "ALL_BENCHMARKS",
    "BENCHMARK_MAP",
    "BenchmarkType",
    "PRESETS",
    "BenchmarkBase",
    "get_all_benchmarks",
    "get_presets_for_benchmark",
]
