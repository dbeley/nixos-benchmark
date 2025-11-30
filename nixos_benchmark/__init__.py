"""NixOS Benchmark Suite - A modular benchmarking framework for NixOS systems."""

from .cli import main
from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
    SystemInfo,
)


__version__ = "2.0.0"

__all__ = [
    "BenchmarkMetrics",
    "BenchmarkParameters",
    "BenchmarkReport",
    "BenchmarkResult",
    "SystemInfo",
    "main",
]
