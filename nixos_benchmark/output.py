"""Output generation for JSON and HTML reports."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from .benchmarks import (
    BENCHMARK_MAP,
    CPU_BENCHMARK_TYPES,
    GPU_BENCHMARK_TYPES,
    BenchmarkType,
    ScoreRule,
    get_score_rule,
)
from .benchmarks.base import BenchmarkBase
from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
)


UNKNOWN_TIMESTAMP = datetime.min.replace(tzinfo=UTC)


class ReportRow(TypedDict):
    file: str
    generated: str
    generated_dt: datetime
    system: dict[str, object]
    presets: list[str]
    benchmarks: list[dict[str, object]]
    benchmark_results: list[BenchmarkResult]


class Cell(TypedDict):
    text: str
    version: str
    has_result: bool


class RowWithCells(TypedDict):
    file: str
    generated: str
    generated_dt: datetime
    system: dict[str, object]
    presets: list[str]
    cells: list[Cell]


class GraphBar(TypedDict):
    label: str
    value: float
    display: str
    report_file: str
    system_meta: str


def sanitize_for_filename(value: str) -> str:
    """Sanitize a string to be safe for use in filenames."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


def describe_benchmark(bench: BenchmarkResult) -> str:
    """Extract the human-readable score of a benchmark result."""
    benchmark_instance = BENCHMARK_MAP.get(bench.benchmark_type)
    if benchmark_instance:
        return benchmark_instance.format_result(bench)

    # Fallback for unknown benchmarks
    status_message = BenchmarkBase.format_status_message(bench)
    return status_message or ""


def _benchmark_type_from_name(name: str) -> BenchmarkType | None:
    try:
        return BenchmarkType(name)
    except ValueError:
        return None


def write_json_report(report: BenchmarkReport, output_path: Path) -> None:
    """Write benchmark report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2))


def _parse_generated(value: str, default_timestamp: datetime) -> datetime:
    """Parse an ISO timestamp, falling back to a default value."""
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return default_timestamp


def _as_str(value: object, default: str = "") -> str:
    """Coerce a value to string for safer typing."""
    text = str(value) if value is not None else ""
    return text if text else default


def _as_str_list(value: object) -> list[str]:
    """Ensure presets/labels are string lists."""
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return []


def _as_metrics_dict(value: object) -> dict[str, float | str | int]:
    """Filter metrics payload to supported primitive values."""
    if not isinstance(value, dict):
        return {}
    filtered: dict[str, float | str | int] = {}
    for key, metric in value.items():
        if isinstance(metric, (float, int, str)):
            filtered[str(key)] = metric
    return filtered


def _as_parameters_dict(value: object) -> dict[str, Any]:
    """Coerce parameters payload into a string-keyed dict."""
    if not isinstance(value, dict):
        return {}
    return {str(key): val for key, val in value.items()}


def _as_float(value: object, default: float = 0.0) -> float:
    """Safely convert duration-like values to float."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _parse_benchmark_result(bench_dict: dict[str, object]) -> BenchmarkResult | None:
    """Convert a raw benchmark dictionary into a BenchmarkResult object."""
    bench_type = _benchmark_type_from_name(_as_str(bench_dict.get("name", "")))
    if bench_type is None:
        return None
    return BenchmarkResult(
        benchmark_type=bench_type,
        status=_as_str(bench_dict.get("status", "ok"), "ok"),
        presets=tuple(_as_str_list(bench_dict.get("presets", []))),
        metrics=BenchmarkMetrics(_as_metrics_dict(bench_dict.get("metrics", {}))),
        parameters=BenchmarkParameters(_as_parameters_dict(bench_dict.get("parameters", {}))),
        duration_seconds=_as_float(bench_dict.get("duration_seconds", 0.0)),
        command=_as_str(bench_dict.get("command", "")),
        message=_as_str(bench_dict.get("message", "")),
        raw_output=_as_str(bench_dict.get("raw_output", "")),
        version=_as_str(bench_dict.get("version", "")),
    )


