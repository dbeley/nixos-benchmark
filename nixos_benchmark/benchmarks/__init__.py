"""Benchmark modules and registration."""
from __future__ import annotations

from typing import List, Type

from .base import BenchmarkBase, BenchmarkDefinition, PRESET_DEFINITIONS
from .compression import get_compression_benchmarks
from .cpu import (
    CPU_BENCHMARK_CLASSES,
    get_cpu_benchmarks,
    OpenSSLBenchmark,
    SevenZipBenchmark,
    StressNGBenchmark,
    SysbenchCPUBenchmark,
)
from .crypto import get_crypto_benchmarks
from .database import get_database_benchmarks
from .gpu import get_gpu_benchmarks
from .io import get_io_benchmarks
from .media import get_media_benchmarks
from .memory import (
    MEMORY_BENCHMARK_CLASSES,
    get_memory_benchmarks,
    SysbenchMemoryBenchmark,
)
from .network import get_network_benchmarks


def get_all_benchmarks() -> List[BenchmarkDefinition]:
    """Get all registered benchmark definitions."""
    benchmarks = []
    benchmarks.extend(get_cpu_benchmarks())
    benchmarks.extend(get_memory_benchmarks())
    benchmarks.extend(get_io_benchmarks())
    benchmarks.extend(get_gpu_benchmarks())
    benchmarks.extend(get_compression_benchmarks())
    benchmarks.extend(get_crypto_benchmarks())
    benchmarks.extend(get_database_benchmarks())
    benchmarks.extend(get_media_benchmarks())
    benchmarks.extend(get_network_benchmarks())
    return benchmarks


def get_all_benchmark_classes() -> List[Type[BenchmarkBase]]:
    """Get all registered benchmark classes."""
    classes: List[Type[BenchmarkBase]] = []
    classes.extend(CPU_BENCHMARK_CLASSES)
    classes.extend(MEMORY_BENCHMARK_CLASSES)
    # Other modules will be converted incrementally
    return classes


def initialize_benchmark_formatters() -> None:
    """Initialize benchmark formatters for output.py."""
    from ..output import register_benchmark_formatter
    
    # Register CPU benchmark formatters
    register_benchmark_formatter(OpenSSLBenchmark())
    register_benchmark_formatter(SevenZipBenchmark())
    register_benchmark_formatter(StressNGBenchmark())
    register_benchmark_formatter(SysbenchCPUBenchmark())
    
    # Register Memory benchmark formatters
    register_benchmark_formatter(SysbenchMemoryBenchmark())


__all__ = [
    "BenchmarkBase",
    "BenchmarkDefinition",
    "PRESET_DEFINITIONS",
    "get_all_benchmarks",
    "get_all_benchmark_classes",
    "initialize_benchmark_formatters",
]



