#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import platform
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class BenchmarkDefinition:
    key: str
    categories: Tuple[str, ...]
    presets: Tuple[str, ...]
    description: str
    runner: Callable[[argparse.Namespace], Dict[str, object]]
    requires: Tuple[str, ...] = ()
    availability_check: Callable[[argparse.Namespace], Tuple[bool, str]] | None = None


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def check_requirements(commands: Sequence[str]) -> Tuple[bool, str]:
    for cmd in commands:
        if not command_exists(cmd):
            return False, f"Command {cmd!r} was not found in PATH"
    return True, ""


def build_status_entry(
    definition: BenchmarkDefinition,
    status: str,
    message: str,
) -> Dict[str, object]:
    return {
        "name": definition.key,
        "status": status,
        "message": message,
        "categories": list(definition.categories),
        "presets": list(definition.presets),
        "metrics": {},
        "parameters": {},
    }


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


def run_speedtest_cli(server_id: str | None) -> Dict[str, object]:
    command = ["speedtest-cli", "--json"]
    if server_id:
        command.extend(["--server", str(server_id)])
    stdout, duration = run_command(command)
    payload = json.loads(stdout)
    metrics = {
        "download_mbps": float(payload.get("download", 0.0)) / 1_000_000,
        "upload_mbps": float(payload.get("upload", 0.0)) / 1_000_000,
        "ping_ms": float(payload.get("ping", 0.0)),
        "server": payload.get("server", {}).get("host", ""),
    }
    return {
        "name": "speedtest-cli",
        "command": " ".join(command),
        "parameters": {"server": server_id or "auto"},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_kernel_build(kernel_source: str, target: str, jobs: int) -> Dict[str, object]:
    source_path = Path(kernel_source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(kernel_source)
    command = [
        "make",
        "-C",
        str(source_path),
        f"-j{jobs}",
        target,
    ]
    stdout, duration = run_command(command)
    return {
        "name": "linux-kernel-build",
        "command": " ".join(command),
        "parameters": {
            "source": str(source_path),
            "target": target,
            "jobs": jobs,
        },
        "metrics": {"build_time_seconds": duration},
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_ffmpeg_progress(output: str) -> Dict[str, float]:
    fps_matches = re.findall(r"fps=\s*([\d.]+)", output)
    speed_matches = re.findall(r"speed=\s*([\d.]+)x", output)
    metrics: Dict[str, float] = {}
    if fps_matches:
        metrics["reported_fps"] = float(fps_matches[-1])
    if speed_matches:
        metrics["speed_factor"] = float(speed_matches[-1])
    return metrics


def run_ffmpeg_benchmark(resolution: str, duration_secs: int, codec: str) -> Dict[str, object]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
        "-benchmark",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={resolution}:rate=30:duration={duration_secs}",
        "-c:v",
        codec,
        "-preset",
        "medium",
        "-f",
        "null",
        "-",
    ]
    stdout, duration = run_command(command)
    metrics = parse_ffmpeg_progress(stdout)
    total_frames = duration_secs * 30
    metrics["calculated_fps"] = total_frames / duration if duration else 0.0
    metrics["frames"] = total_frames
    metrics["codec"] = codec
    return {
        "name": "ffmpeg-transcode",
        "command": " ".join(command),
        "parameters": {"resolution": resolution, "duration": duration_secs, "codec": codec},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def generate_test_pattern(resolution: str, frames: int) -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".y4m")
    tmp.close()
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={resolution}:rate=30",
        "-frames:v",
        str(frames),
        "-pix_fmt",
        "yuv420p",
        tmp.name,
    ]
    run_command(command)
    return Path(tmp.name)


def parse_x264_output(output: str) -> Dict[str, float]:
    match = re.search(r"encoded\s+\d+\s+frames,\s+([\d.]+)\s+fps,\s+([\d.]+)\s+kb/s", output)
    if not match:
        raise ValueError("Unable to parse x264 summary")
    return {"fps": float(match.group(1)), "kb_per_s": float(match.group(2))}


def run_x264_benchmark(resolution: str, frames: int, preset: str, crf: int) -> Dict[str, object]:
    pattern_path = generate_test_pattern(resolution, frames)
    try:
        command = [
            "x264",
            "--preset",
            preset,
            "--crf",
            str(crf),
            "--frames",
            str(frames),
            str(pattern_path),
            "-o",
            "/dev/null",
        ]
        stdout, duration = run_command(command)
        metrics = parse_x264_output(stdout)
    finally:
        pattern_path.unlink(missing_ok=True)
    metrics["preset"] = preset
    metrics["crf"] = crf
    metrics["resolution"] = resolution
    return {
        "name": "x264-encode",
        "command": " ".join(command),
        "parameters": {"resolution": resolution, "frames": frames, "preset": preset, "crf": crf},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_sqlite_benchmark(row_count: int, select_queries: int) -> Dict[str, object]:
    tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp_db.close()
    db_path = Path(tmp_db.name)
    insert_start = time.perf_counter()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA synchronous = OFF;")
        conn.execute("CREATE TABLE bench (id INTEGER PRIMARY KEY, value INTEGER);")
        with conn:
            conn.executemany(
                "INSERT INTO bench(value) VALUES (?)",
                ((i % 1000,) for i in range(row_count)),
            )
        insert_duration = time.perf_counter() - insert_start
        query_start = time.perf_counter()
        cursor = conn.cursor()
        for i in range(select_queries):
            cursor.execute("SELECT AVG(value) FROM bench WHERE value >= ?", (i % 1000,))
            cursor.fetchone()
        query_duration = time.perf_counter() - query_start
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)
    metrics = {
        "insert_rows_per_s": row_count / insert_duration if insert_duration else 0.0,
        "selects_per_s": select_queries / query_duration if query_duration else 0.0,
        "row_count": row_count,
        "select_queries": select_queries,
    }
    total_duration = insert_duration + query_duration
    return {
        "name": "sqlite-mixed",
        "command": "python-sqlite3-inline",
        "parameters": {
            "row_count": row_count,
            "select_queries": select_queries,
        },
        "metrics": metrics,
        "duration_seconds": total_duration,
        "raw_output": "",
    }


def parse_unigine_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    fps_match = re.search(r"FPS[:=]\s*([\d.]+)", output, re.IGNORECASE)
    score_match = re.search(r"Score[:=]\s*([\d.]+)", output, re.IGNORECASE)
    if fps_match:
        metrics["fps"] = float(fps_match.group(1))
    if score_match:
        metrics["score"] = float(score_match.group(1))
    if not metrics:
        raise ValueError("Unable to parse Unigine output")
    return metrics


def run_unigine_command(command_str: str, name: str) -> Dict[str, object]:
    if not command_str:
        raise FileNotFoundError(f"No command configured for {name}")
    command = shlex.split(command_str)
    stdout, duration = run_command(command)
    metrics = parse_unigine_output(stdout)
    return {
        "name": name,
        "command": command_str,
        "parameters": {},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


PRESET_DEFINITIONS: Dict[str, Dict[str, object]] = {
    "balanced": {
        "description": "Quick mix of CPU, IO, and network tests.",
        "benchmarks": (
            "openssl-speed",
            "7zip-benchmark",
            "stress-ng",
            "fio-seq",
            "speedtest-cli",
            "sqlite-mixed",
        ),
    },
    "cpu": {"description": "CPU heavy synthetic workloads.", "categories": ("cpu",)},
    "io": {"description": "Disk and filesystem focused tests.", "categories": ("io",)},
    "network": {"description": "Network throughput and latency tests.", "categories": ("network",)},
    "gpu": {"description": "GPU render benchmarks.", "categories": ("gpu",)},
    "media": {"description": "Media encode/transcode workloads.", "categories": ("media",)},
    "database": {"description": "Data and storage bound tests.", "categories": ("database",)},
    "extreme": {
        "description": "Adds heavy compilation and encoding tests.",
        "benchmarks": ("linux-kernel-build", "ffmpeg-transcode", "x264-encode"),
    },
    "all": {"description": "Run every available benchmark.", "all": True},
}


def _default_jobs() -> int:
    return max(1, os.cpu_count() or 1)


BENCHMARK_DEFINITIONS: List[BenchmarkDefinition] = [
    BenchmarkDefinition(
        key="openssl-speed",
        categories=("cpu", "crypto"),
        presets=("balanced", "cpu", "all"),
        description="OpenSSL symmetric throughput test.",
        runner=lambda args: run_openssl(args.openssl_seconds, args.openssl_algorithm),
        requires=("openssl",),
    ),
    BenchmarkDefinition(
        key="7zip-benchmark",
        categories=("cpu", "compression"),
        presets=("balanced", "cpu", "all"),
        description="7-Zip builtin CPU benchmark.",
        runner=lambda args: run_7zip(),
        requires=("7z",),
    ),
    BenchmarkDefinition(
        key="stress-ng",
        categories=("cpu",),
        presets=("balanced", "cpu", "all"),
        description="stress-ng CPU saturation.",
        runner=lambda args: run_stress_ng(args.stress_ng_seconds, args.stress_ng_method),
        requires=("stress-ng",),
    ),
    BenchmarkDefinition(
        key="fio-seq",
        categories=("io",),
        presets=("balanced", "io", "all"),
        description="fio sequential read/write.",
        runner=lambda args: run_fio(args.fio_size_mb, args.fio_runtime, args.fio_block_kb),
        requires=("fio",),
    ),
    BenchmarkDefinition(
        key="glmark2",
        categories=("gpu",),
        presets=("gpu", "all"),
        description="glmark2 GPU renderer.",
        runner=lambda args: run_glmark2(args.glmark2_size, args.glmark2_mode == "offscreen"),
        requires=("glmark2",),
    ),
    BenchmarkDefinition(
        key="speedtest-cli",
        categories=("network",),
        presets=("balanced", "network", "all"),
        description="speedtest-cli throughput test.",
        runner=lambda args: run_speedtest_cli(args.speedtest_server or None),
        requires=("speedtest-cli",),
    ),
    BenchmarkDefinition(
        key="linux-kernel-build",
        categories=("cpu",),
        presets=("cpu", "extreme", "all"),
        description="Parallel Linux kernel compilation.",
        runner=lambda args: run_kernel_build(args.kernel_source, args.kernel_target, args.kernel_jobs),
        requires=("make",),
        availability_check=lambda args: (
            (True, "") if args.kernel_source else (False, "Set --kernel-source to enable this benchmark.")
        ),
    ),
    BenchmarkDefinition(
        key="ffmpeg-transcode",
        categories=("cpu", "media"),
        presets=("media", "extreme", "all"),
        description="FFmpeg software transcode.",
        runner=lambda args: run_ffmpeg_benchmark(
            args.ffmpeg_resolution,
            args.ffmpeg_duration,
            args.ffmpeg_codec,
        ),
        requires=("ffmpeg",),
    ),
    BenchmarkDefinition(
        key="x264-encode",
        categories=("cpu", "media"),
        presets=("media", "extreme", "all"),
        description="Raw x264 encode throughput.",
        runner=lambda args: run_x264_benchmark(
            args.x264_resolution,
            args.x264_frames,
            args.x264_preset,
            args.x264_crf,
        ),
        requires=("x264", "ffmpeg"),
    ),
    BenchmarkDefinition(
        key="sqlite-mixed",
        categories=("io", "database"),
        presets=("balanced", "io", "database", "all"),
        description="SQLite insert/select mix.",
        runner=lambda args: run_sqlite_benchmark(args.sqlite_rows, args.sqlite_selects),
    ),
    BenchmarkDefinition(
        key="unigine-heaven",
        categories=("gpu",),
        presets=("gpu", "all"),
        description="Unigine Heaven GPU benchmark.",
        runner=lambda args: run_unigine_command(args.unigine_heaven_cmd, "unigine-heaven"),
        availability_check=lambda args: (
            (True, "") if args.unigine_heaven_cmd else (False, "Provide --unigine-heaven-cmd")
        ),
    ),
    BenchmarkDefinition(
        key="unigine-valley",
        categories=("gpu",),
        presets=("gpu", "all"),
        description="Unigine Valley GPU benchmark.",
        runner=lambda args: run_unigine_command(args.unigine_valley_cmd, "unigine-valley"),
        availability_check=lambda args: (
            (True, "") if args.unigine_valley_cmd else (False, "Provide --unigine-valley-cmd")
        ),
    ),
]


def preset_help_text() -> str:
    rows = [f"{name}: {data['description']}" for name, data in sorted(PRESET_DEFINITIONS.items())]
    return "; ".join(rows)


def expand_presets(presets: Sequence[str]) -> List[str]:
    selected: set[str] = set()
    if not presets:
        presets = ["balanced"]
    for preset in presets:
        config = PRESET_DEFINITIONS.get(preset)
        if not config:
            continue
        if config.get("all"):
            return [definition.key for definition in BENCHMARK_DEFINITIONS]
        categories = config.get("categories", [])
        selected |= {
            definition.key
            for definition in BENCHMARK_DEFINITIONS
            if any(cat in definition.categories for cat in categories)
        }
        for bench in config.get("benchmarks", []):
            selected.add(bench)
    return sorted(selected)


def execute_definition(definition: BenchmarkDefinition, args: argparse.Namespace) -> Dict[str, object]:
    ok, reason = check_requirements(definition.requires)
    if not ok:
        return build_status_entry(definition, "skipped", reason)
    if definition.availability_check:
        ok, reason = definition.availability_check(args)
        if not ok:
            return build_status_entry(definition, "skipped", reason)
    try:
        result = definition.runner(args)
    except FileNotFoundError as exc:
        return build_status_entry(definition, "skipped", f"Missing file or path: {exc}")
    except subprocess.CalledProcessError as exc:
        return build_status_entry(
            definition,
            "error",
            f"Command failed with exit code {exc.returncode}",
        )
    except Exception as exc:
        return build_status_entry(definition, "error", str(exc))
    result.setdefault("name", definition.key)
    result.setdefault("metrics", {})
    result.setdefault("parameters", {})
    result["status"] = "ok"
    result["categories"] = list(definition.categories)
    result["presets"] = list(definition.presets)
    return result


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
    status = bench.get("status", "ok")
    if status != "ok":
        details = bench.get("message", status)
        prefix = "Skipped" if status == "skipped" else "Error"
        return f"{prefix}: {details}"
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
    elif name == "speedtest-cli":
        download = metrics.get("download_mbps")
        upload = metrics.get("upload_mbps")
        if download is not None and upload is not None:
            return f"D {download:.1f} / U {upload:.1f} Mbps"
    elif name == "linux-kernel-build":
        build_time = metrics.get("build_time_seconds")
        if build_time is not None:
            return f"{build_time:.1f} s"
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
    elif name in {"unigine-heaven", "unigine-valley"}:
        score = metrics.get("score")
        fps = metrics.get("fps")
        if score is not None:
            return f"{score:.0f} score"
        if fps is not None:
            return f"{fps:.1f} fps"
    return ""


def build_html_summary(results_dir: Path, html_path: Path) -> None:
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
            meta = bench_metadata.setdefault(name, {"categories": set(), "presets": set()})
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
            description = describe_benchmark(bench_map.get(bench_name, {}))
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
    header_cells = ""
    for name in bench_columns:
        meta = bench_metadata.get(name, {"categories": set(), "presets": set()})
        category_label = ", ".join(sorted(meta.get("categories", []))) or "unspecified"
        preset_label = ", ".join(sorted(meta.get("presets", []))) or "unspecified"
        header_cells += (
            f"<th title=\"Presets: {html.escape(preset_label)}\">"
            f"{html.escape(name)}<br><small>{html.escape(category_label)}</small>"
            "</th>"
        )
    body_rows = []
    for row in rows:
        system = row["system"]
        system_label = f"{system.get('hostname', '')} ({system.get('machine', '')})"
        preset_label = ", ".join(row.get("presets", [])) or "n/a"
        cell_html = "".join(f"<td>{html.escape(value)}</td>" for value in row["cells"])
        body_rows.append(
            "<tr>"
            f"<td><a href=\"{html.escape(row['file'])}\">{html.escape(row['file'])}</a></td>"
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
        <th>Presets</th>
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
    parser.add_argument(
        "--preset",
        dest="presets",
        action="append",
        choices=sorted(PRESET_DEFINITIONS.keys()),
        default=[],
        help="Add a benchmark preset to run (defaults to 'balanced').",
    )
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        default=None,
        help="Explicit benchmark names to run (skips preset expansion).",
    )
    parser.add_argument(
        "--skip-benchmark",
        action="append",
        default=[],
        help="Benchmark name to skip from the current selection.",
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
    parser.add_argument(
        "--speedtest-server",
        default="",
        help="Optional server ID for speedtest-cli (defaults to automatic selection).",
    )
    parser.add_argument(
        "--kernel-source",
        default="",
        help="Path to the Linux kernel sources for the compilation benchmark.",
    )
    parser.add_argument(
        "--kernel-target",
        default="bzImage",
        help="Kernel make target (e.g. bzImage, vmlinux).",
    )
    parser.add_argument(
        "--kernel-jobs",
        type=int,
        default=_default_jobs(),
        help="Number of parallel make jobs for the kernel build.",
    )
    parser.add_argument(
        "--ffmpeg-resolution",
        default="1280x720",
        help="Resolution for the FFmpeg benchmark (e.g. 1920x1080).",
    )
    parser.add_argument(
        "--ffmpeg-duration",
        type=int,
        default=5,
        help="Duration (seconds) for the FFmpeg test pattern clip.",
    )
    parser.add_argument(
        "--ffmpeg-codec",
        default="libx264",
        help="Video codec to use for the FFmpeg benchmark.",
    )
    parser.add_argument(
        "--x264-resolution",
        default="1280x720",
        help="Resolution for the standalone x264 benchmark.",
    )
    parser.add_argument(
        "--x264-frames",
        type=int,
        default=240,
        help="Number of frames to encode for x264.",
    )
    parser.add_argument(
        "--x264-preset",
        default="medium",
        help="x264 preset to benchmark (e.g. veryfast, medium, slow).",
    )
    parser.add_argument(
        "--x264-crf",
        type=int,
        default=23,
        help="x264 constant rate factor (quality setting).",
    )
    parser.add_argument(
        "--sqlite-rows",
        type=int,
        default=50000,
        help="Number of rows to insert in the SQLite test.",
    )
    parser.add_argument(
        "--sqlite-selects",
        type=int,
        default=1000,
        help="Number of aggregate SELECT queries in the SQLite test.",
    )
    parser.add_argument(
        "--unigine-heaven-cmd",
        default="",
        help="Command (including args) to run Unigine Heaven in benchmark mode.",
    )
    parser.add_argument(
        "--unigine-valley-cmd",
        default="",
        help="Command (including args) to run Unigine Valley in benchmark mode.",
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
        for definition in BENCHMARK_DEFINITIONS:
            categories = ", ".join(definition.categories)
            presets = ", ".join(definition.presets)
            print(f"  {definition.key:<20} [{categories}] presets: {presets} - {definition.description}")
        return 0

    requested_presets = list(args.presets)
    selected_names: List[str]
    if args.benchmarks:
        selected_names = list(dict.fromkeys(args.benchmarks))
    else:
        if not requested_presets:
            requested_presets = ["balanced"]
        selected_names = expand_presets(requested_presets)

    known_benchmarks = {definition.key for definition in BENCHMARK_DEFINITIONS}
    invalid = [name for name in selected_names if name not in known_benchmarks]
    if invalid:
        print(f"Unknown benchmarks requested: {', '.join(invalid)}", file=sys.stderr)
    selected_names = [name for name in selected_names if name in known_benchmarks]

    skip_names = set(args.skip_benchmark or [])
    legacy_skips = {
        "skip_openssl": "openssl-speed",
        "skip_7zip": "7zip-benchmark",
        "skip_stress_ng": "stress-ng",
        "skip_fio": "fio-seq",
        "skip_glmark2": "glmark2",
    }
    for attr, bench_name in legacy_skips.items():
        if getattr(args, attr, False):
            skip_names.add(bench_name)

    if not selected_names:
        print("No benchmarks requested.", file=sys.stderr)
        return 1

    definition_map = {definition.key: definition for definition in BENCHMARK_DEFINITIONS}
    results: List[Dict[str, object]] = []
    for name in selected_names:
        definition = definition_map[name]
        if name in skip_names:
            results.append(
                {
                    "name": name,
                    "status": "skipped",
                    "message": "Skipped via CLI flag",
                    "categories": list(definition.categories),
                    "presets": list(definition.presets),
                    "metrics": {},
                    "parameters": {},
                }
            )
            continue
        results.append(execute_definition(definition, args))

    if not results:
        print("No benchmarks executed.", file=sys.stderr)
        return 1

    generated_at = datetime.now(timezone.utc)
    system_info = gather_system_info(args.hostname or None)
    report = {
        "generated_at": generated_at.isoformat(),
        "system": system_info,
        "benchmarks": results,
        "presets_requested": requested_presets,
        "benchmarks_requested": selected_names,
        "skip_requests": sorted(skip_names),
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
