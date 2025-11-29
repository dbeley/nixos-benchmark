#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import html
import json
import os
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple


DEFAULT_STRESS_NG_SECONDS = 5
DEFAULT_STRESS_NG_METHOD = "fft"
DEFAULT_FIO_SIZE_MB = 64
DEFAULT_FIO_RUNTIME = 5
DEFAULT_FIO_BLOCK_KB = 1024
DEFAULT_FFMPEG_RESOLUTION = "1280x720"
DEFAULT_FFMPEG_DURATION = 5
DEFAULT_FFMPEG_CODEC = "libx264"
DEFAULT_X264_RESOLUTION = "1280x720"
DEFAULT_X264_FRAMES = 240
DEFAULT_X264_PRESET = "medium"
DEFAULT_X264_CRF = 23
DEFAULT_SQLITE_ROWS = 50_000
DEFAULT_SQLITE_SELECTS = 1_000
DEFAULT_OPENSSL_SECONDS = 3
DEFAULT_OPENSSL_ALGORITHM = "aes-256-cbc"
DEFAULT_GLMARK2_SIZE = "1920x1080"
DEFAULT_VKMARK_CMD = ("vkmark",)
DEFAULT_SYSBENCH_CPU_MAX_PRIME = 20000
DEFAULT_SYSBENCH_RUNTIME = 5
DEFAULT_SYSBENCH_THREADS = 0
DEFAULT_SYSBENCH_MEMORY_BLOCK_KB = 1024
DEFAULT_SYSBENCH_MEMORY_TOTAL_MB = 512
DEFAULT_SYSBENCH_MEMORY_OPERATION = "read"
DEFAULT_IOPING_COUNT = 5
DEFAULT_ZSTD_LEVEL = 5
DEFAULT_PIGZ_LEVEL = 3
DEFAULT_COMPRESS_SIZE_MB = 32
DEFAULT_IPERF_DURATION = 3
DEFAULT_NETPERF_DURATION = 3
DEFAULT_PGBENCH_SCALE = 1
DEFAULT_PGBENCH_TIME = 5


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


def write_temp_data_file(size_mb: int, randomize: bool = True) -> Path:
    block_size = 1024 * 1024
    block = os.urandom(block_size) if randomize else b"\0" * block_size
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    with open(tmp.name, "wb") as handle:
        for _ in range(size_mb):
            handle.write(os.urandom(block_size) if randomize else block)
    return Path(tmp.name)


def find_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.05)
    return False


def find_first_block_device() -> str | None:
    skip_prefixes = ("loop", "ram", "dm-", "zd", "nbd", "sr", "md")
    sys_block = Path("/sys/block")
    if not sys_block.exists():
        return None
    for path in sorted(sys_block.iterdir()):
        name = path.name
        if name.startswith(skip_prefixes):
            continue
        device = Path("/dev") / name
        if device.exists():
            return str(device)
    return None


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


