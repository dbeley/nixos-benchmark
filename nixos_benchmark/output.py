"""Output generation for JSON and HTML reports."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from datetime import datetime

from .benchmarks import BENCHMARK_MAP, BenchmarkType
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
    """Extract the human-readable score of a benchmark result."""
    benchmark_instance = BENCHMARK_MAP.get(bench.benchmark_type)
    if benchmark_instance:
        return benchmark_instance.format_result(bench)

    # Fallback for unknown benchmarks
    if bench.status != "ok":
        prefix = "Skipped" if bench.status == "skipped" else "Error"
        return f"{prefix}: {bench.message}"
    return ""


def _benchmark_type_from_name(name: str) -> BenchmarkType | None:
    try:
        return BenchmarkType(name)
    except ValueError:
        return None


def write_json_report(report: BenchmarkReport, output_path: Path) -> None:
    """Write benchmark report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2))


def build_html_summary(results_dir: Path, html_path: Path) -> None:
    """Build HTML dashboard summarizing all benchmark runs in results_dir."""
    json_files = sorted(results_dir.glob("*.json"))
    reports = []
    bench_metadata: dict[str, dict[str, set[str]]] = {}
    default_timestamp = datetime.min

    def _parse_generated(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return default_timestamp

    for path in json_files:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        reports.append((path, data))
        for bench in data.get("benchmarks", []):
            name = bench.get("name", "")
            bench_type = _benchmark_type_from_name(name)
            if not name or bench_type is None:
                continue
            meta = bench_metadata.setdefault(name, {"presets": set(), "versions": set()})
            meta["presets"].update(bench.get("presets", []))
            version = bench.get("version")
            if version:
                meta["versions"].add(str(version))

    bench_columns = sorted(bench_metadata.keys())
    if not reports or not bench_columns:
        return

    rows = []
    for path, data in reports:
        bench_map = {bench.get("name"): bench for bench in data.get("benchmarks", [])}
        cells = []
        for bench_name in bench_columns:
            bench_dict = bench_map.get(bench_name, {})
            version_value = str(bench_dict.get("version", "") or "")
            # Convert dict to BenchmarkResult for describe_benchmark
            description = ""
            if bench_dict:
                bench_type = _benchmark_type_from_name(bench_dict.get("name", ""))
                if bench_type is not None:
                    bench_result = BenchmarkResult(
                        benchmark_type=bench_type,
                        status=bench_dict.get("status", "ok"),
                        presets=tuple(bench_dict.get("presets", [])),
                        metrics=BenchmarkMetrics(bench_dict.get("metrics", {})),
                        parameters=BenchmarkParameters(bench_dict.get("parameters", {})),
                        duration_seconds=bench_dict.get("duration_seconds", 0.0),
                        command=bench_dict.get("command", ""),
                        message=bench_dict.get("message", ""),
                        raw_output=bench_dict.get("raw_output", ""),
                        version=bench_dict.get("version", ""),
                    )
                    description = describe_benchmark(bench_result)
            cells.append({"text": description or "—", "version": version_value})
        rows.append(
            {
                "file": path.name,
                "generated": data.get("generated_at", "unknown"),
                "generated_dt": _parse_generated(data.get("generated_at", "unknown")),
                "system": data.get("system", {}),
                "presets": data.get("presets_requested", []),
                "cells": cells,
            }
        )

    html_path.parent.mkdir(parents=True, exist_ok=True)

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

    system_summary_html = ""
    if rows:
        latest_row = max(rows, key=lambda row: row.get("generated_dt", default_timestamp) or default_timestamp)
        latest_system = latest_row.get("system", {})
        gpus = latest_system.get("gpus") or []
        gpu_label: str
        if isinstance(gpus, (list, tuple)):
            gpu_label = " / ".join(str(gpu) for gpu in gpus if str(gpu).strip()) or "Unknown GPU"
        else:
            gpu_label = str(gpus) if gpus else "Unknown GPU"
        cpu_label = str(latest_system.get("cpu_model") or latest_system.get("processor") or "Unknown CPU")
        os_label = str(latest_system.get("os_name") or latest_system.get("platform") or "Unknown OS")
        os_version = str(latest_system.get("os_version") or "")
        if os_version:
            os_label = f"{os_label} {os_version}".strip()
        kernel_label = str(latest_system.get("kernel_version") or latest_system.get("platform") or "")
        ram_label = _format_memory_label(latest_system.get("memory_total_bytes"))
        subtitle_bits = [f"Latest run: {latest_row.get('file', 'n/a')} · {latest_row.get('generated', 'unknown')}"]
        hostnames = {str(r.get("system", {}).get("hostname", "") or "") for r in rows}
        if len({hn for hn in hostnames if hn}) > 1:
            subtitle_bits.append("Multiple systems detected; hover a system name for details.")
        subtitle = " \u00b7 ".join(subtitle_bits)
        system_summary_html = f"""
  <section class="system-summary">
    <div>
      <h2>System Info</h2>
      <p class="summary-subtitle">{html.escape(subtitle)}</p>
    </div>
    <div class="info-grid">
      <div class="info-item">
        <div class="label">CPU</div>
        <div class="value">{html.escape(cpu_label)}</div>
      </div>
      <div class="info-item">
        <div class="label">GPU</div>
        <div class="value">{html.escape(gpu_label)}</div>
      </div>
      <div class="info-item">
        <div class="label">RAM</div>
        <div class="value">{html.escape(ram_label)}</div>
      </div>
      <div class="info-item">
        <div class="label">OS</div>
        <div class="value">{html.escape(os_label)}</div>
      </div>
      <div class="info-item">
        <div class="label">Linux</div>
        <div class="value">{html.escape(kernel_label or 'Unknown')}</div>
      </div>
    </div>
  </section>
"""

    # Build header cells for benchmark columns
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
        header_cells += (
            f'<th class="sortable" data-type="text" '
            f'title="{tooltip}">'
            f"{html.escape(name)}"
            "</th>"
        )

    # Build body rows
    body_rows = []
    for row in rows:
        system = row["system"]
        system_label = _system_cell_label(system)
        system_details = html.escape(_system_details_text(system)).replace("\n", "&#10;")
        preset_label = ", ".join(row.get("presets", [])) or "n/a"
        cell_html = "".join(
            f'<td title="{html.escape(cell.get("version") or "Version unknown")}">'
            f"{html.escape(cell.get('text', '—'))}"
            "</td>"
            for cell in row["cells"]
        )
        body_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(row["file"])}">{html.escape(row["file"])}</a></td>'
            f"<td>{html.escape(row['generated'])}</td>"
            f'<td title="{system_details}">{html.escape(system_label)}</td>'
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
    .system-summary {{
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 1rem 1.25rem;
      margin: 0 0 1.5rem;
      background: linear-gradient(145deg, #fdfdfd, #f5f5f5);
    }}
    .summary-subtitle {{
      margin: 0.2rem 0 0;
      color: #555;
      font-size: 0.95rem;
    }}
    .info-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 0.5rem 1rem;
      margin-top: 0.8rem;
    }}
    .info-item .label {{
      font-size: 0.8rem;
      color: #555;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }}
    .info-item .value {{
      font-weight: 600;
      margin-top: 0.15rem;
    }}
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
  {system_summary_html}
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