def _load_reports_and_metadata(
    json_files: list[Path],
    default_timestamp: datetime,
) -> tuple[list[ReportRow], dict[str, dict[str, set[str]]]]:
    """Load JSON reports and collect per-benchmark metadata."""
    reports: list[ReportRow] = []
    bench_metadata: dict[str, dict[str, set[str]]] = {}

    for path in json_files:
        try:
            raw = path.read_text()
            data: dict[str, Any] = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            continue

        presets_raw = data.get("presets_requested", []) or []
        presets = [str(p) for p in presets_raw] if isinstance(presets_raw, list) else []
        benchmarks_raw = data.get("benchmarks", []) or []
        benchmarks: list[dict[str, object]] = [bench for bench in benchmarks_raw if isinstance(bench, dict)]
        benchmark_results: list[BenchmarkResult] = []
        for bench_dict in benchmarks:
            parsed = _parse_benchmark_result(bench_dict)
            if parsed:
                benchmark_results.append(parsed)

        # basic shape for each row
        reports.append(
            {
                "file": path.name,
                "generated": data.get("generated_at", "unknown"),
                "generated_dt": _parse_generated(data.get("generated_at", "unknown"), default_timestamp),
                "system": data.get("system", {}) or {},
                "presets": presets,
                "benchmarks": benchmarks,
                "benchmark_results": benchmark_results,
            }
        )

        for bench_result in benchmark_results:
            name = bench_result.name
            bench_type = bench_result.benchmark_type
            if not name or bench_type is None:
                continue
            meta = bench_metadata.setdefault(name, {"presets": set(), "versions": set()})
            meta["presets"].update(bench_result.presets)
            version = bench_result.version
            if version:
                meta["versions"].add(str(version))

    return reports, bench_metadata


def _build_rows(
    reports: list[ReportRow],
    bench_columns: list[str],
) -> list[RowWithCells]:
    """Build table rows from loaded reports and benchmark columns."""
    rows: list[RowWithCells] = []

    for report in reports:
        bench_map = {bench.name: bench for bench in report.get("benchmark_results", [])}
        raw_bench_map = {_as_str(bench.get("name", "")): bench for bench in report["benchmarks"]}
        cells: list[Cell] = []
        for bench_name in bench_columns:
            bench_result = bench_map.get(bench_name)
            raw_bench = raw_bench_map.get(bench_name, {})
            if bench_result is None and raw_bench:
                bench_result = _parse_benchmark_result(raw_bench)
            version_value = bench_result.version if bench_result else _as_str(raw_bench.get("version", ""))
            description = describe_benchmark(bench_result) if bench_result else ""
            has_result = bool(bench_result or raw_bench)
            cells.append({"text": description or "—", "version": version_value, "has_result": has_result})

        rows.append(
            {
                "file": report["file"],
                "generated": report["generated"],
                "generated_dt": report["generated_dt"],
                "system": report["system"],
                "presets": report["presets"],
                "cells": cells,
            }
        )

    return rows


def _format_memory_label(value: object) -> str:
    try:
        bytes_value = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "Unknown RAM"
    if bytes_value <= 0:
        return "Unknown RAM"
    gib = bytes_value / (1024**3)
    return f"{gib:.1f} GiB"


def _system_cell_label(system: dict[str, object]) -> str:
    hostname = str(system.get("hostname", "") or "").strip()
    machine = str(system.get("machine", "") or "").strip()
    if hostname and machine:
        return f"{hostname} ({machine})"
    return hostname or machine or "n/a"


def _system_details_text(system: dict[str, object]) -> str:
    parts = []
    cpu_label = system.get("cpu_model") or system.get("processor")
    if cpu_label:
        parts.append(f"CPU: {cpu_label}")
    gpus = system.get("gpus") or []
    if isinstance(gpus, (list, tuple)):
        gpu_label = ", ".join(str(gpu) for gpu in gpus if str(gpu).strip())
    else:
        gpu_label = str(gpus) if gpus else ""
    if gpu_label:
        parts.append(f"GPU: {gpu_label}")
    mem_label = _format_memory_label(system.get("memory_total_bytes"))
    if mem_label:
        parts.append(f"RAM: {mem_label}")
    os_name = system.get("os_name") or system.get("platform")
    os_version = system.get("os_version") or ""
    if os_name:
        parts.append(f"OS: {os_name} {os_version}".strip())
    kernel = system.get("kernel_version") or ""
    if kernel:
        parts.append(f"Linux: {kernel}")
    return "\n".join(parts) or "System details unavailable"


