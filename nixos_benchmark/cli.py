"""Command-line interface for nixos-benchmark."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from .benchmarks import (
    ALL_BENCHMARKS,
    BENCHMARK_MAP,
    PRESETS,
    BenchmarkType,
    get_presets_for_benchmark,
)
from .benchmarks.base import BenchmarkBase
from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
)
from .output import (
    build_html_summary,
    sanitize_for_filename,
    write_json_report,
)
from .system_info import gather_system_info


class CommaSeparatedListAction(argparse.Action):
    """Parse comma-separated values and accumulate across repeated flags."""

    def __init__(self, option_strings, dest, **kwargs):
        self.valid_choices = kwargs.pop("choices", None)
        super().__init__(option_strings, dest, **kwargs)
        self.choices = self.valid_choices

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        option_string = option_string or self.option_strings[0]
        current = list(getattr(namespace, self.dest, []) or [])
        raw_values = values if isinstance(values, list) else [values]
        tokens = [part.strip() for token in raw_values for part in token.split(",") if part.strip()]
        if not tokens:
            parser.error(f"{option_string} requires at least one value.")
        for token in tokens:
            if self.valid_choices and token not in self.valid_choices:
                choices = ", ".join(self.valid_choices)
                parser.error(f"{option_string}: invalid choice: {token!r} (choose from {choices})")
            current.append(token)
        setattr(namespace, self.dest, current)


T = TypeVar("T")


def unique_ordered(values: Sequence[T]) -> list[T]:
    """Return unique values in order."""
    return list(dict.fromkeys(values))


def expand_presets(presets: Sequence[str]) -> list[BenchmarkType]:
    """Expand preset names into benchmark types."""
    selected: list[BenchmarkType] = []
    if not presets:
        presets = ["balanced"]
    for preset in presets:
        config = PRESETS.get(preset)
        if not config:
            continue
        benchmarks = config.get("benchmarks", [])
        if isinstance(benchmarks, (list, tuple)):
            for bench_type in benchmarks:
                if isinstance(bench_type, BenchmarkType):
                    selected.append(bench_type)
    return unique_ordered(selected)


def parse_benchmark_types(benchmark_names: Sequence[str]) -> list[BenchmarkType]:
    """Convert user-provided benchmark names to BenchmarkType values."""
    types: list[BenchmarkType] = []
    for name in benchmark_names:
        types.append(BenchmarkType(name))
    return unique_ordered(types)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build and configure the argument parser."""
    parser = argparse.ArgumentParser(description="Run a lightweight benchmark suite.")
    parser.add_argument(
        "--output",
        default="",
        help="Where to write the benchmark results (JSON). Leave empty for timestamped filenames.",
    )
    parser.add_argument(
        "--html-summary",
        default="results/index.html",
        help="Optional HTML dashboard path (empty string to disable).",
    )
    parser.add_argument(
        "--hostname",
        default="",
        help="Override the hostname stored in the report (also used for auto filenames).",
    )
    parser.add_argument(
        "--preset",
        dest="presets",
        action=CommaSeparatedListAction,
        choices=sorted(PRESETS.keys()),
        metavar="PRESET",
        default=[],
        help="Comma-separated preset names (defaults to 'balanced').",
    )
    parser.add_argument(
        "--benchmarks",
        dest="benchmarks",
        action=CommaSeparatedListAction,
        choices=sorted(bt.value for bt in BenchmarkType),
        metavar="BENCHMARK",
        default=[],
        help="Comma-separated benchmark names to run (skips preset expansion).",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets and exit.",
    )
    parser.add_argument(
        "--list-benchmarks",
        action="store_true",
        help="List available benchmarks and exit.",
    )
    parser.add_argument(
        "--glmark2-mode",
        choices=("offscreen", "onscreen"),
        default="offscreen",
        help="Rendering mode for glmark2 (offscreen avoids taking over the display).",
    )
    return parser


def list_presets() -> int:
    """List available presets and exit."""
    print("Available presets:")
    for name in sorted(PRESETS):
        desc = PRESETS[name]["description"]
        print(f"  {name:<10} {desc}")
    return 0


def list_benchmarks() -> int:
    """List available benchmarks and exit."""
    print("Available benchmarks:")
    for benchmark in ALL_BENCHMARKS:
        presets = ", ".join(get_presets_for_benchmark(benchmark))
        print(f"  {benchmark.name:<20} presets: {presets} - {benchmark.description}")
    return 0


