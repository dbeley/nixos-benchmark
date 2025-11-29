"""Output generation for JSON and HTML reports."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Dict, List

from .models import (
    BenchmarkMetrics,
    BenchmarkParameters,
    BenchmarkReport,
    BenchmarkResult,
)


def sanitize_for_filename(value: str) -> str:
    """Sanitize a string to be safe for use in filenames."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug


def describe_benchmark(bench: BenchmarkResult) -> str:
    """Generate a short human-readable description of benchmark results."""
    if bench.status != "ok":
        prefix = "Skipped" if bench.status == "skipped" else "Error"
        return f"{prefix}: {bench.message}"

    metrics = bench.metrics
    name = bench.name

    if name == "openssl-speed":
        throughput = metrics.get("max_kbytes_per_sec")
        if throughput is not None:
            return f"{throughput / 1024:.1f} MiB/s"
    elif name == "7zip-benchmark":
        rating = metrics.get("total_rating_mips")
        if rating is not None:
            return f"{rating:.0f} MIPS"
    elif name == "stress-ng":
        ops = metrics.get("bogo_ops_per_sec_real")
        if ops is not None:
            return f"{ops:,.0f} bogo-ops/s"
    elif name == "sysbench-cpu":
        events = metrics.get("events_per_sec")
        if events is not None:
            return f"{events:,.1f} events/s"
    elif name == "sysbench-memory":
        throughput = metrics.get("throughput_mib_per_s")
        if throughput is not None:
            return f"{throughput:,.0f} MiB/s"
    elif name == "fio-seq":
        read_bw = metrics.get("seqread_mib_per_s")
        write_bw = metrics.get("seqwrite_mib_per_s")
        if read_bw is not None and write_bw is not None:
            return f"R {read_bw:.1f} / W {write_bw:.1f} MiB/s"
    elif name == "glmark2":
        score = metrics.get("score")
        if score is not None:
            return f"{score:.0f} pts"
    elif name == "vkmark":
        fps = metrics.get("fps_avg") or metrics.get("fps_max")
        if fps is not None:
            return f"{fps:.1f} fps"
    elif name == "ffmpeg-transcode":
        fps = metrics.get("calculated_fps")
        if fps is not None:
            return f"{fps:.1f} fps"
    elif name == "x264-encode":
        fps = metrics.get("fps")
        if fps is not None:
            return f"{fps:.1f} fps"
    elif name == "sqlite-mixed":
        inserts = metrics.get("insert_rows_per_s")
        selects = metrics.get("selects_per_s")
        if inserts is not None and selects is not None:
            return f"Ins {inserts:.0f}/s Sel {selects:.0f}/s"
    elif name == "tinymembench":
        memcpy = metrics.get("memcpy_mb_per_s")
        if memcpy is None:
            memcpy = metrics.get("memcpy_-_aligned_mb_per_s")
        if memcpy is None and metrics.data:
            numeric_values = [v for v in metrics.data.values() if isinstance(v, (int, float))]
            if numeric_values:
                memcpy = max(numeric_values)
        if memcpy is not None:
            return f"{memcpy:,.0f} MB/s"
    elif name == "clpeak":
        bandwidth = metrics.get("global_mem_bandwidth_gbps_float")
        if bandwidth is None and metrics.data:
            numeric_values = [v for v in metrics.data.values() if isinstance(v, (int, float))]
            if numeric_values:
                bandwidth = max(numeric_values)
        if bandwidth is not None:
            return f"{bandwidth:.1f} GB/s"
    elif name == "zstd-compress" or name == "pigz-compress":
        comp = metrics.get("compress_mb_per_s")
        decomp = metrics.get("decompress_mb_per_s")
        if comp is not None and decomp is not None:
            return f"C {comp:.0f}/D {decomp:.0f} MB/s"
    elif name == "cryptsetup-benchmark":
        speeds = [
            value
            for key, value in metrics.data.items()
            if key.endswith("_enc_mib_per_s") and isinstance(value, (int, float))
        ]
        if speeds:
            peak = max(speeds)
            return f"{peak:,.0f} MiB/s"
    elif name == "ioping":
        latency = metrics.get("latency_avg_ms")
        if latency is not None:
            return f"{latency:.2f} ms avg"
    elif name == "hdparm":
        cached = metrics.get("cached_read_mb_per_s")
        buffered = metrics.get("buffered_read_mb_per_s")
        if cached is not None and buffered is not None:
            return f"T {cached:.0f}/D {buffered:.0f} MB/s"
    elif name == "fsmark":
        files = metrics.get("files_per_sec")
        if files is not None:
            return f"{files:.0f} files/s"
    elif name == "filebench":
        ops = metrics.get("ops_per_sec")
        if ops is not None:
            return f"{ops:.0f} ops/s"
    elif name == "pgbench":
        tps = metrics.get("tps")
        if tps is not None:
            return f"{tps:.0f} tps"
    elif name == "sqlite-speedtest":
        inserts = metrics.get("insert_rows_per_s")
        selects = metrics.get("indexed_selects_per_s")
        if inserts is not None and selects is not None:
            return f"Ins {inserts:.0f}/Sel {selects:.0f}/s"
    elif name == "iperf3-loopback":
        bw = metrics.get("throughput_mib_per_s")
        if bw is not None:
            return f"{bw:.1f} MiB/s"
    elif name == "netperf":
        mbps = metrics.get("throughput_mbps")
        if mbps is not None:
            return f"{mbps:.1f} Mb/s"
    return ""


def write_json_report(report: BenchmarkReport, output_path: Path) -> None:
    """Write benchmark report to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2))


def build_html_summary(results_dir: Path, html_path: Path) -> None:
    """Build HTML dashboard summarizing all benchmark runs in results_dir."""
    json_files = sorted(results_dir.glob("*.json"))
    reports = []
    bench_metadata: Dict[str, Dict[str, set[str]]] = {}

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
            meta = bench_metadata.setdefault(
                name, {"categories": set(), "presets": set()}
            )
            meta["categories"].update(bench.get("categories", []))
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
                    categories=tuple(bench_dict.get("categories", [])),
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
        meta = bench_metadata.get(name, {"categories": set(), "presets": set()})
        category_label = ", ".join(sorted(meta.get("categories", []))) or "unspecified"
        preset_label = ", ".join(sorted(meta.get("presets", []))) or "unspecified"
        header_cells += (
            f'<th class="sortable" data-type="text" '
            f'title="Presets: {html.escape(preset_label)}">'
            f"{html.escape(name)}<br><small>{html.escape(category_label)}</small>"
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
