"""Score rules and helpers for benchmark outputs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..models import BenchmarkMetrics, BenchmarkResult
from .types import BenchmarkType


def _coerce_number(value: object) -> float | None:
    """Convert arbitrary values to float when possible."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _metric_number(metrics: BenchmarkMetrics, key: str, scale: float = 1.0) -> float | None:
    """Fetch a numeric metric and apply an optional scale."""
    number = _coerce_number(metrics.get(key))
    if number is None:
        return None
    return number * scale


def _first_numeric(*values: object) -> float | None:
    """Return the first value that can be coerced to a float."""
    for value in values:
        number = _coerce_number(value)
        if number is not None:
            return number
    return None


def _max_numeric(values: Iterable[float]) -> float | None:
    """Return max value or None for empty iterables."""
    numbers = list(values)
    return max(numbers) if numbers else None


def _mean_numeric(values: Iterable[float | None]) -> float | None:
    """Return the arithmetic mean of numeric values, ignoring missing entries."""
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _format_hash_rate(hashes_per_sec: float) -> str:
    """Pretty-format a hash rate with dynamic units."""
    units = ["H/s", "kH/s", "MH/s", "GH/s", "TH/s"]
    value = hashes_per_sec
    unit = units[0]
    for candidate in units[1:]:
        if value < 1000:
            break
        value /= 1000
        unit = candidate
    return f"{value:.1f} {unit}"


@dataclass(frozen=True)
class ScoreRule:
    metric: str
    label: str
    higher_is_better: bool = True
    extractor: Callable[[BenchmarkResult], float | None] | None = None
    formatter: Callable[[float], str] | None = None

    def extract(self, result: BenchmarkResult) -> float | None:
        if result.status != "ok":
            return None
        return self.extractor(result) if self.extractor else _metric_number(result.metrics, self.metric)

    def format_value(self, value: float) -> str:
        if self.formatter:
            return self.formatter(value)
        return f"{value:,.2f}"


CPU_SCORE_RULES: dict[BenchmarkType, ScoreRule] = {
    BenchmarkType.OPENSSL_SPEED: ScoreRule(
        metric="max_kbytes_per_sec",
        label="AES throughput (MiB/s)",
        higher_is_better=True,
        extractor=lambda result: _metric_number(result.metrics, "max_kbytes_per_sec", scale=1 / 1024),
        formatter=lambda value: f"{value:.1f} MiB/s",
    ),
    BenchmarkType.SEVENZIP: ScoreRule(
        metric="total_rating_mips",
        label="Total rating (MIPS)",
        higher_is_better=True,
        formatter=lambda value: f"{value:,.0f} MIPS",
    ),
    BenchmarkType.JOHN: ScoreRule(
        metric="c_per_sec",
        label="Cracks per second",
        higher_is_better=True,
        formatter=lambda value: f"{value:,.0f} c/s",
    ),
    BenchmarkType.STOCKFISH: ScoreRule(
        metric="nodes_per_sec",
        label="Nodes per second",
        higher_is_better=True,
        formatter=lambda value: f"{value / 1_000_000:.2f} Mnps",
    ),
    BenchmarkType.STRESS_NG: ScoreRule(
        metric="bogo_ops_per_sec_real",
        label="Bogo-ops per second",
        higher_is_better=True,
        formatter=lambda value: f"{value:,.0f} ops/s",
    ),
    BenchmarkType.SYSBENCH_CPU: ScoreRule(
        metric="events_per_sec",
        label="Events per second",
        higher_is_better=True,
        formatter=lambda value: f"{value:,.0f} events/s",
    ),
    BenchmarkType.GEEKBENCH: ScoreRule(
        metric="multi_core_score",
        label="CPU score",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(
            result.metrics.get("multi_core_score"), result.metrics.get("single_core_score")
        ),
        formatter=lambda value: f"{value:,.0f} pts",
    ),
    BenchmarkType.ZSTD: ScoreRule(
        metric="compress_mb_per_s",
        label="Compression throughput (MB/s)",
        higher_is_better=True,
        formatter=lambda value: f"{value:,.0f} MB/s",
    ),
    BenchmarkType.PIGZ: ScoreRule(
        metric="compress_mb_per_s",
        label="Compression throughput (MB/s)",
        higher_is_better=True,
        formatter=lambda value: f"{value:,.0f} MB/s",
    ),
    BenchmarkType.LZ4: ScoreRule(
        metric="compress_mb_per_s",
        label="Compression throughput (MB/s)",
        higher_is_better=True,
        formatter=lambda value: f"{value:,.0f} MB/s",
    ),
    BenchmarkType.X264: ScoreRule(
        metric="fps",
        label="Encoding FPS",
        higher_is_better=True,
        formatter=lambda value: f"{value:.1f} fps",
    ),
    BenchmarkType.X265: ScoreRule(
        metric="fps",
        label="Encoding FPS",
        higher_is_better=True,
        formatter=lambda value: f"{value:.1f} fps",
    ),
    BenchmarkType.FFMPEG_TRANSCODE: ScoreRule(
        metric="effective_fps",
        label="Transcode FPS",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(
            result.metrics.get("effective_fps"), result.metrics.get("reported_fps")
        ),
        formatter=lambda value: f"{value:.1f} fps",
    ),
}

