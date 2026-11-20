from __future__ import annotations

import argparse
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import cast

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from .base import BenchmarkBase
from .types import BenchmarkType


DEFAULT_SQLITE_ROWS = 100_000  # Increased from 50k for more representative testing
DEFAULT_SQLITE_SELECTS = 2_000  # Increased from 1k


class SQLiteBenchmark(BenchmarkBase):
    """SQLite insert/select run, optionally against an indexed column.

    One class serves both presets: the "speedtest" variant adds a journal mode
    and an index, which is the only difference between the two measurements.
    """

    def __init__(
        self,
        benchmark_type: BenchmarkType,
        description: str,
        *,
        indexed: bool,
        select_key: str,
    ) -> None:
        self.benchmark_type = benchmark_type
        self.description = description
        self.indexed = indexed
        self.select_key = select_key

    def get_version(self) -> str:
        return f"SQLite {sqlite3.sqlite_version}"

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        row_count = DEFAULT_SQLITE_ROWS
        select_queries = DEFAULT_SQLITE_SELECTS

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
            db_path = Path(tmp_db.name)
        conn = sqlite3.connect(db_path)
        insert_start = time.perf_counter()
        try:
            conn.execute("PRAGMA synchronous = OFF;")
            if self.indexed:
                conn.execute("PRAGMA journal_mode = MEMORY;")
            conn.execute("CREATE TABLE bench (id INTEGER PRIMARY KEY, value INTEGER);")
            with conn:
                conn.executemany(
                    "INSERT INTO bench(value) VALUES (?)",
                    ((i % 1000,) for i in range(row_count)),
                )
            insert_duration = time.perf_counter() - insert_start
            if self.indexed:
                conn.execute("CREATE INDEX idx_value ON bench(value);")
            query_start = time.perf_counter()
            cursor = conn.cursor()
            query = (
                "SELECT COUNT(*) FROM bench WHERE value = ?"
                if self.indexed
                else "SELECT AVG(value) FROM bench WHERE value >= ?"
            )
            for i in range(select_queries):
                cursor.execute(query, (i % 1000,))
                cursor.fetchone()
            query_duration = time.perf_counter() - query_start
        finally:
            conn.close()
            db_path.unlink(missing_ok=True)

        metrics_data = {
            "insert_rows_per_s": row_count / insert_duration if insert_duration else 0.0,
            self.select_key: select_queries / query_duration if query_duration else 0.0,
            "row_count": row_count,
            "select_queries": select_queries,
        }
        total_duration = insert_duration + query_duration

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status="ok",
            presets=(),
            metrics=BenchmarkMetrics(cast(dict[str, float | str | int], metrics_data)),
            parameters=BenchmarkParameters({"row_count": row_count, "select_queries": select_queries}),
            duration_seconds=total_duration,
            command=f"python-sqlite3-{self.benchmark_type.value}",
            raw_output="",
        )

    def format_result(self, result: BenchmarkResult) -> str:
        """Format result for display."""
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        inserts = result.metrics.get("insert_rows_per_s")
        selects = result.metrics.get(self.select_key)
        if inserts is not None and selects is not None:
            return f"Ins {inserts:,.0f}/s Sel {selects:,.0f}/s"
        return ""