def _format_gpu_label(system: dict[str, object]) -> str:
    gpus = system.get("gpus") or []
    if isinstance(gpus, (list, tuple)):
        labels = [str(gpu) for gpu in gpus if str(gpu).strip()]
        return " / ".join(labels)
    return str(gpus) if gpus else ""


def _format_cpu_label(system: dict[str, object]) -> str:
    cpu_label = system.get("cpu_model") or system.get("processor") or ""
    return str(cpu_label)


def _system_meta_line(system: dict[str, object]) -> str:
    parts = []
    cpu_label = system.get("cpu_model") or system.get("processor")
    if cpu_label:
        parts.append(str(cpu_label))

    gpu_label = _format_gpu_label(system)
    if gpu_label:
        parts.append(gpu_label)

    ram_label = _format_memory_label(system.get("memory_total_bytes"))
    if ram_label and not ram_label.lower().startswith("unknown"):
        parts.append(ram_label)

    os_name = system.get("os_name") or system.get("platform")
    os_version = system.get("os_version") or ""
    if os_name:
        parts.append(f"{os_name} {os_version}".strip())

    kernel = system.get("kernel_version") or ""
    if kernel:
        label = str(kernel)
        parts.append(label if label.lower().startswith("linux") else f"Linux {label}")

    return " · ".join(str(part) for part in parts if str(part).strip())


def _format_generated_cell(generated: str, generated_dt: datetime) -> tuple[str, str, str]:
    """Return display text, sort value, and tooltip label for generated column."""
    raw_label = generated or "unknown"
    if generated_dt != UNKNOWN_TIMESTAMP:
        pretty = generated_dt.strftime("%b %d, %Y, %H:%M:%S %Z")
        return pretty, generated_dt.isoformat(), raw_label
    return raw_label, raw_label, raw_label


def _build_header_cells(
    bench_columns: list[str],
    bench_metadata: dict[str, dict[str, set[str]]],
) -> str:
    header_cells = ""
    for name in bench_columns:
        meta = bench_metadata.get(name, {"presets": set(), "versions": set()})
        preset_label = ", ".join(sorted(meta.get("presets", []))) or "unspecified"
        versions = ", ".join(sorted(meta.get("versions", []))) or "unknown"
        bench_type = _benchmark_type_from_name(name)
        bench_instance = BENCHMARK_MAP.get(bench_type) if bench_type else None
        summary = bench_instance.short_description() if bench_instance else ""
        tooltip_parts = [f"Presets: {preset_label}", f"Version: {versions}"]
        if summary:
            tooltip_parts.append(summary)
        rule = get_score_rule(bench_type) if bench_type else None
        if rule:
            direction_text = "Higher is better" if rule.higher_is_better else "Lower is better"
            tooltip_parts.append(f"{rule.label} · {direction_text}")
        tooltip = " &#10;".join(html.escape(part) for part in tooltip_parts)
        header_cells += f'<th class="sortable" data-type="text" title="{tooltip}">{html.escape(name)}</th>'
    return header_cells


