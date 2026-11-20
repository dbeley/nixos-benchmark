"""Benchmark modules - all benchmark implementations and registry."""

from __future__ import annotations

from typing import TypedDict

from .base import BenchmarkBase
from .bonnie import BonnieBenchmark
from .clpeak import CLPeakBenchmark
from .cryptsetup import CryptsetupBenchmark
from .encoder import EncoderBenchmark
from .ffmpeg import FFmpegBenchmark
from .fio import FIOBenchmark
from .furmark import FurmarkBenchmark
from .geekbench import GeekbenchBenchmark, GeekbenchGPUBenchmark, GeekbenchVulkanBenchmark
from .glmark2 import GLMark2Benchmark
from .hashcat import HashcatBenchmark
from .ioping import IOPingBenchmark
from .iozone import IozoneBenchmark
from .john import JohnBenchmark
from .lz4 import LZ4Benchmark
from .netperf import NetperfBenchmark
from .openssl import OpenSSLBenchmark
from .pigz import PigzBenchmark
from .scoring import (
    CPU_SCORE_RULES,
    GPU_SCORE_RULES,
    IO_SCORE_RULES,
    MEMORY_SCORE_RULES,
    NETWORK_SCORE_RULES,
    SCORE_RULES,
    ScoreRule,
    get_score_rule,
)
from .sevenzip import SevenZipBenchmark
from .sqlite import SQLiteBenchmark
from .stockfish import StockfishBenchmark
from .stress_ng import StressNGBenchmark
from .stressapptest import StressAppTestBenchmark
from .sysbench_cpu import SysbenchCPUBenchmark
from .sysbench_memory import SysbenchMemoryBenchmark
from .tinymembench import TinyMemBenchBenchmark
from .types import BenchmarkType
from .wrk import WrkHTTPBenchmark
from .zstd import ZstdBenchmark


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
    IozoneBenchmark(),
    BonnieBenchmark(),
    IOPingBenchmark(),
    GLMark2Benchmark(),
    FurmarkBenchmark("furmark-gl", BenchmarkType.FURMARK_GL, "FurMark OpenGL"),
    FurmarkBenchmark("furmark-vk", BenchmarkType.FURMARK_VK, "FurMark Vulkan"),
    FurmarkBenchmark("furmark-knot-gl", BenchmarkType.FURMARK_KNOT_GL, "FurMark knot OpenGL"),
    FurmarkBenchmark("furmark-knot-vk", BenchmarkType.FURMARK_KNOT_VK, "FurMark knot Vulkan"),
    CLPeakBenchmark(),
    HashcatBenchmark(),
    LZ4Benchmark(),
    ZstdBenchmark(),
    PigzBenchmark(),
    CryptsetupBenchmark(),
    SQLiteBenchmark(
        BenchmarkType.SQLITE_MIXED,
        "SQLite insert/select mix",
        indexed=False,
        select_key="selects_per_s",
    ),
    SQLiteBenchmark(
        BenchmarkType.SQLITE_SPEEDTEST,
        "SQLite speedtest-style insert/select",
        indexed=True,
        select_key="indexed_selects_per_s",
    ),
    FFmpegBenchmark(),
    EncoderBenchmark(BenchmarkType.X264, "x264 encoder benchmark", "x264"),
    EncoderBenchmark(BenchmarkType.X265, "x265 encoder benchmark", "x265"),
    NetperfBenchmark(),
    WrkHTTPBenchmark(),
    GeekbenchBenchmark(),
    GeekbenchGPUBenchmark(),
    GeekbenchVulkanBenchmark(),
]

# Create a map from benchmark type to benchmark instance for easy lookup
BENCHMARK_MAP: dict[BenchmarkType, BenchmarkBase] = {bench.benchmark_type: bench for bench in ALL_BENCHMARKS}


class Preset(TypedDict):
    """A named collection of benchmarks plus its one-line description."""

    description: str
    benchmarks: tuple[BenchmarkType, ...]