def run_command(
    command: List[str], *, env: Dict[str, str] | None = None
) -> Tuple[str, float]:
    start = time.perf_counter()
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
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
    pattern = re.compile(
        r"stress-ng:\s+\w+:\s+\[\d+\]\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
        r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        stressor_name = match.group(1)
        if stressor_name == "stressor" or stressor_name.startswith("("):
            continue
        return {
            "stressor": stressor_name,
            "bogo_ops": float(match.group(2)),
            "real_time_secs": float(match.group(3)),
            "user_time_secs": float(match.group(4)),
            "system_time_secs": float(match.group(5)),
            "bogo_ops_per_sec_real": float(match.group(6)),
            "bogo_ops_per_sec_cpu": float(match.group(7)),
        }
    raise ValueError("Unable to parse stress-ng metrics (try increasing runtime)")


def parse_sysbench_cpu_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    events_per_sec = re.search(r"events per second:\s+([\d.]+)", output)
    total_time = re.search(r"total time:\s+([\d.]+)s", output)
    total_events = re.search(r"total number of events:\s+([\d.]+)", output)
    if events_per_sec:
        metrics["events_per_sec"] = float(events_per_sec.group(1))
    if total_time:
        metrics["total_time_secs"] = float(total_time.group(1))
    if total_events:
        metrics["total_events"] = float(total_events.group(1))
    if not metrics:
        raise ValueError("Unable to parse sysbench CPU output")
    return metrics


def parse_sysbench_memory_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    operations = re.search(
        r"Total operations:\s+([\d.]+)\s+\(([\d.]+)\s+per second\)", output
    )
    throughput = re.search(
        r"([\d.]+)\s+MiB transferred\s+\(([\d.]+)\s+MiB/sec\)", output
    )
    total_time = re.search(r"total time:\s+([\d.]+)s", output)
    if operations:
        metrics["operations"] = float(operations.group(1))
        metrics["operations_per_sec"] = float(operations.group(2))
    if throughput:
        metrics["transferred_mib"] = float(throughput.group(1))
        metrics["throughput_mib_per_s"] = float(throughput.group(2))
    if total_time:
        metrics["total_time_secs"] = float(total_time.group(1))
    if not metrics:
        raise ValueError("Unable to parse sysbench memory output")
    return metrics


def run_openssl(
    seconds: int = DEFAULT_OPENSSL_SECONDS,
    algorithm: str = DEFAULT_OPENSSL_ALGORITHM,
) -> Dict[str, object]:
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


def run_sysbench_cpu(
    threads: int, max_prime: int, runtime_secs: int
) -> Dict[str, object]:
    thread_count = threads if threads > 0 else (os.cpu_count() or 1)
    command = [
        "sysbench",
        "cpu",
        f"--cpu-max-prime={max_prime}",
        f"--threads={thread_count}",
        f"--time={runtime_secs}",
        "run",
    ]
    stdout, duration = run_command(command)
    metrics = parse_sysbench_cpu_output(stdout)
    metrics["threads"] = thread_count
    metrics["cpu_max_prime"] = max_prime
    return {
        "name": "sysbench-cpu",
        "command": " ".join(command),
        "parameters": {
            "threads": thread_count,
            "cpu_max_prime": max_prime,
            "runtime_secs": runtime_secs,
        },
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_sysbench_memory(
    threads: int, block_kb: int, total_mb: int, operation: str
) -> Dict[str, object]:
    thread_count = threads if threads > 0 else (os.cpu_count() or 1)
    command = [
        "sysbench",
        "memory",
        f"--memory-block-size={block_kb}K",
        f"--memory-total-size={total_mb}M",
        f"--memory-oper={operation}",
        f"--threads={thread_count}",
        "run",
    ]
    stdout, duration = run_command(command)
    metrics = parse_sysbench_memory_output(stdout)
    metrics["threads"] = thread_count
    metrics["block_kb"] = block_kb
    metrics["total_mb"] = total_mb
    metrics["operation"] = operation
    return {
        "name": "sysbench-memory",
        "command": " ".join(command),
        "parameters": {
            "threads": thread_count,
            "block_kb": block_kb,
            "total_mb": total_mb,
            "operation": operation,
        },
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


def run_glmark2(
    size: str = DEFAULT_GLMARK2_SIZE, offscreen: bool = True
) -> Dict[str, object]:
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


def parse_vkmark_output(output: str) -> Dict[str, float]:
    scene_pattern = re.compile(
        r"(?P<scene>[\w-]+).*?(?P<frames>[\d.]+)\s+frames\s+in\s+[\d.]+\s+seconds\s*="
        r"\s*(?P<fps>[\d.]+)\s*FPS",
        flags=re.IGNORECASE,
    )
    fps_values = [float(match.group("fps")) for match in scene_pattern.finditer(output)]
    if not fps_values:
        fps_values = [
            float(match)
            for match in re.findall(r"FPS[:=]\s*([\d.]+)", output, flags=re.IGNORECASE)
        ]
    if not fps_values:
        raise ValueError("Unable to parse vkmark FPS results")
    return {
        "fps_avg": sum(fps_values) / len(fps_values),
        "fps_min": min(fps_values),
        "fps_max": max(fps_values),
        "samples": len(fps_values),
    }


def run_vkmark(command: Sequence[str] = DEFAULT_VKMARK_CMD) -> Dict[str, object]:
    command_list = list(command)
    stdout, duration = run_command(command_list)
    metrics = parse_vkmark_output(stdout)
    return {
        "name": "vkmark",
        "command": " ".join(command_list),
        "parameters": {},
        "metrics": metrics,
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


def run_ffmpeg_benchmark(
    resolution: str, duration_secs: int, codec: str
) -> Dict[str, object]:
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
        "parameters": {
            "resolution": resolution,
            "duration": duration_secs,
            "codec": codec,
        },
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
    match = re.search(
        r"encoded\s+\d+\s+frames,\s+([\d.]+)\s+fps,\s+([\d.]+)\s+kb/s", output
    )
    if not match:
        raise ValueError("Unable to parse x264 summary")
    return {"fps": float(match.group(1)), "kb_per_s": float(match.group(2))}


def run_x264_benchmark(
    resolution: str, frames: int, preset: str, crf: int
) -> Dict[str, object]:
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
        "parameters": {
            "resolution": resolution,
            "frames": frames,
            "preset": preset,
            "crf": crf,
        },
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


def parse_tinymembench_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in output.splitlines():
        match = re.match(r"\s*([A-Za-z0-9 +/_-]+?)\s+([\d.]+)\s+MB/s", line)
        if not match:
            continue
        label = re.sub(r"\s+", "_", match.group(1).strip().lower())
        metrics[f"{label}_mb_per_s"] = float(match.group(2))
    if not metrics:
        raise ValueError("Unable to parse tinymembench throughput")
    return metrics


def run_tinymembench() -> Dict[str, object]:
    stdout, duration = run_command(["tinymembench"])
    metrics = parse_tinymembench_output(stdout)
    return {
        "name": "tinymembench",
        "command": "tinymembench",
        "parameters": {},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_clpeak_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    section = ""
    for line in output.splitlines():
        if "Global memory bandwidth" in line:
            section = "global_mem_bandwidth_gbps"
            continue
        if "Single-precision compute" in line:
            section = "single_precision_gflops"
            continue
        if "Double-precision compute" in line:
            section = "double_precision_gflops"
            continue
        if "Integer compute" in line:
            section = "integer_compute_giops"
            continue
        if "Kernel launch latency" in line:
            section = "kernel_launch_latency_us"
            continue
        match = re.match(r"\s*(float|double|half|int\d*|long)\s*:\s*([\d.]+)", line)
        if match and section:
            key = f"{section}_{match.group(1)}"
            metrics[key] = float(match.group(2))
        latency_match = re.match(r"\s*([\d.]+)\s*us", line)
        if section == "kernel_launch_latency_us" and latency_match:
            metrics[section] = float(latency_match.group(1))
    if not metrics:
        raise ValueError("Unable to parse clpeak output (check OpenCL drivers)")
    return metrics


def run_clpeak() -> Dict[str, object]:
    stdout, duration = run_command(["clpeak"])
    metrics = parse_clpeak_output(stdout)
    return {
        "name": "clpeak",
        "command": "clpeak",
        "parameters": {},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_zstd_benchmark(
    level: int = DEFAULT_ZSTD_LEVEL, size_mb: int = DEFAULT_COMPRESS_SIZE_MB
) -> Dict[str, object]:
    data_path = write_temp_data_file(size_mb)
    compressed_path = data_path.with_suffix(data_path.suffix + ".zst")
    decompressed_path = data_path.with_suffix(".out")
    try:
        start = time.perf_counter()
        run_command(
            ["zstd", "-q", "-f", f"-{level}", str(data_path), "-o", str(compressed_path)]
        )
        compress_duration = time.perf_counter() - start

        data_path.unlink(missing_ok=True)
        start = time.perf_counter()
        run_command(
            ["zstd", "-d", "-q", "-f", str(compressed_path), "-o", str(decompressed_path)]
        )
        decompress_duration = time.perf_counter() - start
    finally:
        data_path.unlink(missing_ok=True)
        compressed_path.unlink(missing_ok=True)
        decompressed_path.unlink(missing_ok=True)
    metrics = {
        "compress_mb_per_s": size_mb / compress_duration if compress_duration else 0.0,
        "decompress_mb_per_s": size_mb / decompress_duration
        if decompress_duration
        else 0.0,
        "level": level,
        "size_mb": size_mb,
    }
    return {
        "name": "zstd-compress",
        "command": f"zstd -q -f -{level} {data_path} -o {compressed_path}",
        "parameters": {"level": level, "size_mb": size_mb},
        "metrics": metrics,
        "duration_seconds": compress_duration + decompress_duration,
        "raw_output": "",
    }


def run_pigz_benchmark(
    level: int = DEFAULT_PIGZ_LEVEL, size_mb: int = DEFAULT_COMPRESS_SIZE_MB
) -> Dict[str, object]:
    data_path = write_temp_data_file(size_mb)
    compressed_path = Path(f"{data_path}.gz")
    decompressed_path = compressed_path.with_suffix("")
    try:
        start = time.perf_counter()
        run_command(
            ["pigz", "-f", "-k", "-p", "0", f"-{level}", str(data_path)]
        )
        compress_duration = time.perf_counter() - start

        data_path.unlink(missing_ok=True)
        start = time.perf_counter()
        run_command(["pigz", "-d", "-f", "-k", str(compressed_path)])
        decompress_duration = time.perf_counter() - start
    finally:
        data_path.unlink(missing_ok=True)
        compressed_path.unlink(missing_ok=True)
        decompressed_path.unlink(missing_ok=True)
    metrics = {
        "compress_mb_per_s": size_mb / compress_duration if compress_duration else 0.0,
        "decompress_mb_per_s": size_mb / decompress_duration
        if decompress_duration
        else 0.0,
        "level": level,
        "size_mb": size_mb,
    }
    return {
        "name": "pigz-compress",
        "command": f"pigz -f -k -p 0 -{level} {data_path}",
        "parameters": {"level": level, "size_mb": size_mb},
        "metrics": metrics,
        "duration_seconds": compress_duration + decompress_duration,
        "raw_output": "",
    }


def parse_hashcat_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in output.splitlines():
        match = re.search(r"([\d.]+)\s*(G|M|k)?H/s", line)
        if not match:
            continue
        value = float(match.group(1))
        unit = match.group(2) or ""
        if unit == "G":
            value *= 1_000_000_000
        elif unit == "M":
            value *= 1_000_000
        elif unit == "k":
            value *= 1_000
        metrics.setdefault("throughput_hps", 0.0)
        metrics["throughput_hps"] = max(metrics["throughput_hps"], value)
    if not metrics:
        raise ValueError("Unable to parse hashcat benchmark output")
    return metrics


def run_hashcat_benchmark() -> Dict[str, object]:
    stdout, duration = run_command(
        [
            "hashcat",
            "--benchmark",
            "--benchmark-all",
            "--machine-readable",
            "--potfile-disable",
            "--quiet",
            "--force",
        ]
    )
    metrics = parse_hashcat_output(stdout)
    return {
        "name": "hashcat-benchmark",
        "command": "hashcat --benchmark --benchmark-all --machine-readable --potfile-disable --quiet --force",
        "parameters": {},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_cryptsetup_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    pattern = re.compile(
        r"^(?P<cipher>[a-z0-9-]+)\s+(?P<keybits>\d+)b\s+(?P<enc>[\d.]+)\s+MiB/s\s+(?P<dec>[\d.]+)\s+MiB/s",
        flags=re.IGNORECASE,
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        cipher = match.group("cipher")
        keybits = int(match.group("keybits"))
        enc = float(match.group("enc"))
        dec = float(match.group("dec"))
        metrics[f"{cipher}_{keybits}_enc_mib_per_s"] = enc
        metrics[f"{cipher}_{keybits}_dec_mib_per_s"] = dec
    if not metrics:
        raise ValueError("Unable to parse cryptsetup benchmark results")
    return metrics


def run_cryptsetup_benchmark() -> Dict[str, object]:
    stdout, duration = run_command(["cryptsetup", "benchmark"])
    metrics = parse_cryptsetup_output(stdout)
    return {
        "name": "cryptsetup-benchmark",
        "command": "cryptsetup benchmark",
        "parameters": {},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_ioping_output(output: str) -> Dict[str, float]:
    match = re.search(r"min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", output)
    if not match:
        raise ValueError("Unable to parse ioping summary")
    return {
        "latency_min_ms": float(match.group(1)),
        "latency_avg_ms": float(match.group(2)),
        "latency_max_ms": float(match.group(3)),
        "latency_mdev_ms": float(match.group(4)),
    }


def run_ioping(count: int = DEFAULT_IOPING_COUNT) -> Dict[str, object]:
    stdout, duration = run_command(["ioping", "-c", str(count), "."])
    metrics = parse_ioping_output(stdout)
    metrics["requests"] = count
    return {
        "name": "ioping",
        "command": f"ioping -c {count} .",
        "parameters": {"count": count},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_hdparm_output(output: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    cached = re.search(r"Timing cached reads:\s+[\d.]+\s+MB in\s+[\d.]+\s+seconds\s+=\s+([\d.]+)\s+MB/sec", output)
    buffered = re.search(
        r"Timing buffered disk reads:\s+[\d.]+\s+MB in\s+[\d.]+\s+seconds\s+=\s+([\d.]+)\s+MB/sec",
        output,
    )
    if cached:
        metrics["cached_read_mb_per_s"] = float(cached.group(1))
    if buffered:
        metrics["buffered_read_mb_per_s"] = float(buffered.group(1))
    if not metrics:
        raise ValueError("Unable to parse hdparm output")
    return metrics


def run_hdparm(device: str | None = None) -> Dict[str, object]:
    target = device or find_first_block_device()
    if not target:
        raise FileNotFoundError("No suitable block device found for hdparm")
    stdout, duration = run_command(["hdparm", "-Tt", target])
    metrics = parse_hdparm_output(stdout)
    metrics["device"] = target
    return {
        "name": "hdparm",
        "command": f"hdparm -Tt {target}",
        "parameters": {"device": target},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_fsmark_output(output: str) -> Dict[str, float]:
    match = re.search(r"Throughput\s*=\s*([\d.]+)\s+files/sec", output)
    if not match:
        raise ValueError("Unable to parse fsmark throughput")
    return {"files_per_sec": float(match.group(1))}


def run_fsmark() -> Dict[str, object]:
    workdir = Path("results/fsmark")
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        stdout, duration = run_command(
            [
                "fs_mark",
                "-d",
                str(workdir),
                "-n",
                "200",
                "-s",
                "1024",
                "-t",
                "1",
                "-k",
            ]
        )
        metrics = parse_fsmark_output(stdout)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return {
        "name": "fsmark",
        "command": f"fs_mark -d {workdir} -n 200 -s 1024 -t 1 -k",
        "parameters": {"files": 200, "size_kb": 1024},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_filebench_output(output: str) -> Dict[str, float]:
    match = re.search(r"IO Summary:\s+([\d.]+)\s+ops/s", output)
    if not match:
        raise ValueError("Unable to parse filebench IO summary")
    return {"ops_per_sec": float(match.group(1))}


def run_filebench() -> Dict[str, object]:
    workdir = Path(tempfile.mkdtemp(prefix="filebench-"))
    workload = (
        f"set $dir={workdir}\n"
        "set $filesize=1m\n"
        "set $nfiles=100\n"
        "define fileset name=fileset1, path=$dir, size=$filesize, entries=$nfiles, prealloc=100\n"
        "define process name=seqwriter {\n"
        "  thread name=writer thread_count=1 {\n"
        "    flowop createfile name=create, filesetname=fileset1\n"
        "    flowop writewholefile name=write, filesetname=fileset1\n"
        "    flowop closefile name=close, filesetname=fileset1\n"
        "    flowop deletefile name=delete, filesetname=fileset1\n"
        "  }\n"
        "}\n"
        "run 5\n"
    )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".f") as tmp:
        workload_path = Path(tmp.name)
        tmp.write(workload.encode("utf-8"))
    try:
        stdout, duration = run_command(["filebench", "-f", str(workload_path)])
        metrics = parse_filebench_output(stdout)
    finally:
        workload_path.unlink(missing_ok=True)
        shutil.rmtree(workdir, ignore_errors=True)
    return {
        "name": "filebench",
        "command": f"filebench -f {workload_path}",
        "parameters": {"files": 100, "filesize": "1m"},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def parse_pgbench_output(output: str) -> Dict[str, float]:
    tps_match = re.search(r"tps = ([\d.]+)", output)
    latency_match = re.search(r"latency average = ([\d.]+) ms", output)
    metrics: Dict[str, float] = {}
    if tps_match:
        metrics["tps"] = float(tps_match.group(1))
    if latency_match:
        metrics["latency_ms"] = float(latency_match.group(1))
    if not metrics:
        raise ValueError("Unable to parse pgbench output")
    return metrics


def run_pgbench(scale: int = DEFAULT_PGBENCH_SCALE, seconds: int = DEFAULT_PGBENCH_TIME) -> Dict[str, object]:
    data_dir = Path(tempfile.mkdtemp(prefix="pgbench-"))
    port = find_free_tcp_port()
    socket_dir = data_dir / "socket"
    socket_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PGHOST"] = str(socket_dir)
    env["PGPORT"] = str(port)
    try:
        run_command(["initdb", "-D", str(data_dir), "-A", "trust", "--no-locale", "--encoding", "UTF8"])
        run_command(["pg_ctl", "-D", str(data_dir), "-o", f"-F -k {socket_dir} -p {port}", "-w", "start"])
        run_command(["createdb", "benchdb"], env=env)
        run_command(["pgbench", "-i", "-s", str(scale), "benchdb"], env=env)
        stdout, duration = run_command(["pgbench", "-T", str(seconds), "benchdb"], env=env)
        metrics = parse_pgbench_output(stdout)
    finally:
        try:
            run_command(["pg_ctl", "-D", str(data_dir), "-m", "fast", "stop"])
        except Exception:
            pass
        shutil.rmtree(data_dir, ignore_errors=True)
    metrics["scale"] = scale
    metrics["duration_s"] = seconds
    return {
        "name": "pgbench",
        "command": f"pgbench -T {seconds} benchdb",
        "parameters": {"scale": scale, "duration_s": seconds},
        "metrics": metrics,
        "duration_seconds": duration,
        "raw_output": stdout,
    }


def run_sqlite_speedtest(
    row_count: int = DEFAULT_SQLITE_ROWS, select_queries: int = DEFAULT_SQLITE_SELECTS
) -> Dict[str, object]:
    tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp_db.close()
    db_path = Path(tmp_db.name)
    conn = sqlite3.connect(db_path)
    insert_start = time.perf_counter()
    try:
        conn.execute("PRAGMA synchronous = OFF;")
        conn.execute("PRAGMA journal_mode = MEMORY;")
        conn.execute("CREATE TABLE bench (id INTEGER PRIMARY KEY, value INTEGER);")
        with conn:
            conn.executemany(
                "INSERT INTO bench(value) VALUES (?)",
                ((i % 1000,) for i in range(row_count)),
            )
        insert_duration = time.perf_counter() - insert_start
        conn.execute("CREATE INDEX idx_value ON bench(value);")
        query_start = time.perf_counter()
        cursor = conn.cursor()
        for i in range(select_queries):
            cursor.execute("SELECT COUNT(*) FROM bench WHERE value = ?", (i % 1000,))
            cursor.fetchone()
        query_duration = time.perf_counter() - query_start
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)
    metrics = {
        "insert_rows_per_s": row_count / insert_duration if insert_duration else 0.0,
        "indexed_selects_per_s": select_queries / query_duration if query_duration else 0.0,
        "row_count": row_count,
        "select_queries": select_queries,
    }
    total_duration = insert_duration + query_duration
    return {
        "name": "sqlite-speedtest",
        "command": "python-sqlite3-speedtest",
        "parameters": {"row_count": row_count, "select_queries": select_queries},
        "metrics": metrics,
        "duration_seconds": total_duration,
        "raw_output": "",
    }


def run_iperf3_loopback(duration: int = DEFAULT_IPERF_DURATION) -> Dict[str, object]:
    port = find_free_tcp_port()
    server = subprocess.Popen(
        ["iperf3", "-s", "-1", "-p", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if not wait_for_port("127.0.0.1", port):
        server.kill()
        raise RuntimeError("iperf3 server failed to start")
    try:
        stdout, client_duration = run_command(
            ["iperf3", "-c", "127.0.0.1", "-p", str(port), "-t", str(duration), "-J"]
        )
        data = json.loads(stdout)
    finally:
        with contextlib.suppress(Exception):
            server.wait(timeout=5)
    end = data.get("end", {})
    sum_received = end.get("sum_received", {})
    bits_per_second = float(sum_received.get("bits_per_second", 0.0))
    metrics = {
        "throughput_mib_per_s": bits_per_second / (8 * 1024 * 1024),
        "retransmits": float(sum_received.get("retransmits", 0)),
        "duration_s": duration,
    }
    return {
        "name": "iperf3-loopback",
        "command": f"iperf3 -c 127.0.0.1 -p {port} -t {duration} -J",
        "parameters": {"duration_s": duration},
        "metrics": metrics,
        "duration_seconds": client_duration,
        "raw_output": stdout,
    }


def parse_netperf_output(output: str) -> Dict[str, float]:
    values = [float(token) for token in re.findall(r"([\d.]+)\s*$", output, flags=re.MULTILINE) if token]
    if not values:
        raise ValueError("Unable to parse netperf throughput")
    throughput_mbps = values[-1]
    return {"throughput_mbps": throughput_mbps}


def run_netperf(duration: int = DEFAULT_NETPERF_DURATION) -> Dict[str, object]:
    port = find_free_tcp_port()
    server = subprocess.Popen(
        ["netserver", "-p", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if not wait_for_port("127.0.0.1", port):
        server.kill()
        raise RuntimeError("netserver failed to start")
    try:
        stdout, client_duration = run_command(
            ["netperf", "-H", "127.0.0.1", "-p", str(port), "-l", str(duration), "-t", "TCP_STREAM"]
        )
        metrics = parse_netperf_output(stdout)
    finally:
        server.terminate()
        with contextlib.suppress(Exception):
            server.wait(timeout=5)
    metrics["duration_s"] = duration
    return {
        "name": "netperf",
        "command": f"netperf -H 127.0.0.1 -p {port} -l {duration} -t TCP_STREAM",
        "parameters": {"duration_s": duration},
        "metrics": metrics,
        "duration_seconds": client_duration,
        "raw_output": stdout,
    }

PRESET_DEFINITIONS: Dict[str, Dict[str, object]] = {
    "balanced": {
        "description": "Quick mix of CPU and IO tests.",
        "benchmarks": (
            "openssl-speed",
            "7zip-benchmark",
            "stress-ng",
            "sysbench-cpu",
            "sysbench-memory",
            "fio-seq",
            "sqlite-mixed",
        ),
    },
    "cpu": {"description": "CPU heavy synthetic workloads.", "categories": ("cpu",)},
    "io": {"description": "Disk and filesystem focused tests.", "categories": ("io",)},
    "memory": {
        "description": "Memory bandwidth and latency tests.",
        "categories": ("memory",),
    },
    "compression": {
        "description": "Compression and decompression throughput.",
        "categories": ("compression",),
    },
    "crypto": {
        "description": "Cryptography focused benchmarks.",
        "categories": ("crypto",),
    },
    "database": {
        "description": "Database engines (SQLite and PostgreSQL).",
        "categories": ("database",),
    },
    "gpu-light": {
        "description": "Lightweight GPU render sanity checks.",
        "benchmarks": ("glmark2", "vkmark"),
    },
    "gpu": {
        "description": "GPU render benchmarks (glmark2 and vkmark).",
        "categories": ("gpu",),
    },
    "network": {
        "description": "Loopback network throughput tests.",
        "categories": ("network",),
    },
    "all": {"description": "Run every available benchmark.", "all": True},
}


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


BENCHMARK_DEFINITIONS: List[BenchmarkDefinition] = [
    BenchmarkDefinition(
        key="openssl-speed",
        categories=("cpu", "crypto"),
        presets=("balanced", "cpu", "all"),
        description="OpenSSL symmetric throughput test.",
        runner=lambda args: run_openssl(),
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
        runner=lambda args: run_stress_ng(
            DEFAULT_STRESS_NG_SECONDS, DEFAULT_STRESS_NG_METHOD
        ),
        requires=("stress-ng",),
    ),
    BenchmarkDefinition(
        key="sysbench-cpu",
        categories=("cpu",),
        presets=("balanced", "cpu", "all"),
        description="sysbench prime calculation throughput.",
        runner=lambda args: run_sysbench_cpu(
            DEFAULT_SYSBENCH_THREADS,
            DEFAULT_SYSBENCH_CPU_MAX_PRIME,
            DEFAULT_SYSBENCH_RUNTIME,
        ),
        requires=("sysbench",),
    ),
    BenchmarkDefinition(
        key="sysbench-memory",
        categories=("memory", "io"),
        presets=("balanced", "io", "memory", "all"),
        description="sysbench memory bandwidth test.",
        runner=lambda args: run_sysbench_memory(
            DEFAULT_SYSBENCH_THREADS,
            DEFAULT_SYSBENCH_MEMORY_BLOCK_KB,
            DEFAULT_SYSBENCH_MEMORY_TOTAL_MB,
            DEFAULT_SYSBENCH_MEMORY_OPERATION,
        ),
        requires=("sysbench",),
    ),
    BenchmarkDefinition(
        key="fio-seq",
        categories=("io",),
        presets=("balanced", "io", "all"),
        description="fio sequential read/write.",
        runner=lambda args: run_fio(
            DEFAULT_FIO_SIZE_MB, DEFAULT_FIO_RUNTIME, DEFAULT_FIO_BLOCK_KB
        ),
        requires=("fio",),
    ),
    BenchmarkDefinition(
        key="glmark2",
        categories=("gpu",),
        presets=("gpu-light", "gpu", "all"),
        description="glmark2 GPU renderer.",
        runner=lambda args: run_glmark2(offscreen=args.glmark2_mode == "offscreen"),
        requires=("glmark2",),
    ),
    BenchmarkDefinition(
        key="vkmark",
        categories=("gpu",),
        presets=("gpu-light", "gpu", "all"),
        description="vkmark Vulkan renderer.",
        runner=lambda args: run_vkmark(),
        requires=("vkmark",),
    ),
    BenchmarkDefinition(
        key="ffmpeg-transcode",
        categories=("cpu", "media"),
        presets=("all",),
        description="FFmpeg software transcode.",
        runner=lambda args: run_ffmpeg_benchmark(
            DEFAULT_FFMPEG_RESOLUTION,
            DEFAULT_FFMPEG_DURATION,
            DEFAULT_FFMPEG_CODEC,
        ),
        requires=("ffmpeg",),
    ),
    BenchmarkDefinition(
        key="x264-encode",
        categories=("cpu", "media"),
        presets=("all",),
        description="Raw x264 encode throughput.",
        runner=lambda args: run_x264_benchmark(
            DEFAULT_X264_RESOLUTION,
            DEFAULT_X264_FRAMES,
            DEFAULT_X264_PRESET,
            DEFAULT_X264_CRF,
        ),
        requires=("x264", "ffmpeg"),
    ),
    BenchmarkDefinition(
        key="sqlite-mixed",
        categories=("io", "database"),
        presets=("balanced", "io", "all"),
        description="SQLite insert/select mix.",
        runner=lambda args: run_sqlite_benchmark(
            DEFAULT_SQLITE_ROWS, DEFAULT_SQLITE_SELECTS
        ),
    ),
    BenchmarkDefinition(
        key="tinymembench",
        categories=("memory",),
        presets=("memory", "all"),
        description="TinyMemBench memory throughput.",
        runner=lambda args: run_tinymembench(),
        requires=("tinymembench",),
    ),
    BenchmarkDefinition(
        key="clpeak",
        categories=("gpu", "compute"),
        presets=("gpu", "all"),
        description="OpenCL peak bandwidth/compute.",
        runner=lambda args: run_clpeak(),
        requires=("clpeak",),
    ),
    BenchmarkDefinition(
        key="zstd-compress",
        categories=("cpu", "compression"),
        presets=("cpu", "compression", "all"),
        description="zstd compress/decompress throughput.",
        runner=lambda args: run_zstd_benchmark(
            DEFAULT_ZSTD_LEVEL, DEFAULT_COMPRESS_SIZE_MB
        ),
        requires=("zstd",),
    ),
    BenchmarkDefinition(
        key="pigz-compress",
        categories=("cpu", "compression"),
        presets=("cpu", "compression", "all"),
        description="pigz compress/decompress throughput.",
        runner=lambda args: run_pigz_benchmark(
            DEFAULT_PIGZ_LEVEL, DEFAULT_COMPRESS_SIZE_MB
        ),
        requires=("pigz",),
    ),
    BenchmarkDefinition(
        key="hashcat-benchmark",
        categories=("cpu", "crypto", "gpu"),
        presets=("cpu", "crypto", "all"),
        description="hashcat self-contained benchmark.",
        runner=lambda args: run_hashcat_benchmark(),
        requires=("hashcat",),
    ),
    BenchmarkDefinition(
        key="cryptsetup-benchmark",
        categories=("crypto", "io"),
        presets=("crypto", "io", "all"),
        description="cryptsetup cipher benchmark.",
        runner=lambda args: run_cryptsetup_benchmark(),
        requires=("cryptsetup",),
    ),
    BenchmarkDefinition(
        key="ioping",
        categories=("io",),
        presets=("io", "all"),
        description="ioping latency probe.",
        runner=lambda args: run_ioping(DEFAULT_IOPING_COUNT),
        requires=("ioping",),
    ),
    BenchmarkDefinition(
        key="hdparm",
        categories=("io",),
        presets=("io", "all"),
        description="hdparm cached/buffered read speed.",
        runner=lambda args: run_hdparm(),
        requires=("hdparm",),
        availability_check=lambda args: (
            find_first_block_device() is not None,
            "No readable block device found",
        ),
    ),
    BenchmarkDefinition(
        key="fsmark",
        categories=("io",),
        presets=("io", "all"),
        description="fs_mark small file benchmark.",
        runner=lambda args: run_fsmark(),
        requires=("fs_mark",),
    ),
    BenchmarkDefinition(
        key="filebench",
        categories=("io",),
        presets=("io", "all"),
        description="filebench micro workload.",
        runner=lambda args: run_filebench(),
        requires=("filebench",),
    ),
    BenchmarkDefinition(
        key="pgbench",
        categories=("database", "io"),
        presets=("database", "all"),
        description="PostgreSQL pgbench on local socket.",
        runner=lambda args: run_pgbench(DEFAULT_PGBENCH_SCALE, DEFAULT_PGBENCH_TIME),
        requires=("initdb", "pgbench", "pg_ctl", "createdb"),
    ),
    BenchmarkDefinition(
        key="sqlite-speedtest",
        categories=("io", "database"),
        presets=("database", "io", "all"),
        description="SQLite speedtest-style insert/select.",
        runner=lambda args: run_sqlite_speedtest(DEFAULT_SQLITE_ROWS, DEFAULT_SQLITE_SELECTS),
    ),
    BenchmarkDefinition(
        key="iperf3-loopback",
        categories=("network",),
        presets=("network", "all"),
        description="iperf3 loopback throughput.",
        runner=lambda args: run_iperf3_loopback(DEFAULT_IPERF_DURATION),
        requires=("iperf3",),
    ),
    BenchmarkDefinition(
        key="netperf",
        categories=("network",),
        presets=("network", "all"),
        description="netperf TCP_STREAM loopback.",
        runner=lambda args: run_netperf(DEFAULT_NETPERF_DURATION),
        requires=("netperf", "netserver"),
    ),
]


def preset_help_text() -> str:
    rows = [
        f"{name}: {data['description']}"
        for name, data in sorted(PRESET_DEFINITIONS.items())
    ]
    return "; ".join(rows)


def unique_ordered(values: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(values))


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


def execute_definition(
    definition: BenchmarkDefinition, args: argparse.Namespace
) -> Dict[str, object]:
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
        if memcpy is None and metrics:
            memcpy = max(metrics.values())
        if memcpy is not None:
            return f"{memcpy:,.0f} MB/s"
    elif name == "clpeak":
        bandwidth = metrics.get("global_mem_bandwidth_gbps_float")
        if bandwidth is None and metrics:
            bandwidth = max(metrics.values())
        if bandwidth is not None:
            return f"{bandwidth:.1f} GB/s"
    elif name == "zstd-compress" or name == "pigz-compress":
        comp = metrics.get("compress_mb_per_s")
        decomp = metrics.get("decompress_mb_per_s")
        if comp is not None and decomp is not None:
            return f"C {comp:.0f}/D {decomp:.0f} MB/s"
    elif name == "hashcat-benchmark":
        throughput = metrics.get("throughput_hps")
        if throughput is not None:
            return f"{throughput/1_000_000:.1f} MH/s"
    elif name == "cryptsetup-benchmark":
        speeds = [value for key, value in metrics.items() if key.endswith("_enc_mib_per_s")]
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
            f'<th title="Presets: {html.escape(preset_label)}">'
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
        choices=sorted(definition.key for definition in BENCHMARK_DEFINITIONS),
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
        for definition in BENCHMARK_DEFINITIONS:
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

    definition_map = {
        definition.key: definition for definition in BENCHMARK_DEFINITIONS
    }
    results: List[Dict[str, object]] = []
    for name in selected_names:
        definition = definition_map[name]
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