def _build_body_rows(rows: list[RowWithCells]) -> list[str]:
    body_rows: list[str] = []
    for row in rows:
        system = row["system"]
        system_label = _system_cell_label(system)
        system_meta = _system_meta_line(system)
        system_details = html.escape(_system_details_text(system)).replace("\n", "&#10;")
        system_html = f'<div class="system-label">{html.escape(system_label)}</div>'
        if system_meta:
            system_html += f'<div class="system-meta">{html.escape(system_meta)}</div>'

        preset_label = ", ".join(row["presets"]) or "n/a"
        preset_html = f'<div class="preset-label">{html.escape(preset_label)}</div>'

        generated_display, generated_sort_value, generated_title = _format_generated_cell(
            row["generated"], row["generated_dt"]
        )

        cell_parts: list[str] = []
        for cell in row["cells"]:
            version_value = _as_str(cell.get("version", ""))
            description = _as_str(cell.get("text", "—")) or "—"
            has_result = bool(cell.get("has_result"))
            version_display = (version_value or "unknown") if has_result else ""
            version_text = (version_display if version_value else "version unknown") if has_result else ""
            cell_parts.append(
                f'<td title="Version: {html.escape(version_display)}">'
                f'<div class="cell-main">{html.escape(description)}</div>'
                f'<div class="cell-version">{html.escape(version_text)}</div>'
                "</td>"
            )
        cell_html = "".join(cell_parts)
        generated_cell = (
            f'<td class="run-generated" data-sort="{html.escape(generated_sort_value)}" '
            f'title="{html.escape(generated_title)}">'
            f"{html.escape(generated_display)}</td>"
        )
        body_rows.append(
            "<tr>"
            f'<td class="run-system" title="{system_details}">{system_html}</td>'
            f'<td class="run-presets">{preset_html}</td>'
            f"{generated_cell}"
            f"{cell_html}"
            f'<td class="run-file"><a href="{html.escape(row["file"])}">{html.escape(row["file"])}</a></td>'
            "</tr>"
        )
    return body_rows


def _graph_label_for_system(system: dict[str, object], bench_type: BenchmarkType) -> str:
    """Build a compact label (CPU/GPU with hostname)."""
    hostname = _as_str(system.get("hostname", ""))
    base_label = _format_cpu_label(system) if bench_type in CPU_BENCHMARK_TYPES else _format_gpu_label(system)
    if not base_label:
        base_label = "Unknown CPU" if bench_type in CPU_BENCHMARK_TYPES else "Unknown GPU"
    suffix_parts = [part for part in (hostname, _as_str(system.get("machine", ""))) if part]
    suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
    return f"{base_label}{suffix}"


def _collect_graph_series(
    reports: list[ReportRow],
    benchmark_types: Iterable[BenchmarkType],
) -> dict[BenchmarkType, list[GraphBar]]:
    """Collect per-benchmark series for chart rendering."""
    series: dict[BenchmarkType, list[GraphBar]] = defaultdict(list)
    for report in reports:
        system = report["system"]
        system_meta = _system_meta_line(system)
        for bench in report.get("benchmark_results", []):
            if bench.benchmark_type not in benchmark_types:
                continue
            rule = get_score_rule(bench.benchmark_type)
            if not rule:
                continue
            score_value = rule.extract(bench)
            if score_value is None:
                continue
            label = _graph_label_for_system(system, bench.benchmark_type)
            series[bench.benchmark_type].append(
                {
                    "label": label,
                    "value": score_value,
                    "display": rule.format_value(score_value),
                    "report_file": report["file"],
                    "system_meta": system_meta or "System details unavailable",
                }
            )
    return series


def _normalize_width(value: float, min_value: float, max_value: float, higher_is_better: bool) -> float:
    """Convert raw values to a bar width percentage."""
    min_width = 10.0
    if higher_is_better:
        if max_value <= 0:
            return 100.0
        width = (value / max_value) * 100
    else:
        positive_min = min((v for v in (min_value, max_value, value) if v > 0), default=None)
        baseline = positive_min if positive_min is not None else (min_value if min_value != 0 else 1.0)
        width = (baseline / value) * 100 if value else 100.0
    return max(min_width, min(100.0, width))