# Preset definitions - directly list benchmark classes
PRESETS: dict[str, Preset] = {
    "fast": {
        "description": "Every short-running benchmark, for lots of results quickly.",
        "benchmarks": (
            # CPU
            BenchmarkType.OPENSSL_SPEED,
            BenchmarkType.JOHN,
            BenchmarkType.STRESS_NG,
            BenchmarkType.SYSBENCH_CPU,
            # MEMORY
            BenchmarkType.SYSBENCH_MEMORY,
            BenchmarkType.STRESSAPPTEST,
            # IO / DATABASE
            BenchmarkType.FIO_SEQ,
            BenchmarkType.IOZONE,
            BenchmarkType.SQLITE_SPEEDTEST,
            # MEDIA
            BenchmarkType.FFMPEG_TRANSCODE,
            BenchmarkType.X264,
            BenchmarkType.X265,
            # COMPRESSION
            BenchmarkType.LZ4,
            BenchmarkType.ZSTD,
            BenchmarkType.PIGZ,
            # NETWORK
            BenchmarkType.NETPERF,
            BenchmarkType.WRK_HTTP,
        ),
    },
    "balanced": {
        "description": "Quick mix of CPU and IO tests.",
        "benchmarks": (
            # CPU
            BenchmarkType.SEVENZIP,
            BenchmarkType.OPENSSL_SPEED,
            BenchmarkType.ZSTD,
            BenchmarkType.STRESS_NG,
            BenchmarkType.SYSBENCH_CPU,
            BenchmarkType.GEEKBENCH,
            # MEMORY
            BenchmarkType.SYSBENCH_MEMORY,
            # IO
            BenchmarkType.FIO_SEQ,
            BenchmarkType.SQLITE_MIXED,
            # GPU
            BenchmarkType.FURMARK_VK,
            BenchmarkType.GEEKBENCH_GPU_VULKAN,
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
            BenchmarkType.GEEKBENCH,
            BenchmarkType.ZSTD,
            BenchmarkType.PIGZ,
            BenchmarkType.X264,
            BenchmarkType.X265,
            BenchmarkType.LZ4,
            BenchmarkType.FFMPEG_TRANSCODE,
        ),
    },
    "io": {
        "description": "Disk and filesystem focused tests.",
        "benchmarks": (
            BenchmarkType.FIO_SEQ,
            BenchmarkType.IOPING,
            BenchmarkType.IOZONE,
            BenchmarkType.BONNIE,
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
        "description": "Quick GPU tests.",
        "benchmarks": (
            BenchmarkType.FURMARK_VK,
            BenchmarkType.GEEKBENCH_GPU_VULKAN,
        ),
    },
    "gpu": {
        "description": "GPU render benchmarks and compute tests.",
        "benchmarks": (
            BenchmarkType.GLMARK2,
            BenchmarkType.FURMARK_GL,
            BenchmarkType.FURMARK_VK,
            BenchmarkType.FURMARK_KNOT_GL,
            BenchmarkType.FURMARK_KNOT_VK,
            BenchmarkType.CLPEAK,
            BenchmarkType.HASHCAT_GPU,
            BenchmarkType.GEEKBENCH_GPU,
            BenchmarkType.GEEKBENCH_GPU_VULKAN,
        ),
    },
    "network": {
        "description": "Loopback network throughput.",
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


def get_benchmark_types_for_preset(preset_name: str) -> tuple[BenchmarkType, ...]:
    """Return the benchmark types associated with a preset."""
    preset = PRESETS.get(preset_name)
    return preset["benchmarks"] if preset else ()


def get_presets_for_benchmark(benchmark: BenchmarkBase) -> tuple[str, ...]:
    """Compute which presets include a given benchmark."""
    presets_list: list[str] = []
    for preset_name, preset in PRESETS.items():
        # Skip "all" preset in loop since we always add it at the end
        if preset_name == "all":
            continue
        if benchmark.benchmark_type in preset["benchmarks"]:
            presets_list.append(preset_name)
    # "all" preset includes all benchmarks, so always add it
    presets_list.append("all")
    return tuple(sorted(presets_list))


__all__ = [
    "ALL_BENCHMARKS",
    "BENCHMARK_MAP",
    "CPU_SCORE_RULES",
    "GPU_SCORE_RULES",
    "IO_SCORE_RULES",
    "MEMORY_SCORE_RULES",
    "NETWORK_SCORE_RULES",
    "PRESETS",
    "SCORE_RULES",
    "BenchmarkBase",
    "BenchmarkType",
    "ScoreRule",
    "get_benchmark_types_for_preset",
    "get_presets_for_benchmark",
    "get_score_rule",
]
