#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


def run_command(command: List[str]) -> Tuple[str, float]:
    start = time.perf_counter()
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    duration = time.perf_counter() - start
    return completed.stdout, duration


def parse_openssl_output(output: str, algorithm: str) -> Dict[str, float]:
    pattern = rf"^{re.escape(algorithm)}\s+(.+)$"
    match = re.search(pattern, output, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to find throughput table for {algorithm!r}")

    values_str = match.group(1).split()
    block_sizes = ["16B", "64B", "256B", "1KiB", "8KiB", "16KiB"]
    values = {}
    for size, token in zip(block_sizes, values_str):
        values[size] = float(token.rstrip("k"))

    values["max_kbytes_per_sec"] = max(values.values())
    return values


def parse_7zip_output(output: str) -> Dict[str, float]:
    totals_match = re.search(r"Tot:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", output)
    avg_match = re.search(
        r"Avr:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\|\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
        output,
    )
    result: Dict[str, float] = {}

    if totals_match:
        result["total_usage_pct"] = float(totals_match.group(1))
        result["total_ru"] = float(totals_match.group(2))
        result["total_rating_mips"] = float(totals_match.group(3))

    if avg_match:
        result["compress_usage_pct"] = float(avg_match.group(1))
        result["compress_ru_mips"] = float(avg_match.group(2))
        result["compress_rating_mips"] = float(avg_match.group(3))
        result["decompress_usage_pct"] = float(avg_match.group(4))
        result["decompress_ru_mips"] = float(avg_match.group(5))
        result["decompress_rating_mips"] = float(avg_match.group(6))

    if not result:
        raise ValueError("Unable to parse 7-Zip benchmark output")

    return result


def parse_stress_ng_output(output: str) -> Dict[str, float]:
    for line in output.splitlines():
        if "stress-ng: metrc:" not in line:
            continue
        tokens = line.split()
        if len(tokens) < 10:
            continue
        stressor_name = tokens[3]
        if stressor_name == "stressor" or stressor_name.startswith("("):
            continue
        return {
            "stressor": stressor_name,
            "bogo_ops": float(tokens[4]),
            "real_time_secs": float(tokens[5]),
            "user_time_secs": float(tokens[6]),
            "system_time_secs": float(tokens[7]),
            "bogo_ops_per_sec_real": float(tokens[8]),
            "bogo_ops_per_sec_cpu": float(tokens[9]),
        }
    raise ValueError("Unable to parse stress-ng metrics (try increasing runtime)")


def run_openssl(seconds: int, algorithm: str) -> Dict[str, object]:
    command = ["openssl", "speed", "-elapsed", "-seconds", str(seconds), algorithm]
    stdout, duration = run_command(command)
    metrics = parse_openssl_output(stdout, algorithm)
    return {
        "name": "openssl-speed",
        "command": " ".join(command),
        "parameters": {"seconds": seconds, "algorithm": algorithm},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_7zip() -> Dict[str, object]:
    command = ["7z", "b"]
    stdout, duration = run_command(command)
    metrics = parse_7zip_output(stdout)
    return {
        "name": "7zip-benchmark",
        "command": " ".join(command),
        "parameters": {},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_stress_ng(seconds: int, method: str) -> Dict[str, object]:
    command = [
        "stress-ng",
        "--cpu",
        "0",
        "--cpu-method",
        method,
        "--timeout",
        f"{seconds}s",
        "--metrics-brief",
    ]
    stdout, duration = run_command(command)
    metrics = parse_stress_ng_output(stdout)
    return {
        "name": "stress-ng",
        "command": " ".join(command),
        "parameters": {"seconds": seconds, "cpu_method": method},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_fio(size_mb: int, runtime: int, block_kb: int) -> Dict[str, object]:
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    data_file = results_dir / "fio-testfile.bin"

    job_text = (
        "[global]\n"
        "ioengine=sync\n"
        "direct=0\n"
        f"size={size_mb}m\n"
        f"runtime={runtime}\n"
        "time_based=1\n"
        "group_reporting=1\n"
        f"bs={block_kb}k\n"
        f"filename={data_file}\n"
        "\n"
        "[seqwrite]\n"
        "rw=write\n"
        "\n"
        "[seqread]\n"
        "rw=read\n"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".fio") as tmp:
        job_path = Path(tmp.name)
        tmp.write(job_text.encode("utf-8"))

    try:
        stdout, duration = run_command(["fio", "--output-format=json", str(job_path)])
        data = json.loads(stdout)
    finally:
        job_path.unlink(missing_ok=True)
        if data_file.exists():
            data_file.unlink()

    jobs = data.get("jobs", [])
    if not jobs:
        raise ValueError("fio output missing job data")

    aggregate = jobs[0]
    read_stats = aggregate.get("read", {})
    write_stats = aggregate.get("write", {})

    metrics = {
        "seqwrite_mib_per_s": float(write_stats.get("bw", 0.0)) / 1024,
        "seqwrite_iops": float(write_stats.get("iops", 0.0)),
        "seqread_mib_per_s": float(read_stats.get("bw", 0.0)) / 1024,
        "seqread_iops": float(read_stats.get("iops", 0.0)),
    }

    return {
        "name": "fio-seq",
        "command": f"fio --output-format=json {job_path}",
        "parameters": {"size_mb": size_mb, "runtime_s": runtime, "block_kb": block_kb},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_glmark2_output(output: str) -> Dict[str, float]:
    match = re.search(r"glmark2 Score:\s+(\d+)", output)
    if not match:
        raise ValueError("Unable to parse glmark2 score from output")
    return {"score": float(match.group(1))}


def run_glmark2(size: str, offscreen: bool) -> Dict[str, object]:
    command = ["glmark2", "-s", size]
    if offscreen:
        command.append("--off-screen")
    stdout, duration = run_command(command)
    metrics = parse_glmark2_output(stdout)
    return {
        "name": "glmark2",
        "command": " ".join(command),
        "parameters": {"size": size, "mode": "offscreen" if offscreen else "onscreen"},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def gather_system_info(hostname_override: str | None = None) -> Dict[str, object]:
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "hostname": platform.node(),
    }
    if hostname_override:
        info["hostname"] = hostname_override
    return info


def sanitize_for_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug


def describe_benchmark(bench: Dict[str, object]) -> str:
    metrics = bench.get("metrics", {})
    name = bench.get("name", "")
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
    elif name == "fio-seq":
        read_bw = metrics.get("seqread_mib_per_s")
        write_bw = metrics.get("seqwrite_mib_per_s")
        if read_bw is not None and write_bw is not None:
            return f"R {read_bw:.1f} / W {write_bw:.1f} MiB/s"
    elif name == "glmark2":
        score = metrics.get("score")
        if score is not None:
            return f"{score:.0f} pts"
    return ""


def build_html_summary(results_dir: Path, html_path: Path) -> None:
    json_files = sorted(results_dir.glob("*.json"))
    reports = []
    bench_names = set()
    for path in json_files:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        reports.append((path, data))
        for bench in data.get("benchmarks", []):
            bench_names.add(bench.get("name", ""))

    bench_columns = sorted(filter(None, bench_names))
    if not reports or not bench_columns:
        return

    rows = []
    for path, data in reports:
        bench_map = {bench.get("name"): bench for bench in data.get("benchmarks", [])}
        cells = []
        for bench_name in bench_columns:
            description = describe_benchmark(bench_map.get(bench_name, {}))
            cells.append(description or "—")
        rows.append(
            {
                "file": path.name,
                "generated": data.get("generated_at", "unknown"),
                "system": data.get("system", {}),
                "cells": cells,
            }
        )

    html_path.parent.mkdir(parents=True, exist_ok=True)
    header_cells = "".join(f"<th>{html.escape(name)}</th>" for name in bench_columns)
    body_rows = []
    for row in rows:
        system = row["system"]
        system_label = f"{system.get('hostname', '')} ({system.get('machine', '')})"
        cell_html = "".join(f"<td>{html.escape(value)}</td>" for value in row["cells"])
        body_rows.append(
            "<tr>"
            f"<td><a href=\"{html.escape(row['file'])}\">{html.escape(row['file'])}</a></td>"
            f"<td>{html.escape(row['generated'])}</td>"
            f"<td>{html.escape(system_label)}</td>"
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
  </style>
</head>
<body>
  <h1>Benchmark Runs</h1>
  <table>
    <thead>
      <tr>
        <th>Result</th>
        <th>Generated</th>
        <th>System</th>
        {header_cells}
      </tr>
    </thead>
    <tbody>
      {table_html}
    </tbody>
  </table>
</body>
</html>
"""
    html_path.write_text(document)
    print(f"Updated {html_path} ({len(rows)} runs tracked)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a lightweight benchmark suite.")
    parser.add_argument(
        "--openssl-seconds",
        type=int,
        default=3,
        help="Duration to run openssl speed for each algorithm.",
    )
    parser.add_argument(
        "--openssl-algorithm",
        default="aes-256-cbc",
        help="Algorithm to benchmark with openssl speed.",
    )
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
    parser.add_argument("--skip-7zip", action="store_true", help="Skip the 7-Zip benchmark.")
    parser.add_argument(
        "--skip-openssl",
        action="store_true",
        help="Skip running the OpenSSL benchmark.",
    )
    parser.add_argument(
        "--skip-stress-ng",
        action="store_true",
        help="Skip the stress-ng CPU saturation test.",
    )
    parser.add_argument(
        "--stress-ng-seconds",
        type=int,
        default=5,
        help="stress-ng runtime for the CPU test.",
    )
    parser.add_argument(
        "--stress-ng-method",
        default="fft",
        help="stress-ng CPU method (see stress-ng --cpu-method help).",
    )
    parser.add_argument(
        "--skip-fio",
        action="store_true",
        help="Skip the fio sequential read/write benchmark.",
    )
    parser.add_argument("--fio-size-mb", type=int, default=64, help="fio working-set size (MiB).")
    parser.add_argument("--fio-runtime", type=int, default=5, help="fio runtime per job (seconds).")
    parser.add_argument(
        "--fio-block-kb",
        type=int,
        default=1024,
        help="fio block size (KiB).",
    )
    parser.add_argument(
        "--skip-glmark2",
        action="store_true",
        help="Skip the glmark2 GPU benchmark.",
    )
    parser.add_argument(
        "--glmark2-size",
        default="1920x1080",
        help="Resolution for glmark2 runs (e.g. 1920x1080).",
    )
    parser.add_argument(
        "--glmark2-mode",
        choices=("offscreen", "onscreen"),
        default="offscreen",
        help="Rendering mode for glmark2 (offscreen avoids taking over the display).",
    )
    args = parser.parse_args()

    results: List[Dict[str, object]] = []

    if not args.skip_openssl:
        results.append(run_openssl(args.openssl_seconds, args.openssl_algorithm))

    if not args.skip_7zip:
        results.append(run_7zip())

    if not args.skip_stress_ng:
        results.append(run_stress_ng(args.stress_ng_seconds, args.stress_ng_method))

    if not args.skip_fio:
        results.append(run_fio(args.fio_size_mb, args.fio_runtime, args.fio_block_kb))

    if not args.skip_glmark2:
        results.append(run_glmark2(args.glmark2_size, args.glmark2_mode == "offscreen"))

    if not results:
        print("No benchmarks requested.", file=sys.stderr)
        return 1

    generated_at = datetime.now(timezone.utc)
    system_info = gather_system_info(args.hostname or None)
    report = {
        "generated_at": generated_at.isoformat(),
        "system": system_info,
        "benchmarks": results,
    }

    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = generated_at.strftime("%Y%m%d-%H%M%S")
        hostname_slug = sanitize_for_filename(system_info.get("hostname", ""))
        filename = f"{timestamp}.json"
        if hostname_slug:
            filename = f"{timestamp}-{hostname_slug}.json"
        output_path = Path("results") / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))

    print(f"Wrote {output_path}")
    for bench in results:
        summary = describe_benchmark(bench)
        if summary:
            print(f"{bench['name']}: {summary}")

    if args.html_summary:
        build_html_summary(output_path.parent, Path(args.html_summary))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