def _build_graph_section(
    title: str,
    bench_types: Iterable[BenchmarkType],
    series: dict[BenchmarkType, list[GraphBar]],
) -> str:
    cards: list[str] = []
    for bench_type in bench_types:
        bars = series.get(bench_type, [])
        if not bars:
            continue
        rule = get_score_rule(bench_type)
        if not rule:
            continue
        sorted_bars = sorted(bars, key=lambda bar: bar["value"], reverse=rule.higher_is_better)
        values = [bar["value"] for bar in sorted_bars]
        max_value = max(values)
        min_value = min(values)
        direction_text = "Higher is better" if rule.higher_is_better else "Lower is better"
        bench_instance = BENCHMARK_MAP.get(bench_type)
        bench_title = bench_instance.description if bench_instance else bench_type.value

        bar_html_parts: list[str] = []
        for bar in sorted_bars:
            width_pct = _normalize_width(bar["value"], min_value, max_value, rule.higher_is_better)
            tooltip_lines = [
                f"Score: {bar['display']}",
                direction_text,
                f"Report: {bar['report_file']}",
                bar["system_meta"],
            ]
            tooltip = " &#10;".join(html.escape(line) for line in tooltip_lines if line)
            bar_html_parts.append(
                f'<div class="bar-row" title="{tooltip}">'
                f'<div class="bar-label">{html.escape(bar["label"])}</div>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{width_pct:.1f}%;"></div></div>'
                f'<div class="bar-value">{html.escape(bar["display"])}</div>'
                "</div>"
            )

        cards.append(
            '<section class="chart-card">'
            '<header class="chart-card-header">'
            f'<div class="chart-title">{html.escape(bench_title)}</div>'
            f'<div class="chart-subtitle">{html.escape(rule.label)} · {html.escape(direction_text)}</div>'
            "</header>"
            f'<div class="bar-list">{"".join(bar_html_parts)}</div>'
            "</section>"
        )

    if not cards:
        return ""

    return (
        '<section class="chart-section">'
        '<div class="chart-heading">'
        f"<h2>{html.escape(title)}</h2>"
        '<p class="chart-note">Sorted best to worst based on reported scores.</p>'
        "</div>"
        f'<div class="chart-grid">{"".join(cards)}</div>'
        "</section>"
    )


def _build_graphs(reports: list[ReportRow]) -> str:
    """Build HTML for CPU/GPU comparison charts."""
    cpu_series = _collect_graph_series(reports, CPU_BENCHMARK_TYPES)
    gpu_series = _collect_graph_series(reports, GPU_BENCHMARK_TYPES)
    sections = [
        _build_graph_section("CPU Benchmarks", CPU_BENCHMARK_TYPES, cpu_series),
        _build_graph_section("GPU Benchmarks", GPU_BENCHMARK_TYPES, gpu_series),
    ]
    return "\n".join(section for section in sections if section)


def _svg_escape(text: str) -> str:
    return html.escape(text, quote=True)


