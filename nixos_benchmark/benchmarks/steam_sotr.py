from __future__ import annotations

import contextlib
import csv
from collections.abc import Iterable
from pathlib import Path

from .steam_base import SteamBenchmarkBase
from .types import BenchmarkType


def _find_column_index(hdr_lower: list[str], names: Iterable[str]) -> int | None:
    for name in names:
        if name in hdr_lower:
            return hdr_lower.index(name)
    return None


def _parse_csv_for_metrics(csvfile: Path) -> dict[str, float] | None:
    """Parse a CSV and extract fps metrics if present."""
    try:
        with csvfile.open() as fh:
            reader = csv.reader(fh)
            headers = None
            rows: list[list[str]] = []
            for row in reader:
                if headers is None:
                    headers = [h.strip() for h in row]
                    continue
                rows.append(row)
        if not rows or not headers:
            return None

        hdr_lower = [h.lower() for h in headers]
        metrics: dict[str, float] = {}

        avg_idx = _find_column_index(hdr_lower, ("average", "avg fps", "avg"))
        min_idx = _find_column_index(hdr_lower, ("minimum", "min fps", "min"))
        max_idx = _find_column_index(hdr_lower, ("maximum", "max fps", "max"))

        if avg_idx is not None:
            with contextlib.suppress(Exception):
                metrics["fps_avg"] = float(rows[-1][avg_idx])
        if min_idx is not None:
            with contextlib.suppress(Exception):
                metrics["fps_min"] = float(rows[-1][min_idx])
        if max_idx is not None:
            with contextlib.suppress(Exception):
                metrics["fps_max"] = float(rows[-1][max_idx])

        if metrics:
            metrics.setdefault("total_frames", 0)
            return metrics
    except Exception:
        return None
    return None


class SteamSoTRBenchmark(SteamBenchmarkBase):
    benchmark_type = BenchmarkType.STEAM_SOTR
    description = "Shadow of the Tomb Raider built-in benchmark"
    app_id = 750920
    process_name = "sotr"  # loose match for process name
    _launch_args = ("-benchmark",)
    _result_timeout = 600.0
    _start_timeout = 180.0

    def _parse_game_results(self, steam_root: Path, game_dir: Path | None) -> dict[str, float] | None:
        # Proton prefix path where SotTR writes CSV results
        compat = steam_root / "steamapps" / "compatdata" / str(self.app_id)
        candidates = [
            compat / "pfx" / "drive_c" / "users" / "steamuser" / "Documents" / "Shadow of the Tomb Raider",
            compat / "pfx" / "drive_c" / "users" / "steamuser" / "Documents",
        ]
        for base in candidates:
            if not base.exists():
                continue
            for csvfile in sorted(base.glob("**/*.csv"), key=lambda p: p.stat().st_mtime, reverse=True):
                # Quick check for likely CSV content then try parsing helper
                try:
                    text = csvfile.read_text(errors="ignore")
                except Exception:
                    continue
                if "average" in text.lower() or "fps" in text.lower() or "frames" in text.lower():
                    metrics = _parse_csv_for_metrics(csvfile)
                    if metrics:
                        return metrics
        return None
