"""Command-line interface for nixos-benchmark."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Sequence

from .benchmarks import PRESET_DEFINITIONS, get_all_benchmarks
from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
)
from .output import build_html_summary, describe_benchmark, sanitize_for_filename, write_json_report
from .system_info import gather_system_info
from .utils import check_requirements


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
    all_benchmarks = get_all_benchmarks()
    selected: set[str] = set()
    if not presets:
        presets = ["balanced"]
    for preset in presets:
        config = PRESET_DEFINITIONS.get(preset)
        if not config:
            continue
        if config.get("all"):
            return [definition.key for definition in all_benchmarks]
        categories = config.get("categories", [])
        selected |= {
            definition.key
            for definition in all_benchmarks
            if any(cat in definition.categories for cat in categories)
        }
        for bench in config.get("benchmarks", []):
            selected.add(bench)
    return sorted(selected)


def execute_definition(definition, args: argparse.Namespace) -> BenchmarkResult:
    """Execute a single benchmark definition."""
    ok, reason = check_requirements(definition.requires)
    if not ok:
        return BenchmarkResult(
            name=definition.key,
            status="skipped",
            categories=definition.categories,
            presets=definition.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=reason,
        )

    if definition.availability_check:
        ok, reason = definition.availability_check(args)
        if not ok:
            return BenchmarkResult(
                name=definition.key,
                status="skipped",
                categories=definition.categories,
                presets=definition.presets,
                metrics=BenchmarkMetrics({}),
                parameters=BenchmarkParameters({}),
                message=reason,
            )

    try:
        result = definition.runner(args)
    except FileNotFoundError as exc:
        return BenchmarkResult(
            name=definition.key,
            status="skipped",
            categories=definition.categories,
            presets=definition.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=f"Missing file or path: {exc}",
        )
    except subprocess.CalledProcessError as exc:
        return BenchmarkResult(
            name=definition.key,
            status="error",
            categories=definition.categories,
            presets=definition.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=f"Command failed with exit code {exc.returncode}",
        )
    except Exception as exc:
        return BenchmarkResult(
            name=definition.key,
            status="error",
            categories=definition.categories,
            presets=definition.presets,
            metrics=BenchmarkMetrics({}),
            parameters=BenchmarkParameters({}),
            message=str(exc),
        )

    # Update result with categories and presets from definition
    result = BenchmarkResult(
        name=result.name,
        status=result.status,
        categories=definition.categories,
        presets=definition.presets,
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
    all_benchmarks = get_all_benchmarks()

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
        choices=sorted(PRESET_DEFINITIONS.keys()),
        metavar="PRESET",
        default=[],
        help="Comma-separated preset names (defaults to 'balanced').",
    )
    parser.add_argument(
        "--benchmarks",
        dest="benchmarks",
        action=CommaSeparatedListAction,
        choices=sorted(definition.key for definition in all_benchmarks),
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
        for name in sorted(PRESET_DEFINITIONS):
            desc = PRESET_DEFINITIONS[name]["description"]
            print(f"  {name:<10} {desc}")
        return 0

    if args.list_benchmarks:
        print("Available benchmarks:")
        for definition in all_benchmarks:
            categories = ", ".join(definition.categories)
            presets = ", ".join(definition.presets)
            print(
                f"  {definition.key:<20} [{categories}] presets: {presets} - {definition.description}"
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

    definition_map = {definition.key: definition for definition in all_benchmarks}
    results: List[BenchmarkResult] = []
    for name in selected_names:
        print(f"Executing {name}")
        definition = definition_map[name]
        results.append(execute_definition(definition, args))

    if not results:
        print("No benchmarks executed.", file=sys.stderr)
        return 1

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
    for bench in results:
        summary = describe_benchmark(bench)
        if summary:
            print(f"{bench.name}: {summary}")

    if args.html_summary:
        build_html_summary(output_path.parent, Path(args.html_summary))

    return 0
