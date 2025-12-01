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
from .iperf3 import IPerf3Benchmark
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
    IPerf3Benchmark(),
    NetperfBenchmark(),
    WrkHTTPBenchmark(),
]

# Create a map from benchmark name to benchmark instance for easy lookup
BENCHMARK_MAP = {bench.name: bench for bench in ALL_BENCHMARKS}

# Preset definitions - directly list benchmark classes
PRESETS: dict[str, dict[str, object]] = {
    "balanced": {
        "description": "Quick mix of CPU and IO tests.",
        "benchmarks": (
            BENCHMARK_MAP["openssl-speed"],
            BENCHMARK_MAP["7zip-benchmark"],
            BENCHMARK_MAP["john-benchmark"],
            BENCHMARK_MAP["stress-ng"],
            BENCHMARK_MAP["sysbench-cpu"],
            BENCHMARK_MAP["sysbench-memory"],
            BENCHMARK_MAP["fio-seq"],
            BENCHMARK_MAP["sqlite-mixed"],
        ),
    },
    "cpu": {
        "description": "CPU heavy synthetic workloads.",
        "benchmarks": (
            BENCHMARK_MAP["openssl-speed"],
            BENCHMARK_MAP["7zip-benchmark"],
            BENCHMARK_MAP["john-benchmark"],
            BENCHMARK_MAP["stockfish-bench"],
            BENCHMARK_MAP["stress-ng"],
            BENCHMARK_MAP["sysbench-cpu"],
            BENCHMARK_MAP["zstd-compress"],
            BENCHMARK_MAP["pigz-compress"],
            BENCHMARK_MAP["x265-encode"],
            BENCHMARK_MAP["lz4-benchmark"],
        ),
    },
    "io": {
        "description": "Disk and filesystem focused tests.",
        "benchmarks": (
            BENCHMARK_MAP["fio-seq"],
            BENCHMARK_MAP["ioping"],
            BENCHMARK_MAP["sqlite-mixed"],
            BENCHMARK_MAP["sqlite-speedtest"],
            BENCHMARK_MAP["cryptsetup-benchmark"],
        ),
    },
    "memory": {
        "description": "Memory bandwidth and latency tests.",
        "benchmarks": (
            BENCHMARK_MAP["sysbench-memory"],
            BENCHMARK_MAP["tinymembench"],
            BENCHMARK_MAP["stressapptest-memory"],
        ),
    },
    "compression": {
        "description": "Compression and decompression throughput.",
        "benchmarks": (
            BENCHMARK_MAP["7zip-benchmark"],
            BENCHMARK_MAP["zstd-compress"],
            BENCHMARK_MAP["pigz-compress"],
            BENCHMARK_MAP["lz4-benchmark"],
        ),
    },
    "crypto": {
        "description": "Cryptography focused benchmarks.",
        "benchmarks": (
            BENCHMARK_MAP["openssl-speed"],
            BENCHMARK_MAP["cryptsetup-benchmark"],
        ),
    },
    "database": {
        "description": "Database engines (SQLite only).",
        "benchmarks": (
            BENCHMARK_MAP["sqlite-mixed"],
            BENCHMARK_MAP["sqlite-speedtest"],
        ),
    },
    "gpu-light": {
        "description": "Lightweight GPU render sanity checks.",
        "benchmarks": (
            BENCHMARK_MAP["glmark2"],
            BENCHMARK_MAP["vkmark"],
        ),
    },
    "gpu": {
        "description": "GPU render benchmarks (glmark2 and vkmark).",
        "benchmarks": (
            BENCHMARK_MAP["glmark2"],
            BENCHMARK_MAP["vkmark"],
            BENCHMARK_MAP["clpeak"],
            BENCHMARK_MAP["hashcat-gpu"],
        ),
    },
    "network": {
        "description": "Loopback network throughput tests.",
        "benchmarks": (
            BENCHMARK_MAP["iperf3-loopback"],
            BENCHMARK_MAP["netperf"],
            BENCHMARK_MAP["wrk-http"],
        ),
    },
    "all": {
        "description": "Run every available benchmark.",
        "benchmarks": tuple(ALL_BENCHMARKS),
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
        if isinstance(benchmarks, (list, tuple)) and benchmark in benchmarks:
            presets_list.append(preset_name)
    # "all" preset includes all benchmarks, so always add it
    presets_list.append("all")
    return tuple(sorted(presets_list))


def get_all_benchmarks():
    """Get all benchmark instances."""
    return ALL_BENCHMARKS


__all__ = [
    "ALL_BENCHMARKS",
    "PRESETS",
    "BenchmarkBase",
    "get_all_benchmarks",
    "get_presets_for_benchmark",
]
