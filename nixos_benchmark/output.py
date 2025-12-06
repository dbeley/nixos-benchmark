"""Output generation for JSON and HTML reports."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from .benchmarks import BENCHMARK_MAP, BenchmarkType
from .benchmarks.base import BenchmarkBase
from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
)


class ReportRow(TypedDict):
    file: str
    generated: str
    generated_dt: datetime
    system: dict[str, object]
    presets: list[str]
    benchmarks: list[dict[str, object]]


class Cell(TypedDict):
    text: str
    version: str


class RowWithCells(TypedDict):
    file: str
    generated: str
    generated_dt: datetime
    system: dict[str, object]
    presets: list[str]
    cells: list[Cell]


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

        # basic shape for each row
        reports.append(
            {
                "file": path.name,
                "generated": data.get("generated_at", "unknown"),
                "generated_dt": _parse_generated(data.get("generated_at", "unknown"), default_timestamp),
                "system": data.get("system", {}) or {},
                "presets": presets,
                "benchmarks": benchmarks,
            }
        )

        for bench in benchmarks:
            name = _as_str(bench.get("name", ""))
            bench_type = _benchmark_type_from_name(name)
            if not name or bench_type is None:
                continue
            meta = bench_metadata.setdefault(name, {"presets": set(), "versions": set()})
            meta["presets"].update(_as_str_list(bench.get("presets", [])))
            version = bench.get("version")
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
        bench_map = {_as_str(bench.get("name", "")): bench for bench in report["benchmarks"]}
        cells: list[Cell] = []
        for bench_name in bench_columns:
            bench_dict = bench_map.get(bench_name, {})
            version_value = _as_str(bench_dict.get("version", ""))
            description = ""
            if bench_dict:
                bench_type = _benchmark_type_from_name(_as_str(bench_dict.get("name", "")))
                if bench_type is not None:
                    bench_result = BenchmarkResult(
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
                    description = describe_benchmark(bench_result)
            cells.append({"text": description or "—", "version": version_value})

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

        cell_parts: list[str] = []
        for cell in row["cells"]:
            version_value = _as_str(cell.get("version", ""))
            version_display = version_value or "unknown"
            description = _as_str(cell.get("text", "—")) or "—"
            cell_parts.append(
                f'<td title="Version: {html.escape(version_display)}">'
                f'<div class="cell-main">{html.escape(description)}</div>'
                f'<div class="cell-version">{html.escape(f"v{version_display}" if version_value else "version unknown")}</div>'
                "</td>"
            )
        cell_html = "".join(cell_parts)
        body_rows.append(
            "<tr>"
            f'<td class="run-file"><a href="{html.escape(row["file"])}">{html.escape(row["file"])}</a></td>'
            f'<td class="run-generated">{html.escape(row["generated"])}</td>'
            f'<td class="run-system" title="{system_details}">{system_html}</td>'
            f'<td class="run-presets">{preset_html}</td>'
            f"{cell_html}"
            "</tr>"
        )
    return body_rows


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
        <th class="sortable" data-type="text">Result</th>
        <th class="sortable" data-type="date">Generated</th>
        <th class="sortable" data-type="text">System</th>
        <th class="sortable" data-type="text">Presets</th>
        {header_cells}
      </tr>
    </thead>
    <tbody>
      {table_html}
    </tbody>
  </table>
  <script>
    document.addEventListener('DOMContentLoaded', function () {{
      const table = document.getElementById('benchmark-table');
      const headers = table.querySelectorAll('thead th');
      const tbody = table.querySelector('tbody');

      function getCellValue(row, index) {{
        return row.children[index].textContent.trim();
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

      // Default sort: by Generated (2nd col = index 1), newest first
      const generatedHeader = headers[1];
      generatedHeader.setAttribute('data-order', 'desc');
      sortByColumn(1, generatedHeader.getAttribute('data-type') || 'date', 'desc');
    }});
  </script>
</body>
</html>
"""


def build_html_summary(results_dir: Path, html_path: Path) -> None:
    """Build HTML dashboard summarizing all benchmark runs in results_dir."""
    json_files = sorted(results_dir.glob("*.json"))
    default_timestamp = datetime.min.replace(tzinfo=UTC)

    reports, bench_metadata = _load_reports_and_metadata(json_files, default_timestamp)
    bench_columns = sorted(bench_metadata.keys())
    if not reports or not bench_columns:
        return

    rows = _build_rows(reports, bench_columns)

    html_path.parent.mkdir(parents=True, exist_ok=True)

    header_cells = _build_header_cells(bench_columns, bench_metadata)
    body_rows = _build_body_rows(rows)
    table_html = "\n".join(body_rows)
    document = _render_html_document(header_cells, table_html)

    html_path.write_text(document)
    print(f"Updated {html_path} ({len(rows)} runs tracked)")
