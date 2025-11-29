"""Benchmark modules and registration."""
from __future__ import annotations

from typing import List

from .base import BenchmarkDefinition, PRESET_DEFINITIONS
from .compression import get_compression_benchmarks
from .cpu import get_cpu_benchmarks
from .crypto import get_crypto_benchmarks
from .database import get_database_benchmarks
from .gpu import get_gpu_benchmarks
from .io import get_io_benchmarks
from .media import get_media_benchmarks
from .memory import get_memory_benchmarks
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


__all__ = [
    "BenchmarkDefinition",
    "PRESET_DEFINITIONS",
    "get_all_benchmarks",
]
