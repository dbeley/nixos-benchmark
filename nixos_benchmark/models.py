"""Data models for benchmark results and system information."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .benchmarks.types import BenchmarkType


@dataclass
class BenchmarkMetrics:
    """Type-safe container for benchmark-specific metrics."""

    data: dict[str, float | str | int]

    def __getitem__(self, key: str) -> float | str | int:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def to_dict(self) -> dict[str, float | str | int]:
        """Convert to dict for JSON serialization."""
        return self.data.copy()


@dataclass
class BenchmarkParameters:
    """Type-safe container for benchmark parameters."""

    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return self.data.copy()


@dataclass
class BenchmarkResult:
    """Complete benchmark result - use throughout entire lifecycle."""

    benchmark_type: BenchmarkType
    status: str  # "ok" | "skipped" | "error"
    presets: tuple[str, ...]
    metrics: BenchmarkMetrics
    parameters: BenchmarkParameters
    duration_seconds: float = 0.0
    command: str = ""
    message: str = ""  # For skipped/error cases
    raw_output: str = ""
    version: str = ""

    @property
    def name(self) -> str:
        return self.benchmark_type.value

    def to_dict(self) -> dict[str, object]:
        """Convert to dict only when serializing to JSON."""
        return {
            "name": self.benchmark_type.value,
            "status": self.status,
            "presets": list(self.presets),
            "metrics": self.metrics.to_dict(),
            "parameters": self.parameters.to_dict(),
            "duration_seconds": self.duration_seconds,
            "command": self.command,
            "message": self.message,
            "raw_output": self.raw_output,
            "version": self.version,
        }


@dataclass
class SystemInfo:
    """System information."""

    platform: str
    machine: str
    processor: str
    python_version: str
    cpu_count: int | None
    hostname: str
    os_name: str = ""
    os_version: str = ""
    kernel_version: str = ""
    cpu_model: str = ""
    memory_total_bytes: int | None = None
    gpus: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Convert to dict for JSON serialization."""
        return {
            "platform": self.platform,
            "machine": self.machine,
            "processor": self.processor,
            "python_version": self.python_version,
            "cpu_count": self.cpu_count,
            "hostname": self.hostname,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "kernel_version": self.kernel_version,
            "cpu_model": self.cpu_model,
            "memory_total_bytes": self.memory_total_bytes,
            "gpus": list(self.gpus),
        }


@dataclass
class BenchmarkReport:
    """Complete report - top-level data structure."""

    generated_at: datetime
    system: SystemInfo
    benchmarks: list[BenchmarkResult]
    presets_requested: list[str]
    benchmarks_requested: list[BenchmarkType]

    def to_dict(self) -> dict[str, object]:
        """Only convert to dict for JSON serialization."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "system": self.system.to_dict(),
            "benchmarks": [b.to_dict() for b in self.benchmarks],
            "presets_requested": self.presets_requested,
            "benchmarks_requested": [b.value for b in self.benchmarks_requested],
        }