GPU_SCORE_RULES: dict[BenchmarkType, ScoreRule] = {
    BenchmarkType.GLMARK2: ScoreRule(
        metric="score",
        label="glmark2 score",
        higher_is_better=True,
        formatter=lambda value: f"{value:.0f} pts",
    ),
    BenchmarkType.VKMARK: ScoreRule(
        metric="fps_avg",
        label="Average FPS",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(result.metrics.get("fps_avg"), result.metrics.get("fps_max")),
        formatter=lambda value: f"{value:.1f} fps",
    ),
    BenchmarkType.FURMARK_GL: ScoreRule(
        metric="fps_avg",
        label="Average FPS",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(result.metrics.get("fps_avg")),
        formatter=lambda value: f"{value:.1f} fps",
    ),
    BenchmarkType.FURMARK_VK: ScoreRule(
        metric="fps_avg",
        label="Average FPS",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(result.metrics.get("fps_avg")),
        formatter=lambda value: f"{value:.1f} fps",
    ),
    BenchmarkType.FURMARK_KNOT_GL: ScoreRule(
        metric="fps_avg",
        label="Average FPS",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(result.metrics.get("fps_avg")),
        formatter=lambda value: f"{value:.1f} fps",
    ),
    BenchmarkType.FURMARK_KNOT_VK: ScoreRule(
        metric="fps_avg",
        label="Average FPS",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(result.metrics.get("fps_avg")),
        formatter=lambda value: f"{value:.1f} fps",
    ),
    BenchmarkType.CLPEAK: ScoreRule(
        metric="global_memory_bandwidth_gb_per_s",
        label="Peak bandwidth (GB/s)",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(
            result.metrics.get("global_memory_bandwidth_gb_per_s"),
            _max_numeric(v for v in result.metrics.data.values() if isinstance(v, (int, float))),
        ),
        formatter=lambda value: f"{value:.1f} GB/s",
    ),
    BenchmarkType.HASHCAT_GPU: ScoreRule(
        metric="hashes_per_sec",
        label="Hash throughput",
        higher_is_better=True,
        formatter=_format_hash_rate,
    ),
    BenchmarkType.GEEKBENCH_GPU: ScoreRule(
        metric="compute_score",
        label="Compute score",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(
            result.metrics.get("compute_score"),
            result.metrics.get("vulkan_score"),
            result.metrics.get("opencl_score"),
            result.metrics.get("metal_score"),
            result.metrics.get("cuda_score"),
        ),
        formatter=lambda value: f"{value:,.0f} pts",
    ),
    BenchmarkType.GEEKBENCH_GPU_VULKAN: ScoreRule(
        metric="compute_score",
        label="Compute score",
        higher_is_better=True,
        extractor=lambda result: _first_numeric(
            result.metrics.get("vulkan_score"),
            result.metrics.get("compute_score"),
            result.metrics.get("opencl_score"),
            result.metrics.get("metal_score"),
            result.metrics.get("cuda_score"),
        ),
        formatter=lambda value: f"{value:,.0f} pts",
    ),
}

IO_SCORE_RULES: dict[BenchmarkType, ScoreRule] = {
    BenchmarkType.FIO_SEQ: ScoreRule(
        metric="seqread_mib_per_s",
        label="Seq throughput (MiB/s)",
        higher_is_better=True,
        extractor=lambda result: _mean_numeric(
            [
                _metric_number(result.metrics, "seqread_mib_per_s"),
                _metric_number(result.metrics, "seqwrite_mib_per_s"),
            ]
        ),
        formatter=lambda value: f"{value:.1f} MiB/s",
    ),
    BenchmarkType.BONNIE: ScoreRule(
        metric="block_read_mb_s",
        label="Block throughput (MiB/s)",
        higher_is_better=True,
        extractor=lambda result: _mean_numeric(
            [
                _metric_number(result.metrics, "block_read_mb_s"),
                _metric_number(result.metrics, "block_write_mb_s"),
            ]
        ),
        formatter=lambda value: f"{value:.1f} MiB/s",
    ),
    BenchmarkType.IOZONE: ScoreRule(
        metric="read_mb_s",
        label="I/O throughput (MiB/s)",
        higher_is_better=True,
        extractor=lambda result: _mean_numeric(
            [
                _metric_number(result.metrics, "read_mb_s"),
                _metric_number(result.metrics, "reread_mb_s"),
                _metric_number(result.metrics, "write_mb_s"),
                _metric_number(result.metrics, "rewrite_mb_s"),
            ]
        ),
        formatter=lambda value: f"{value:.1f} MiB/s",
    ),
}

SCORE_RULES: dict[BenchmarkType, ScoreRule] = {**CPU_SCORE_RULES, **GPU_SCORE_RULES, **IO_SCORE_RULES}


def get_score_rule(bench_type: BenchmarkType | None) -> ScoreRule | None:
    """Return the scoring rule for a benchmark, if defined."""
    if bench_type is None:
        return None
    return SCORE_RULES.get(bench_type)


__all__ = [
    "CPU_SCORE_RULES",
    "GPU_SCORE_RULES",
    "IO_SCORE_RULES",
    "SCORE_RULES",
    "ScoreRule",
    "get_score_rule",
]
