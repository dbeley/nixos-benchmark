"""Benchmark modules - all benchmark implementations and registry."""

from __future__ import annotations

from .base import PRESETS, BenchmarkBase
from .clpeak import CLPeakBenchmark
from .cryptsetup import CryptsetupBenchmark
from .ffmpeg import FFmpegBenchmark
from .fio import FIOBenchmark
from .glmark2 import GLMark2Benchmark
from .ioping import IOPingBenchmark
from .iperf3 import IPerf3Benchmark
from .netperf import NetperfBenchmark
from .openssl import OpenSSLBenchmark
from .pigz import PigzBenchmark
from .sevenzip import SevenZipBenchmark
from .sqlite_mixed import SQLiteMixedBenchmark
from .sqlite_speedtest import SQLiteSpeedtestBenchmark
from .stress_ng import StressNGBenchmark
from .sysbench_cpu import SysbenchCPUBenchmark
from .sysbench_memory import SysbenchMemoryBenchmark
from .tinymembench import TinyMemBenchBenchmark
from .vkmark import VKMarkBenchmark
from .x264 import X264Benchmark
from .zstd import ZstdBenchmark


# Registry of all benchmarks
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


def get_all_benchmarks():
    """Get all benchmark instances."""
    return ALL_BENCHMARKS


__all__ = [
    "ALL_BENCHMARKS",
    "PRESETS",
    "BenchmarkBase",
    "get_all_benchmarks",
]