def _wrap_label(text: str, max_len: int = 32) -> list[str]:
    """Wrap labels at word boundaries for better readability."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word]) if current else word
        if len(candidate) <= max_len:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _render_svg_chart(title: str, subtitle: str, bars: list[GraphBar], rule: ScoreRule) -> str:
    """Render a single bar chart as an SVG image."""
    bar_height = 28
    bar_gap = 12
    left_pad = 380
    right_pad = 150
    track_width = 760
    chart_width = left_pad + track_width + right_pad
    header_height = 54
    body_height = len(bars) * (bar_height + bar_gap)
    total_height = header_height + body_height + 20

    values = [bar["value"] for bar in bars]
    max_value = max(values)
    min_value = min(values)

    bar_elements: list[str] = []
    y = header_height
    for bar in bars:
        width_pct = _normalize_width(bar["value"], min_value, max_value, rule.higher_is_better)
        fill_width = (width_pct / 100.0) * track_width
        label_lines = _wrap_label(bar["label"])
        label_text = "".join(
            f'<tspan x="12" dy="{0 if idx == 0 else 16}">{_svg_escape(line)}</tspan>'
            for idx, line in enumerate(label_lines)
        )
        bar_elements.append(
            f'<g transform="translate(0,{y})" aria-label="{_svg_escape(bar["label"])}">'
            f'<text y="{bar_height / 2 + 4}" font-size="14" font-family="system-ui,sans-serif" '
            f'fill="#0f172a">{label_text}</text>'
            f'<rect x="{left_pad}" y="4" width="{track_width}" height="{bar_height}" rx="6" '
            f'fill="#e5e7eb" />'
            f'<rect x="{left_pad}" y="4" width="{fill_width:.1f}" height="{bar_height}" rx="6" '
            f'fill="url(#barGradient)" />'
            f'<text x="{left_pad + track_width + 10}" y="{bar_height / 2 + 5}" '
            f'font-size="14" font-family="system-ui,sans-serif" font-weight="700" fill="#111827">'
            f"{_svg_escape(bar['display'])}"
            "</text>"
            "</g>"
        )
        y += bar_height + bar_gap

    direction_text = "Higher is better" if rule.higher_is_better else "Lower is better"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{chart_width}" height="{total_height}" '
        f'viewBox="0 0 {chart_width} {total_height}">'
        "<defs>"
        '<linearGradient id="barGradient" x1="0%" x2="100%" y1="0%" y2="0%">'
        '<stop offset="0%" stop-color="#1da1f2"/>'
        '<stop offset="50%" stop-color="#3b82f6"/>'
        '<stop offset="100%" stop-color="#2563eb"/>'
        "</linearGradient>"
        "</defs>"
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<text x="12" y="24" font-size="17" font-family="system-ui,sans-serif" '
        f'font-weight="700" fill="#0b1221">{_svg_escape(title)}</text>'
        f'<text x="12" y="44" font-size="14" font-family="system-ui,sans-serif" fill="#4b5563">'
        f"{_svg_escape(subtitle)} · {_svg_escape(direction_text)}</text>"
        f"{''.join(bar_elements)}"
        "</svg>"
    )


def _write_svg_charts(base_dir: Path, category: str, series: dict[BenchmarkType, list[GraphBar]]) -> list[Path]:
    """Write per-benchmark SVG charts to disk and return generated paths."""
    if not series:
        return []
    charts_dir = base_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for bench_type, bars in series.items():
        if not bars:
            continue
        rule = get_score_rule(bench_type)
        if not rule:
            continue
        bench_instance = BENCHMARK_MAP.get(bench_type)
        bench_title = bench_instance.description if bench_instance else bench_type.value
        sorted_bars = sorted(bars, key=lambda bar: bar["value"], reverse=rule.higher_is_better)
        subtitle = rule.label
        svg = _render_svg_chart(bench_title, subtitle, sorted_bars, rule)
        filename = sanitize_for_filename(f"{category}-{bench_type.value}.svg")
        output_path = charts_dir / filename
        output_path.write_text(svg)
        generated.append(output_path)

    return generated


def _convert_svg_to_png(svg_paths: list[Path]) -> list[Path]:
    """Convert SVG charts to PNG using ImageMagick if available."""
    converter = shutil.which("convert") or shutil.which("magick")
    if not converter:
        return []

    png_paths: list[Path] = []
    for svg_path in svg_paths:
        png_path = svg_path.with_suffix(".png")
        try:
            completed = subprocess.run(
                [converter, "-density", "220", "-background", "white", svg_path, png_path],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if completed.returncode == 0 and png_path.exists():
                png_paths.append(png_path)
        except (OSError, subprocess.SubprocessError):
            continue
    return png_paths


def _render_html_document(
    header_cells: str,
    table_html: str,
) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>NixOS Benchmark Runs</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1f2429; background: #fdfdfd; }}
    h1 {{ margin: 0 0 1rem; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #d9d9d9; }}
    th, td {{ border: 1px solid #e3e3e3; padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }}
    th {{ background: #f4f6f8; font-weight: 700; }}
    tr:nth-child(even) {{ background: #fbfbfc; }}

    .run-file a {{ color: #0b73e0; text-decoration: none; }}
    .run-file a:hover {{ text-decoration: underline; }}
    .run-generated {{ white-space: nowrap; color: #3c4650; }}
    .run-system {{ min-width: 16rem; }}
    .system-label {{ font-weight: 700; }}
    .system-meta {{ color: #5a646f; font-size: 0.9rem; margin-top: 0.1rem; line-height: 1.25; }}
    .run-presets .preset-label {{ color: #1f2429; font-size: 0.95rem; }}
    .cell-main {{ font-weight: 600; }}
    .cell-version {{ color: #5a646f; font-size: 0.8rem; margin-top: 0.2rem; }}

    /* Sortable headers */
    th.sortable {{
      cursor: pointer;
      user-select: none;
      position: relative;
    }}

    th.sortable::after {{
      content: "";
      position: absolute;
      right: 0.4rem;
      font-size: 0.7rem;
      opacity: 0.4;
    }}

    th.sortable[data-order="asc"]::after {{
      content: "▲";
    }}

    th.sortable[data-order="desc"]::after {{
      content: "▼";
    }}
  </style>
</head>
<body>
  <h1>Benchmark Runs</h1>
  <table id="benchmark-table">
    <thead>
      <tr>
        <th class="sortable" data-type="text">System</th>
        <th class="sortable" data-type="text">Presets</th>
        <th class="sortable run-generated-header" data-type="date">Run Date</th>
        {header_cells}
        <th class="sortable" data-type="text">Report</th>
      </tr>
    </thead>
    <tbody>
      {table_html}
    </tbody>
  </table>
  <script>
    document.addEventListener('DOMContentLoaded', function () {{
      const table = document.getElementById('benchmark-table');
      const headers = Array.from(table.querySelectorAll('thead th'));
      const tbody = table.querySelector('tbody');

      function getCellValue(row, index) {{
        const cell = row.children[index];
        const sortValue = cell.getAttribute('data-sort');
        return (sortValue || cell.textContent).trim();
      }}

      function parseValue(value, type) {{
        if (type === 'date') {{
          const t = Date.parse(value);
          return isNaN(t) ? 0 : t;
        }}

        if (type === 'number') {{
          const m = value.match(/-?\\d+(\\.\\d+)?/);
          if (m) return parseFloat(m[0]);
        }}

        // default: text
        return value.toLowerCase();
      }}

      function sortByColumn(index, type, order) {{
        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {{
          const va = parseValue(getCellValue(a, index), type);
          const vb = parseValue(getCellValue(b, index), type);

          if (va < vb) return order === 'asc' ? -1 : 1;
          if (va > vb) return order === 'asc' ? 1 : -1;
          return 0;
        }});

        rows.forEach(row => tbody.appendChild(row));
      }}

      headers.forEach((header, index) => {{
        if (!header.classList.contains('sortable')) return;
        header.addEventListener('click', () => {{
          const currentOrder = header.getAttribute('data-order') === 'asc' ? 'asc' : 'desc';
          const newOrder = currentOrder === 'asc' ? 'desc' : 'asc';
          const type = header.getAttribute('data-type') || 'text';

          // reset other headers
          headers.forEach(h => {{
            if (h !== header) h.removeAttribute('data-order');
          }});

          header.setAttribute('data-order', newOrder);
          sortByColumn(index, type, newOrder);
        }});
      }});

      // Default sort: by Run Date column, newest first
      const generatedHeader = headers.find(h => h.classList.contains('run-generated-header'));
      if (generatedHeader) {{
        const generatedIndex = headers.indexOf(generatedHeader);
        generatedHeader.setAttribute('data-order', 'desc');
        sortByColumn(generatedIndex, generatedHeader.getAttribute('data-type') || 'date', 'desc');
      }}
    }});
  </script>
</body>
</html>
"""