def determine_output_path(args: argparse.Namespace, generated_at: datetime, system_info) -> Path:
    """Determine the output path for the benchmark report."""
    if args.output:
        return Path(args.output)
    timestamp = generated_at.strftime("%Y%m%d-%H%M%S")
    hostname_slug = sanitize_for_filename(system_info.hostname)
    filename = f"{timestamp}.json"
    if hostname_slug:
        filename = f"{timestamp}-{hostname_slug}.json"
    return Path("results") / filename


def execute_benchmark(benchmark, args: argparse.Namespace) -> BenchmarkResult:
    """Execute a single benchmark instance."""
    benchmark_presets = get_presets_for_benchmark(benchmark)
    benchmark_version = benchmark.get_version()
    ok, reason = benchmark.validate(args)
    if not ok:
        return BenchmarkResult(
            benchmark_type=benchmark.benchmark_type,
            status="skipped",
            presets=benchmark_presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=reason,
            version=benchmark_version,
        )

    try:
        result = benchmark.execute(args)
    except FileNotFoundError as exc:
        return BenchmarkResult(
            benchmark_type=benchmark.benchmark_type,
            status="skipped",
            presets=benchmark_presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=f"Missing file or path: {exc}",
        )
    except subprocess.CalledProcessError as exc:
        # Preserve command output for debugging
        raw_output = exc.stdout if exc.stdout else ""
        command = " ".join(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
        return BenchmarkResult(
            benchmark_type=benchmark.benchmark_type,
            status="error",
            presets=benchmark_presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=f"Command failed with exit code {exc.returncode}",
            command=command,
            raw_output=raw_output,
            version=benchmark_version,
        )
    except Exception as exc:
        # Try to preserve raw_output if it's a parsing error on a valid result
        raw_output = ""
        command = ""
        if hasattr(exc, "__context__") and isinstance(exc.__context__, subprocess.CalledProcessError):
            context = exc.__context__
            raw_output = context.stdout if context.stdout else ""
            command = " ".join(context.cmd) if isinstance(context.cmd, list) else str(context.cmd)
        return BenchmarkResult(
            benchmark_type=benchmark.benchmark_type,
            status="error",
            presets=benchmark_presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=str(exc),
            command=command,
            raw_output=raw_output,
            version=benchmark_version,
        )

    # Update result with presets from benchmark instance
    return BenchmarkResult(
        benchmark_type=result.benchmark_type,
        status=result.status,
        presets=benchmark_presets,
        metrics=result.metrics,
        parameters=result.parameters,
        duration_seconds=result.duration_seconds,
        command=result.command,
        message=result.message,
        raw_output=result.raw_output,
        version=result.version or benchmark_version,
    )


def main() -> int:
    """Main entry point for the benchmark suite."""
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.list_presets:
        return list_presets()

    if args.list_benchmarks:
        return list_benchmarks()

    requested_presets = unique_ordered(args.presets)
    if not args.benchmarks and not requested_presets:
        requested_presets = ["balanced"]
    selected_benchmarks = (
        parse_benchmark_types(unique_ordered(args.benchmarks)) if args.benchmarks else expand_presets(requested_presets)
    )

    if not selected_benchmarks:
        print("No benchmarks requested.", file=sys.stderr)
        return 1

    results_with_benchmarks: list[tuple[BenchmarkResult, BenchmarkBase]] = []
    for benchmark_type in selected_benchmarks:
        print(f"Executing {benchmark_type.value}")
        benchmark = BENCHMARK_MAP[benchmark_type]
        result = execute_benchmark(benchmark, args)
        results_with_benchmarks.append((result, benchmark))

    if not results_with_benchmarks:
        print("No benchmarks executed.", file=sys.stderr)
        return 1

    results = [result for result, _ in results_with_benchmarks]
    generated_at = datetime.now(UTC)
    system_info = gather_system_info(args.hostname or None)

    report = BenchmarkReport(
        generated_at=generated_at,
        system=system_info,
        benchmarks=results,
        presets_requested=requested_presets,
        benchmarks_requested=selected_benchmarks,
    )

    output_path = determine_output_path(args, generated_at, system_info)
    write_json_report(report, output_path)

    print(f"Wrote {output_path}")
    for result, benchmark in results_with_benchmarks:
        summary = benchmark.format_result(result)
        if summary:
            print(f"{result.name}: {summary}")

    if args.html_summary:
        build_html_summary(output_path.parent, Path(args.html_summary))

    return 0
