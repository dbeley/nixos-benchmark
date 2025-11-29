"""Database benchmarks."""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..parsers import parse_pgbench_output
from ..utils import find_free_tcp_port, run_command
from .base import (
    DEFAULT_PGBENCH_SCALE,
    DEFAULT_PGBENCH_TIME,
    DEFAULT_SQLITE_ROWS,
    DEFAULT_SQLITE_SELECTS,
)


def run_sqlite_benchmark(
    row_count: int = DEFAULT_SQLITE_ROWS,
    select_queries: int = DEFAULT_SQLITE_SELECTS,
) -> BenchmarkResult:
    """Run SQLite insert/select mix benchmark."""
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

    metrics_data = {
        "insert_rows_per_s": row_count / insert_duration if insert_duration else 0.0,
        "selects_per_s": select_queries / query_duration if query_duration else 0.0,
        "row_count": row_count,
        "select_queries": select_queries,
    }
    total_duration = insert_duration + query_duration

    return BenchmarkResult(
        name="sqlite-mixed",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters(
            {
                "row_count": row_count,
                "select_queries": select_queries,
            }
        ),
        duration_seconds=total_duration,
        command="python-sqlite3-inline",
        raw_output="",
    )


def run_sqlite_speedtest(
    row_count: int = DEFAULT_SQLITE_ROWS, select_queries: int = DEFAULT_SQLITE_SELECTS
) -> BenchmarkResult:
    """Run SQLite speedtest-style insert/select benchmark."""
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

    metrics_data = {
        "insert_rows_per_s": row_count / insert_duration if insert_duration else 0.0,
        "indexed_selects_per_s": select_queries / query_duration
        if query_duration
        else 0.0,
        "row_count": row_count,
        "select_queries": select_queries,
    }
    total_duration = insert_duration + query_duration

    return BenchmarkResult(
        name="sqlite-speedtest",
        status="ok",
        categories=(),
        presets=(),
        metrics=BenchmarkMetrics(metrics_data),
        parameters=BenchmarkParameters(
            {"row_count": row_count, "select_queries": select_queries}
        ),
        duration_seconds=total_duration,
        command="python-sqlite3-speedtest",
        raw_output="",
    )


def run_pgbench(
    scale: int = DEFAULT_PGBENCH_SCALE, seconds: int = DEFAULT_PGBENCH_TIME
) -> BenchmarkResult:
    """Run PostgreSQL pgbench on local socket."""
    data_dir = Path(tempfile.mkdtemp(prefix="pgbench-"))
    port = find_free_tcp_port()
    socket_dir = data_dir / "socket"
    socket_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PGHOST"] = str(socket_dir)
    env["PGPORT"] = str(port)
    try:
        command = [
            "initdb",
            "-D",
            str(data_dir),
            "-A",
            "trust",
            "--no-locale",
            "--encoding",
            "UTF8",
        ]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        command = [
            "pg_ctl",
            "-D",
            str(data_dir),
            "-o",
            f"-F -k {socket_dir} -p {port}",
            "-w",
            "start",
        ]
        stdout, _, returncode = run_command(command)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        command = ["createdb", "benchdb"]
        stdout, _, returncode = run_command(command, env=env)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        command = ["pgbench", "-i", "-s", str(scale), "benchdb"]
        stdout, _, returncode = run_command(command, env=env)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        command = ["pgbench", "-T", str(seconds), "benchdb"]
        stdout, duration, returncode = run_command(command, env=env)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command, stdout)
        
        try:
            metrics_data = parse_pgbench_output(stdout)
            status = "ok"
            metrics = BenchmarkMetrics(metrics_data)
            message = ""
        except ValueError as e:
            # Preserve output even when parsing fails
            status = "error"
            metrics = BenchmarkMetrics({})
            message = str(e)
    finally:
        try:
            command = ["pg_ctl", "-D", str(data_dir), "-m", "fast", "stop"]
            _, _, _ = run_command(command)
        except Exception:
            pass
        shutil.rmtree(data_dir, ignore_errors=True)

    if status == "ok":
        metrics_data["scale"] = scale
        metrics_data["duration_s"] = seconds

    return BenchmarkResult(
        name="pgbench",
        status=status,
        categories=(),
        presets=(),
        metrics=metrics,
        parameters=BenchmarkParameters({"scale": scale, "duration_s": seconds}),
        duration_seconds=duration,
        command=f"pgbench -T {seconds} benchdb",
        raw_output=stdout,
        message=message,
    )


# Benchmark definitions for registration
def get_database_benchmarks():
    """Get list of database benchmark definitions."""
    from .base import BenchmarkDefinition

    return [
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
            key="sqlite-speedtest",
            categories=("io", "database"),
            presets=("database", "io", "all"),
            description="SQLite speedtest-style insert/select.",
            runner=lambda args: run_sqlite_speedtest(
                DEFAULT_SQLITE_ROWS, DEFAULT_SQLITE_SELECTS
            ),
        ),
        BenchmarkDefinition(
            key="pgbench",
            categories=("database", "io"),
            presets=("database", "all"),
            description="PostgreSQL pgbench on local socket.",
            runner=lambda args: run_pgbench(DEFAULT_PGBENCH_SCALE, DEFAULT_PGBENCH_TIME),
            requires=("initdb", "pgbench", "pg_ctl", "createdb"),
        ),
    ]