def build_html_summary(results_dir: Path, html_path: Path) -> None:
    """Build HTML dashboard summarizing all benchmark runs in results_dir."""
    json_files = sorted(results_dir.glob("*.json"))
    default_timestamp = UNKNOWN_TIMESTAMP

    reports, bench_metadata = _load_reports_and_metadata(json_files, default_timestamp)
    bench_columns = sorted(bench_metadata.keys())
    if not reports or not bench_columns:
        return

    rows = _build_rows(reports, bench_columns)

    html_path.parent.mkdir(parents=True, exist_ok=True)

    header_cells = _build_header_cells(bench_columns, bench_metadata)
    body_rows = _build_body_rows(rows)
    table_html = "\n".join(body_rows)
    cpu_series = _collect_graph_series(reports, CPU_BENCHMARK_TYPES)
    gpu_series = _collect_graph_series(reports, GPU_BENCHMARK_TYPES)
    generated_svgs = []
    generated_svgs.extend(_write_svg_charts(html_path.parent, "cpu", cpu_series))
    generated_svgs.extend(_write_svg_charts(html_path.parent, "gpu", gpu_series))
    generated_pngs = _convert_svg_to_png(generated_svgs)
    chart_files = generated_pngs or generated_svgs
    document = _render_html_document(header_cells, table_html)

    html_path.write_text(document)
    print(f"Updated {html_path} ({len(rows)} runs tracked)")
    if chart_files:
        print(f"Wrote {len(chart_files)} chart file(s) to {chart_files[0].parent}/")
