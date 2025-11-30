from __future__ import annotations

import argparse
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from .base import (
    DEFAULT_SQLITE_ROWS,
    DEFAULT_SQLITE_SELECTS,
    BenchmarkBase,
)


class SQLiteMixedBenchmark(BenchmarkBase):
    name = "sqlite-mixed"
    description = "SQLite insert/select mix"

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        row_count = DEFAULT_SQLITE_ROWS
        select_queries = DEFAULT_SQLITE_SELECTS

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
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
            presets=(),
            metrics=BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data)),
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

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        if result.status != "ok":
            prefix = "Skipped" if result.status == "skipped" else "Error"
            return f"{prefix}: {result.message}"

        inserts = result.metrics.get("insert_rows_per_s")
        selects = result.metrics.get("selects_per_s")
        if inserts is not None and selects is not None:
            return f"Ins {inserts:.0f}/s Sel {selects:.0f}/s"
        return ""
