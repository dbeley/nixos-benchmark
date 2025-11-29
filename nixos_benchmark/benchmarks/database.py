"""Database benchmarks."""
from __future__ import annotations

import argparse
import sqlite3
import tempfile
import time
from pathlib import Path

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from .base import (
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
    ]
