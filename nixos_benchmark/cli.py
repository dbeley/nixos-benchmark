"""Command-line interface for nixos-benchmark."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence, Tuple

from .benchmark_registry import PRESETS, get_all_benchmarks
from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
)
from .output import (
    build_html_summary,
    describe_benchmark,
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
        tokens = [
            part.strip()
            for token in raw_values
            for part in token.split(",")
            if part.strip()
        ]
        if not tokens:
            parser.error(f"{option_string} requires at least one value.")
        for token in tokens:
            if self.valid_choices and token not in self.valid_choices:
                choices = ", ".join(self.valid_choices)
                parser.error(
                    f"{option_string}: invalid choice: {token!r} "
                    f"(choose from {choices})"
                )
            current.append(token)
        setattr(namespace, self.dest, current)


def unique_ordered(values: Sequence[str]) -> List[str]:
    """Return unique values in order."""
    return list(dict.fromkeys(values))


def expand_presets(presets: Sequence[str]) -> List[str]:
    """Expand preset names into benchmark keys."""
    from .benchmark_registry import ALL_BENCHMARKS, PRESETS
    
    selected: set[str] = set()
    if not presets:
        presets = ["balanced"]
    for preset in presets:
        config = PRESETS.get(preset)
        if not config:
            continue
        if config.get("all"):
            return [bench.key for bench in ALL_BENCHMARKS]
        categories = config.get("categories", [])
        selected |= {
            bench.key
            for bench in ALL_BENCHMARKS
            if any(cat in bench.categories for cat in categories)
        }
        for bench_name in config.get("benchmarks", []):
            selected.add(bench_name)
    return sorted(selected)


def execute_benchmark(benchmark, args: argparse.Namespace) -> BenchmarkResult:
    """Execute a single benchmark instance."""
    ok, reason = benchmark.validate(args)
    if not ok:
        return BenchmarkResult(
            name=benchmark.key,
            status="skipped",
            categories=benchmark.categories,
            presets=benchmark.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=reason,
        )

    try:
        result = benchmark.execute(args)
    except FileNotFoundError as exc:
        return BenchmarkResult(
            name=benchmark.key,
            status="skipped",
            categories=benchmark.categories,
            presets=benchmark.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=f"Missing file or path: {exc}",
        )
    except subprocess.CalledProcessError as exc:
        # Preserve command output for debugging
        raw_output = exc.stdout if exc.stdout else ""
        command = " ".join(exc.cmd) if isinstance(exc.cmd, list) else str(exc.cmd)
        return BenchmarkResult(
            name=benchmark.key,
            status="error",
            categories=benchmark.categories,
            presets=benchmark.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=f"Command failed with exit code {exc.returncode}",
            command=command,
            raw_output=raw_output,
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
            name=benchmark.key,
            status="error",
            categories=benchmark.categories,
            presets=benchmark.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=str(exc),
            command=command,
            raw_output=raw_output,
        )

    # Update result with categories and presets from benchmark instance
    result = BenchmarkResult(
        name=result.name,
        status=result.status,
        categories=benchmark.categories,
        presets=benchmark.presets,
        metrics=result.metrics,
        parameters=result.parameters,
        duration_seconds=result.duration_seconds,
        command=result.command,
        message=result.message,
        raw_output=result.raw_output,
    )
    return result


def main() -> int:
    """Main entry point for the benchmark suite."""
    from .benchmark_registry import ALL_BENCHMARKS, PRESETS
    
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
    args = parser.parse_args()

    if args.list_presets:
        print("Available presets:")
        for name in sorted(PRESETS):
            desc = PRESETS[name]["description"]
            print(f"  {name:<10} {desc}")
        return 0

    if args.list_benchmarks:
        print("Available benchmarks:")
        for benchmark in ALL_BENCHMARKS:
            categories = ", ".join(benchmark.categories)
            presets = ", ".join(benchmark.presets)
            print(
                f"  {benchmark.key:<20} [{categories}] presets: {presets} - {benchmark.description}"
            )
        return 0

    requested_presets = unique_ordered(args.presets)
    if not args.benchmarks and not requested_presets:
        requested_presets = ["balanced"]
    selected_names = (
        unique_ordered(args.benchmarks)
        if args.benchmarks
        else expand_presets(requested_presets)
    )

    if not selected_names:
        print("No benchmarks requested.", file=sys.stderr)
        return 1

    benchmark_map = {bench.key: bench for bench in ALL_BENCHMARKS}
    results_with_benchmarks: List[Tuple[BenchmarkResult, BenchmarkBase]] = []
    for name in selected_names:
        print(f"Executing {name}")
        benchmark = benchmark_map[name]
        result = execute_benchmark(benchmark, args)
        results_with_benchmarks.append((result, benchmark))

    if not results_with_benchmarks:
        print("No benchmarks executed.", file=sys.stderr)
        return 1

    results = [result for result, _ in results_with_benchmarks]
    generated_at = datetime.now(timezone.utc)
    system_info = gather_system_info(args.hostname or None)

    report = BenchmarkReport(
        generated_at=generated_at,
        system=system_info,
        benchmarks=results,
        presets_requested=requested_presets,
        benchmarks_requested=selected_names,
    )

    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = generated_at.strftime("%Y%m%d-%H%M%S")
        hostname_slug = sanitize_for_filename(system_info.hostname)
        filename = f"{timestamp}.json"
        if hostname_slug:
            filename = f"{timestamp}-{hostname_slug}.json"
        output_path = Path("results") / filename

    write_json_report(report, output_path)

    print(f"Wrote {output_path}")
    for result, benchmark in results_with_benchmarks:
        summary = benchmark.format_result(result)
        if summary:
            print(f"{result.name}: {summary}")

    if args.html_summary:
        build_html_summary(output_path.parent, Path(args.html_summary))

    return 0
