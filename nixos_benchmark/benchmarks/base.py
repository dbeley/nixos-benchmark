"""Base definitions for benchmarks and presets."""

from __future__ import annotations

import argparse
from abc import ABC
from collections.abc import Callable
from typing import ClassVar, cast

from ..models import BenchmarkResult
from ..utils import check_requirements


# Default constants for CPU benchmarks
DEFAULT_STRESS_NG_SECONDS = 5
DEFAULT_STRESS_NG_METHOD = "fft"
DEFAULT_SYSBENCH_CPU_MAX_PRIME = 20000
DEFAULT_SYSBENCH_RUNTIME = 5
DEFAULT_SYSBENCH_THREADS = 0
DEFAULT_OPENSSL_SECONDS = 3
DEFAULT_OPENSSL_ALGORITHM = "aes-256-cbc"

# Default constants for memory benchmarks
DEFAULT_SYSBENCH_MEMORY_BLOCK_KB = 1024
DEFAULT_SYSBENCH_MEMORY_TOTAL_MB = 512
DEFAULT_SYSBENCH_MEMORY_OPERATION = "read"

# Default constants for I/O benchmarks
DEFAULT_FIO_SIZE_MB = 64
DEFAULT_FIO_RUNTIME = 5
DEFAULT_FIO_BLOCK_KB = 1024
DEFAULT_IOPING_COUNT = 5

# Default constants for GPU benchmarks
DEFAULT_GLMARK2_SIZE = "1920x1080"
DEFAULT_VKMARK_CMD = ("vkmark",)

# Default constants for compression benchmarks
DEFAULT_ZSTD_LEVEL = 5
DEFAULT_PIGZ_LEVEL = 3
DEFAULT_COMPRESS_SIZE_MB = 32

# Default constants for database benchmarks
DEFAULT_SQLITE_ROWS = 50_000
DEFAULT_SQLITE_SELECTS = 1_000

# Default constants for media benchmarks
DEFAULT_FFMPEG_RESOLUTION = "1280x720"
DEFAULT_FFMPEG_DURATION = 5
DEFAULT_FFMPEG_CODEC = "libx264"
DEFAULT_X264_RESOLUTION = "1280x720"
DEFAULT_X264_FRAMES = 240
DEFAULT_X264_PRESET = "medium"
DEFAULT_X264_CRF = 23

# Default constants for network benchmarks
DEFAULT_IPERF_DURATION = 3
DEFAULT_NETPERF_DURATION = 3


class BenchmarkBase(ABC):
    """Base class for all benchmarks."""

    key: ClassVar[str]
    categories: ClassVar[tuple[str, ...]]
    presets: ClassVar[tuple[str, ...]]
    description: ClassVar[str]

    def validate(self, args: argparse.Namespace | None = None) -> tuple[bool, str]:
        """Check if benchmark can run."""
        if hasattr(self, "_required_commands"):
            ok, reason = check_requirements(self._required_commands)
            if not ok:
                return ok, reason
        if hasattr(self, "_availability_check") and args is not None:
            check_method = cast(Callable[[argparse.Namespace], tuple[bool, str]], self._availability_check)
            return check_method(args)
        return True, ""

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        """Execute the benchmark."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement format_result()")


# Preset definitions
PRESETS: dict[str, dict[str, object]] = {
    "balanced": {
        "description": "Quick mix of CPU and IO tests.",
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
    "cpu": {"description": "CPU heavy synthetic workloads.", "categories": ("cpu",)},
    "io": {"description": "Disk and filesystem focused tests.", "categories": ("io",)},
    "memory": {
        "description": "Memory bandwidth and latency tests.",
        "categories": ("memory",),
    },
    "compression": {
        "description": "Compression and decompression throughput.",
        "categories": ("compression",),
    },
    "crypto": {
        "description": "Cryptography focused benchmarks.",
        "categories": ("crypto",),
    },
    "database": {
        "description": "Database engines (SQLite only).",
        "categories": ("database",),
    },
    "gpu-light": {
        "description": "Lightweight GPU render sanity checks.",
        "benchmarks": ("glmark2", "vkmark"),
    },
    "gpu": {
        "description": "GPU render benchmarks (glmark2 and vkmark).",
        "categories": ("gpu",),
    },
    "network": {
        "description": "Loopback network throughput tests.",
        "categories": ("network",),
    },
    "all": {"description": "Run every available benchmark.", "all": True},
}
