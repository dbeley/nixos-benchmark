from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import run_command
from .base import (
    DEFAULT_FIO_BLOCK_KB,
    DEFAULT_FIO_RUNTIME,
    DEFAULT_FIO_SIZE_MB,
    BenchmarkBase,
)


class FIOBenchmark(BenchmarkBase):
    name = "fio-seq"
    description = "fio sequential read/write"
    _required_commands = ("fio",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        size_mb = DEFAULT_FIO_SIZE_MB
        runtime = DEFAULT_FIO_RUNTIME
        block_kb = DEFAULT_FIO_BLOCK_KB

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
            presets=(),
            metrics=BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data)),
            parameters=BenchmarkParameters({"size_mb": size_mb, "runtime_s": runtime, "block_kb": block_kb}),
            duration_seconds=duration,
            command=f"fio --output-format=json {job_path}",
            raw_output=stdout,
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        read_bw = result.metrics.get("seqread_mib_per_s")
        write_bw = result.metrics.get("seqwrite_mib_per_s")
        if read_bw is not None and write_bw is not None:
            return f"R {read_bw:.1f} / W {write_bw:.1f} MiB/s"
        return ""
