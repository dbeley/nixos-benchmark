"""I/O benchmarks."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import (
    parse_filebench_output,
    parse_fsmark_output,
    parse_hdparm_output,
    parse_ioping_output,
)
from ..utils import find_first_block_device, run_command
from .base import (
    DEFAULT_FIO_BLOCK_KB,
    DEFAULT_FIO_RUNTIME,
    DEFAULT_FIO_SIZE_MB,
    DEFAULT_IOPING_COUNT,
)


def run_fio(
    size_mb: int = DEFAULT_FIO_SIZE_MB,
    runtime: int = DEFAULT_FIO_RUNTIME,
    block_kb: int = DEFAULT_FIO_BLOCK_KB,
) -> BenchmarkResult:
    """Run fio sequential I/O benchmark."""
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
        stdout, duration, returncode = run_command(["fio", "--output-format=json", str(job_path)])
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, ["fio", "--output-format=json", str(job_path)], stdout)
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

    metrics_data = {
        "seqwrite_mib_per_s": float(write_stats.get("bw", 0.0)) / 1024,
        "seqwrite_iops": float(write_stats.get("iops", 0.0)),
        "seqread_mib_per_s": float(read_stats.get("bw", 0.0)) / 1024,
        "seqread_iops": float(read_stats.get("iops", 0.0)),
    }

    return BenchmarkResult(
        name="fio-seq",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters(
            {"size_mb": size_mb, "runtime_s": runtime, "block_kb": block_kb}
        ),
        duration_seconds=duration,
        command=f"fio --output-format=json {job_path}",
        raw_output=stdout,
    )


def run_ioping(count: int = DEFAULT_IOPING_COUNT) -> BenchmarkResult:
    """Run ioping latency benchmark."""
    command = ["ioping", "-c", str(count), "."]
    stdout, duration, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    metrics_data = parse_ioping_output(stdout)
    metrics_data["requests"] = count

    return BenchmarkResult(
        name="ioping",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"count": count}),
        duration_seconds=duration,
        command=f"ioping -c {count} .",
        raw_output=stdout,
    )


def run_hdparm(device: str | None = None) -> BenchmarkResult:
    """Run hdparm disk read speed test."""
    target = device or find_first_block_device()
    if not target:
        raise FileNotFoundError("No suitable block device found for hdparm")
    command = ["hdparm", "-Tt", target]
    stdout, duration, returncode = run_command(command)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command, stdout)
    metrics_data = parse_hdparm_output(stdout)
    metrics_data["device"] = target

    return BenchmarkResult(
        name="hdparm",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"device": target}),
        duration_seconds=duration,
        command=f"hdparm -Tt {target}",
        raw_output=stdout,
    )


def run_fsmark() -> BenchmarkResult:
    """Run fsmark filesystem benchmark."""
    workdir = Path("results/fsmark")
    workdir.mkdir(parents=True, exist_ok=True)
    command = [
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
    try:
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        metrics_data = parse_fsmark_output(stdout)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return BenchmarkResult(
        name="fsmark",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"files": 200, "size_kb": 1024}),
        duration_seconds=duration,
        command=f"fs_mark -d {workdir} -n 200 -s 1024 -t 1 -k",
        raw_output=stdout,
    )


def run_filebench() -> BenchmarkResult:
    """Run filebench micro workload."""
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

    command = ["filebench", "-f", str(workload_path)]
    try:
        stdout, duration, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        metrics_data = parse_filebench_output(stdout)
    finally:
        workload_path.unlink(missing_ok=True)
        shutil.rmtree(workdir, ignore_errors=True)

    return BenchmarkResult(
        name="filebench",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters({"runtime_s": 5}),
        duration_seconds=duration,
        command=f"filebench -f {workload_path}",
        raw_output=stdout,
    )


# Benchmark definitions for registration
def get_io_benchmarks():
    """Get list of I/O benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
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
    ]
