"""Benchmark modules - all benchmark implementations and registry."""

from __future__ import annotations

from .base import BenchmarkBase
from .bonnie import BonnieBenchmark
from .clpeak import CLPeakBenchmark
from .cryptsetup import CryptsetupBenchmark
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
from .scoring import CPU_SCORE_RULES, GPU_SCORE_RULES, IO_SCORE_RULES, SCORE_RULES, ScoreRule, get_score_rule
from .sevenzip import SevenZipBenchmark
from .sqlite_mixed import SQLiteMixedBenchmark
from .sqlite_speedtest import SQLiteSpeedtestBenchmark
from .stockfish import StockfishBenchmark
from .stress_ng import StressNGBenchmark
from .stressapptest import StressAppTestBenchmark
from .sysbench_cpu import SysbenchCPUBenchmark
from .sysbench_memory import SysbenchMemoryBenchmark
from .tinymembench import TinyMemBenchBenchmark
from .types import BenchmarkType
from .vkmark import VKMarkBenchmark
from .wrk import WrkHTTPBenchmark
from .x264 import X264Benchmark
from .x265 import X265Benchmark
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
    VKMarkBenchmark(),
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
    SQLiteMixedBenchmark(),
    SQLiteSpeedtestBenchmark(),
    FFmpegBenchmark(),
    X264Benchmark(),
    X265Benchmark(),
    NetperfBenchmark(),
    WrkHTTPBenchmark(),
    GeekbenchBenchmark(),
    GeekbenchGPUBenchmark(),
    GeekbenchVulkanBenchmark(),
]

# Create a map from benchmark type to benchmark instance for easy lookup
BENCHMARK_MAP: dict[BenchmarkType, BenchmarkBase] = {bench.benchmark_type: bench for bench in ALL_BENCHMARKS}

# Preset definitions - directly list benchmark classes
PRESETS: dict[str, dict[str, object]] = {
    "balanced": {
        "description": "Quick mix of CPU and IO tests.",
        "benchmarks": (
            # CPU
            BenchmarkType.SEVENZIP,
            BenchmarkType.OPENSSL_SPEED,
            BenchmarkType.ZSTD,
            BenchmarkType.STRESS_NG,
            BenchmarkType.SYSBENCH_CPU,
            # MEMORY
            BenchmarkType.SYSBENCH_MEMORY,
            # IO
            BenchmarkType.FIO_SEQ,
            BenchmarkType.SQLITE_MIXED,
            # GPU
            BenchmarkType.GLMARK2,
            BenchmarkType.FURMARK_VK,
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
            BenchmarkType.UNIXBENCH,
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
            BenchmarkType.GLMARK2,
            BenchmarkType.FURMARK_VK,
        ),
    },
    "gpu": {
        "description": "GPU render benchmarks and compute tests.",
        "benchmarks": (
            BenchmarkType.GLMARK2,
            BenchmarkType.VKMARK,
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
    preset = PRESETS.get(preset_name, {})
    benchmarks = preset.get("benchmarks", ())
    if not isinstance(benchmarks, (list, tuple)):
        return ()
    return tuple(bench for bench in benchmarks if isinstance(bench, BenchmarkType))


CPU_BENCHMARK_TYPES = get_benchmark_types_for_preset("cpu")
GPU_BENCHMARK_TYPES = get_benchmark_types_for_preset("gpu")


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
    "CPU_BENCHMARK_TYPES",
    "CPU_SCORE_RULES",
    "GPU_BENCHMARK_TYPES",
    "GPU_SCORE_RULES",
    "IO_SCORE_RULES",
    "PRESETS",
    "SCORE_RULES",
    "BenchmarkBase",
    "BenchmarkType",
    "ScoreRule",
    "get_all_benchmarks",
    "get_benchmark_types_for_preset",
    "get_presets_for_benchmark",
    "get_score_rule",
]
