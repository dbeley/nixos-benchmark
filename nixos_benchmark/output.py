"""Output generation for JSON and HTML reports."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
)


def sanitize_for_filename(value: str) -> str:
    """Sanitize a string to be safe for use in filenames."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


def describe_benchmark(bench: BenchmarkResult) -> str:
    """Generate a short human-readable description of benchmark results.

    This function looks up the benchmark class by name and delegates to
    its format_result method. If the benchmark is not found, returns an
    empty string.
    """
    # Import here to avoid circular dependency
    from .benchmarks import ALL_BENCHMARKS  # noqa: PLC0415

    # Find the matching benchmark class
    for benchmark_instance in ALL_BENCHMARKS:
        if benchmark_instance.name == bench.name:
            return benchmark_instance.format_result(bench)

    # Fallback for unknown benchmarks
    if bench.status != "ok":
        prefix = "Skipped" if bench.status == "skipped" else "Error"
        return f"{prefix}: {bench.message}"
    return ""


def write_json_report(report: BenchmarkReport, output_path: Path) -> None:
    """Write benchmark report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2))


def build_html_summary(results_dir: Path, html_path: Path) -> None:
    """Build HTML dashboard summarizing all benchmark runs in results_dir."""
    json_files = sorted(results_dir.glob("*.json"))
    reports = []
    bench_metadata: dict[str, dict[str, set[str]]] = {}

    for path in json_files:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        reports.append((path, data))
        for bench in data.get("benchmarks", []):
            name = bench.get("name", "")
            if not name:
                continue
            meta = bench_metadata.setdefault(name, {"presets": set()})
            meta["presets"].update(bench.get("presets", []))

    bench_columns = sorted(bench_metadata.keys())
    if not reports or not bench_columns:
        return

    rows = []
    for path, data in reports:
        bench_map = {bench.get("name"): bench for bench in data.get("benchmarks", [])}
        cells = []
        for bench_name in bench_columns:
            bench_dict = bench_map.get(bench_name, {})
            # Convert dict to BenchmarkResult for describe_benchmark
            if bench_dict:
                bench_result = BenchmarkResult(
                    name=bench_dict.get("name", ""),
                    status=bench_dict.get("status", "ok"),
                    presets=tuple(bench_dict.get("presets", [])),
                    metrics=BenchmarkMetrics(bench_dict.get("metrics", {})),
                    parameters=BenchmarkParameters(bench_dict.get("parameters", {})),
                    duration_seconds=bench_dict.get("duration_seconds", 0.0),
                    command=bench_dict.get("command", ""),
                    message=bench_dict.get("message", ""),
                    raw_output=bench_dict.get("raw_output", ""),
                )
                description = describe_benchmark(bench_result)
            else:
                description = ""
            cells.append(description or "—")
        rows.append(
            {
                "file": path.name,
                "generated": data.get("generated_at", "unknown"),
                "system": data.get("system", {}),
                "presets": data.get("presets_requested", []),
                "cells": cells,
            }
        )

    html_path.parent.mkdir(parents=True, exist_ok=True)

    # Build header cells for benchmark columns
    header_cells = ""
    for name in bench_columns:
        meta = bench_metadata.get(name, {"presets": set()})
        preset_label = ", ".join(sorted(meta.get("presets", []))) or "unspecified"
        header_cells += (
            f'<th class="sortable" data-type="text" '
            f'title="Presets: {html.escape(preset_label)}">'
            f"{html.escape(name)}"
            "</th>"
        )

    # Build body rows
    body_rows = []
    for row in rows:
        system = row["system"]
        system_label = f"{system.get('hostname', '')} ({system.get('machine', '')})"
        preset_label = ", ".join(row.get("presets", [])) or "n/a"
        cell_html = "".join(f"<td>{html.escape(value)}</td>" for value in row["cells"])
        body_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(row["file"])}">{html.escape(row["file"])}</a></td>'
            f"<td>{html.escape(row['generated'])}</td>"
            f"<td>{html.escape(system_label)}</td>"
            f"<td>{html.escape(preset_label)}</td>"
            f"{cell_html}"
            "</tr>"
        )

    table_html = "\n".join(body_rows)

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>NixOS Benchmark Runs</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }}
    th {{ background: #f3f3f3; }}
    tr:nth-child(even) {{ background: #fafafa; }}

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
    html_path.write_text(document)
    print(f"Updated {html_path} ({len(rows)} runs tracked)")
